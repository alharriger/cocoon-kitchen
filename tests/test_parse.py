"""parse.py: paste normalization, known-site + wild scrape extraction, and the
SSRF guard — all offline. No test performs a real network call: URL paths are
driven through local HTML strings or monkeypatched fetch/DNS."""
import socket

import pytest

from clean_recipe.parse import (
    ParseError,
    ParsedRecipe,
    _assert_public_url,
    _scrape_recipe,
    parse_recipe,
)

# A minimal schema.org Recipe page — enough for generic + domain extraction.
SCHEMA_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Test Cookies",
 "recipeIngredient":["1 cup flour","2 eggs","1/2 cup sugar"]}
</script></head><body></body></html>
"""

NO_RECIPE_HTML = "<html><head></head><body><p>just a blog, no recipe</p></body></html>"


# ---- paste path -------------------------------------------------------------

def test_paste_extracts_title_and_ingredients():
    r = parse_recipe("Grandma's Cookies\nflour\neggs\nsugar")
    assert isinstance(r, ParsedRecipe)
    assert r.title == "Grandma's Cookies"
    assert r.ingredients == ["flour", "eggs", "sugar"]
    assert r.source == "pasted"


def test_paste_normalizes_whitespace_and_blank_lines():
    text = "\n\n  Messy   Title  \n\n   flour  \t and   water \n\n\n eggs\n\n"
    r = parse_recipe(text)
    assert r.title == "Messy Title"
    assert r.ingredients == ["flour and water", "eggs"]


def test_paste_empty_input_fails_loud():
    with pytest.raises(ParseError):
        parse_recipe("   \n\n  ")


def test_paste_title_only_needs_ingredients():
    with pytest.raises(ParseError):
        parse_recipe("Just A Title")


# ---- scrape: known site -----------------------------------------------------

def test_known_site_extraction():
    # allrecipes.com is a supported domain; passing local HTML means no network.
    r = _scrape_recipe(SCHEMA_HTML, "https://www.allrecipes.com/recipe/123/")
    assert r.title == "Test Cookies"
    assert r.ingredients == ["1 cup flour", "2 eggs", "1/2 cup sugar"]
    assert r.source == "https://www.allrecipes.com/recipe/123/"


# ---- scrape: wild/generic fallback ------------------------------------------

def test_wild_mode_fallback_on_unknown_site():
    url = "https://totally-unknown-recipe-site.example/post"
    r = _scrape_recipe(SCHEMA_HTML, url)
    assert r.title == "Test Cookies"
    assert r.ingredients == ["1 cup flour", "2 eggs", "1/2 cup sugar"]
    assert r.source == url


def test_unusable_page_tells_caller_to_paste():
    with pytest.raises(ParseError, match="[Pp]aste"):
        _scrape_recipe(NO_RECIPE_HTML, "https://unknown-site.example/x")


def test_parse_recipe_url_path_uses_fetch(monkeypatch):
    # Route the URL branch through the scraper without touching the network.
    monkeypatch.setattr("clean_recipe.parse._fetch_html", lambda url: SCHEMA_HTML)
    r = parse_recipe("https://www.allrecipes.com/recipe/123/")
    assert r.title == "Test Cookies"
    assert r.source == "https://www.allrecipes.com/recipe/123/"


# ---- SSRF guard -------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",       # loopback
    "http://169.254.169.254/latest",  # link-local (cloud metadata)
    "http://10.0.0.1/",             # private
    "http://192.168.1.1/",          # private
    "http://0.0.0.0/",              # unspecified
])
def test_assert_public_url_rejects_internal_ips(url):
    # Literal IPs resolve locally via getaddrinfo — no DNS, no network.
    with pytest.raises(ParseError):
        _assert_public_url(url)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "data:text/html,hi",
])
def test_assert_public_url_rejects_non_http_schemes(url):
    with pytest.raises(ParseError, match="scheme"):
        _assert_public_url(url)


def test_assert_public_url_accepts_public_literal_ip():
    # 93.184.216.34 (example.com) is globally routable; literal → no DNS.
    assert _assert_public_url("https://93.184.216.34/recipe") == "93.184.216.34"


def test_assert_public_url_accepts_public_host_mocked_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                 ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert _assert_public_url("https://recipes.example.com/cookies") == "recipes.example.com"


def test_assert_public_url_rejects_host_resolving_to_private(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                 ("10.1.2.3", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ParseError, match="non-public"):
        _assert_public_url("https://sneaky.example.com/")
