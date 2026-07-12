"""Recipe ingestion: ``parse_recipe(source) -> ParsedRecipe``.

Turns a recipe URL *or* pasted recipe text into a normalized ingredient list —
the input side of the scoring core (score.py is the output side). Three paths:

1. **Paste** — ``source`` is raw text. First non-empty line is the title, the
   rest are ingredients. Light normalization only. This is the reliable
   fallback: no network, no parsing heroics.
2. **Known site** — an http(s) URL for a domain recipe-scrapers supports. We
   fetch the page and let the domain scraper extract title + ingredients.
3. **Wild/generic** — an http(s) URL for an unknown domain. We fall back to
   recipe-scrapers' generic schema.org extraction. If nothing usable comes
   back we fail loud and tell the caller to paste instead — per the product
   non-goal, paste is the fallback, not scraper edge-case heroics.

SECURITY: recipe URLs and pasted text are UNTRUSTED input (Contract 3 in
ai_docs/llm_contracts.md; see architecture.md). A recipe URL is an SSRF surface:
before any fetch, ``_assert_public_url`` resolves the host and refuses private,
loopback, link-local, and reserved targets, and only http/https schemes are
allowed. Fetches are bounded by a timeout and a byte cap, and each redirect hop
is re-validated. We fail loudly on unusable input rather than emit a partial
result.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter, PoolManager
from pydantic import BaseModel
from recipe_scrapers import scrape_html
from recipe_scrapers._exceptions import (
    RecipeScrapersExceptions,
    WebsiteNotImplementedError,
)

_ALLOWED_SCHEMES = {"http", "https"}
# Ingredient lines are short. A pasted line longer than this reads as prose (an
# article, a job posting, notes) rather than an ingredient — a cheap non-recipe
# guard. Deliberately generous to avoid rejecting real recipes; the scorer's
# is_recipe judgment (score.py) is the semantic backstop for subtler junk.
_MAX_INGREDIENT_LINE = 250
_FETCH_TIMEOUT = 10  # seconds, connect + read
_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB response cap
_MAX_REDIRECTS = 5
_USER_AGENT = "CocoonKitchen/0.1 (+recipe-scorer)"


class ParsedRecipe(BaseModel):
    """A recipe normalized to title + ingredient lines, ready to score.

    ``source`` is the original URL, or the literal ``"pasted"`` for text input.
    """

    title: str
    ingredients: list[str]
    source: str


class ParseError(RuntimeError):
    """Raised when input can't be turned into a usable ParsedRecipe.

    The message always tells the caller how to recover — for URLs that failed,
    that means pasting the recipe text instead.
    """


# ---- normalization ----------------------------------------------------------

def _normalize_line(line: str) -> str:
    """Strip ends and collapse internal runs of whitespace to single spaces."""
    return " ".join(line.split())


# ---- SSRF guard -------------------------------------------------------------

def _is_public_ip(ip: ipaddress._BaseAddress) -> bool:
    """True only for globally routable addresses; False for anything internal."""
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _assert_public_url(url: str) -> tuple[str, str]:
    """Validate ``url`` is a fetchable public http(s) endpoint; raise otherwise.

    Rejects non-http(s) schemes and any host that resolves to a private,
    loopback, link-local, multicast, reserved, or unspecified address. This is
    the SSRF guard for the untrusted recipe URL — call it before every fetch and
    on every redirect hop. Returns ``(host, pinned_ip)``: the validated hostname
    and the specific address to connect to. The caller MUST connect to exactly
    that pinned IP (see ``_fetch_html``), so the address we vetted here is the
    address we connect to — closing the DNS-rebinding TOCTOU where a second,
    independent resolution could return a private IP.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ParseError(
            f"refusing URL with scheme {parsed.scheme!r}; only http/https allowed"
        )
    host = parsed.hostname
    if not host:
        raise ParseError(f"URL has no host: {url!r}")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as e:
        raise ParseError(f"invalid port in URL {url!r}: {e}") from e

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ParseError(f"could not resolve host {host!r}: {e}") from e

    validated: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not _is_public_ip(ip):
            raise ParseError(
                f"refusing to fetch {host!r}: resolves to non-public address {ip}"
            )
        validated.append(str(ip))
    if not validated:
        raise ParseError(f"could not resolve host {host!r} to any address")
    return host, validated[0]


# ---- fetch ------------------------------------------------------------------

def _read_capped(resp: requests.Response) -> str:
    """Read a streamed response body up to ``_MAX_BYTES``, decoded to text."""
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=8192):
        total += len(chunk)
        if total > _MAX_BYTES:
            raise ParseError(
                f"recipe page exceeded {_MAX_BYTES}-byte cap; refusing to read more"
            )
        chunks.append(chunk)
    encoding = resp.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


class _PinnedIPAdapter(HTTPAdapter):
    """Route the connection to a pre-validated IP while presenting the original
    hostname for the Host header, TLS SNI, and certificate verification.

    This is what makes the SSRF guard airtight: ``requests`` would otherwise
    re-resolve the hostname itself, so a DNS-rebinding attacker could pass the
    guard with a public IP and then be connected to a private one. By pinning the
    exact address ``_assert_public_url`` vetted, the checked address and the
    connected address are guaranteed identical.
    """

    def __init__(self, hostname: str, ip: str, https: bool):
        self._hostname = hostname
        self._ip = ip
        # server_hostname drives SNI + cert validation against the real hostname
        # even though we connect to the IP. Only valid for TLS pools.
        self._extra_pool_kw = {"server_hostname": hostname} if https else {}
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs.update(self._extra_pool_kw)
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs
        )

    def send(self, request, **kwargs):
        request.headers["Host"] = self._hostname
        request.url = _replace_host(request.url, self._ip)
        return super().send(request, **kwargs)


def _replace_host(url: str, ip: str) -> str:
    """Rewrite the host in ``url`` to ``ip`` (bracketing IPv6), keeping port."""
    parsed = urlparse(url)
    host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return urlunparse(parsed._replace(netloc=netloc))


def _fetch_html(url: str) -> str:
    """Fetch ``url`` as HTML with the SSRF guard, a timeout, a byte cap, and
    manual redirect following (each hop re-validated). The connection is pinned
    to the exact IP validated for that hop. Raises ParseError on any network or
    policy failure."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        host, ip = _assert_public_url(current)
        session = requests.Session()
        session.mount(
            urlparse(current).scheme + "://",
            _PinnedIPAdapter(host, ip, https=urlparse(current).scheme == "https"),
        )
        try:
            resp = session.get(
                current,
                headers={"User-Agent": _USER_AGENT},
                timeout=_FETCH_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as e:
            session.close()
            raise ParseError(
                f"could not fetch {current!r}: {e}. Paste the recipe text instead."
            ) from e

        try:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise ParseError(f"redirect from {current!r} had no Location header")
                current = urljoin(current, location)
                continue
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                raise ParseError(
                    f"fetching {current!r} failed: {e}. Paste the recipe text instead."
                ) from e
            return _read_capped(resp)
        finally:
            resp.close()
            session.close()

    raise ParseError(f"too many redirects fetching {url!r}. Paste the recipe text instead.")


# ---- scrape -----------------------------------------------------------------

def _extract(scraper) -> tuple[str, list[str]] | None:
    """Pull a normalized (title, ingredients) out of a scraper, or None if the
    scraper yielded no usable title/ingredients."""
    title = _normalize_line(scraper.title() or "")
    ingredients = [
        norm for raw in scraper.ingredients() if (norm := _normalize_line(raw or ""))
    ]
    if not title or not ingredients:
        return None
    return title, ingredients


def _scrape_recipe(html: str, url: str) -> ParsedRecipe:
    """Extract a recipe from already-fetched HTML: try the domain-specific
    scraper first, then fall back to generic schema.org extraction. Raise a
    paste-instead ParseError when neither yields a usable recipe."""
    result: tuple[str, list[str]] | None = None

    # Path 2: known/supported domain.
    try:
        result = _extract(scrape_html(html=html, org_url=url, supported_only=True))
    except WebsiteNotImplementedError:
        result = None  # unknown domain — fall through to generic extraction
    except RecipeScrapersExceptions:
        result = None  # supported scraper couldn't find the fields — try generic

    # Path 3: wild/generic schema.org fallback.
    if result is None:
        try:
            result = _extract(scrape_html(html=html, org_url=url, supported_only=False))
        except RecipeScrapersExceptions as e:
            raise ParseError(
                f"could not extract a recipe from {url!r}: unsupported site and no "
                "generic recipe data found. Paste the recipe text instead."
            ) from e

    if result is None:
        raise ParseError(
            f"found a page at {url!r} but no title/ingredients to extract. "
            "Paste the recipe text instead."
        )

    title, ingredients = result
    return ParsedRecipe(title=title, ingredients=ingredients, source=url)


# ---- paste ------------------------------------------------------------------

def _parse_pasted(text: str) -> ParsedRecipe:
    """First non-empty line = title, remaining non-empty lines = ingredients."""
    lines = [norm for raw in text.splitlines() if (norm := _normalize_line(raw))]
    if not lines:
        raise ParseError("pasted recipe is empty")
    title, ingredients = lines[0], lines[1:]
    if not ingredients:
        raise ParseError(
            "pasted recipe needs a title line and at least one ingredient line"
        )
    if any(len(line) > _MAX_INGREDIENT_LINE for line in ingredients):
        raise ParseError(
            "this looks more like prose than a recipe. Paste a title line, then "
            "one ingredient per line."
        )
    return ParsedRecipe(title=title, ingredients=ingredients, source="pasted")


# ---- public entrypoint ------------------------------------------------------

def _looks_like_url(source: str) -> bool:
    """URL vs paste is decided by scheme: only http/https with a host is a URL."""
    parsed = urlparse(source.strip())
    return parsed.scheme in _ALLOWED_SCHEMES and bool(parsed.netloc)


def parse_recipe(source: str) -> ParsedRecipe:
    """Parse a recipe URL or pasted recipe text into a normalized ParsedRecipe.

    An http(s) URL is fetched (SSRF-guarded) and scraped; anything else is
    treated as pasted text. Raises ParseError on unusable input — for failed
    URLs the message tells the caller to paste the recipe instead.
    """
    if not source or not source.strip():
        raise ParseError("empty input: paste a recipe or provide a URL")
    if _looks_like_url(source):
        url = source.strip()
        return _scrape_recipe(_fetch_html(url), url)
    return _parse_pasted(source)
