# Architecture

Source of truth for architecture decisions. Every significant decision gets a log entry (date, decision, why, revisit-when). Keep entries short; this is a decision record, not a tutorial.

## Core shape (v0)

```
recipe link / pasted text
   → parse.py (recipe-scrapers + wild-mode fallback + paste path)
   → normalize ingredients
   → score.py: score_recipe(title, ingredients) -> Verdict
        ├─ builds prompt from rubric/rubric.yaml (prompt.py)
        ├─ calls model (cheap tier)
        └─ validates JSON against schema.py — fail loudly on malformed output
   → consumed by BOTH app.py (Streamlit card) and evals/evaluate.py (harness)
   → log.py appends every input + verdict to JSONL
```

**The load-bearing rule:** `score_recipe()` is a pure, UI-agnostic function in `src/clean_recipe/`. It never imports Streamlit. The UI and the eval harness are both thin consumers. This is what makes the stack swappable later (FastAPI/Next.js) without moving the brains.

## Repo layout (target, from handoff plan §4)

```
cocoonkitchen/
├── CLAUDE.md, README.md, pyproject.toml, .env.example, .gitignore
├── ai_docs/                  # this documentation system
├── rubric/
│   ├── rubric.md             # human-readable (HUMAN-OWNED)
│   └── rubric.yaml           # machine-readable weights/bands/lists (placeholder until human finalizes)
├── src/clean_recipe/
│   ├── schema.py  parse.py  prompt.py  score.py  log.py
├── app.py                    # Streamlit UI
├── evals/
│   ├── golden_set.csv        # HUMAN-OWNED labels; template + sample rows only
│   ├── evaluate.py           # runner + metrics → results/
└── data/logs/                # runtime JSONL (gitignored)
```

## Decision log

### 2026-07-11 — Phase 2 core-engine decisions
- **Composite score & band are computed in code, not by the model.** `score.py` weights the model's six sub-scores by `rubric.yaml` and looks up the band cutoff. The human-owned weights stay authoritative and the roll-up is deterministic; the model only judges the six 0–100 sub-scores (higher = cleaner). **Revisit when:** an eval shows a model-produced holistic score beats the computed composite.
- **`parse.py` fetches URLs behind a pinned-IP SSRF guard.** Resolve + validate once, then connect to that exact IP while presenting the hostname for the Host header, TLS SNI, and cert verification — closing the DNS-rebinding TOCTOU (found in the Phase 2 security review). Timeout + 2 MiB cap + per-hop redirect revalidation. Paste remains the primary, network-free path (non-goal: scraper heroics).
- **`clean_recipe.cli`** is the dev/manual-test entrypoint (dotenv → `parse_recipe` → `score_recipe`); the real UI is Phase 3 (Streamlit).

### 2026-07-11 — LLM provider strategy: neutral seam, free-tier-first, eval-selected
Model access goes through a thin **OpenAI-compatible Chat Completions client** (`base_url` + `api_key` + `model` are config, not code) — no heavy provider-abstraction layer (anti-bloat). Nearly every candidate speaks this API: OpenAI, DeepSeek, Qwen, Zhipu GLM (via z.ai), Groq, Together, OpenRouter, and **Gemini via its OpenAI-compat endpoint**. Switching providers = changing env vars.
- **Development default (build + prove the whole pipeline): Zhipu GLM-4.5-Flash on z.ai** — always $0 in/out, JSON-schema output, 128K context, OpenAI-compatible (`base_url=https://api.z.ai/api/paas/v4`, `model=glm-4.5-flash`; the `/api/openai/v1` path returns a wrapped 404 — verified 2026-07-11), no card. **It is a thinking model** — reasoning tokens come back in a separate `reasoning_content` field and are spent before the answer, so budget `max_tokens` generously (≥512, more for a full Verdict) or `content` is empty. Sign up on **z.ai international**, NOT bigmodel.cn (needs a Chinese phone). ~1 req/sec limit is fine for dev; validate-and-retry-once covers its weaker adversarial-JSON robustness. **Per Amber (2026-07-11): build and test the entire system on GLM-Flash first, then defer model choice to the eval bake-off.**
- **Bargain candidates for the golden-set bake-off (Phase 5):** Gemini Flash-Lite (free ~1,500/day, $0.10/$0.40 paid, native strict schema), Groq `gpt-oss-20b` (free ~14,400/day, fastest), DeepSeek V4-flash (~$0.003 cached in, 1M ctx), Qwen-flash. **References (no free tier):** Claude Haiku 4.5 ($1/$5), GPT-5.4-nano ($0.20/$1.25).

**Selection rule:** the model is chosen by **golden-set band-accuracy + MAE, never by brand**. The eval harness (Phase 5) compares providers on one prompt. `Verdict` Pydantic validation already fails loud → add **validate-and-retry-once** so non-strict free models are safe. **Data note:** free tiers (Gemini, OpenAI data-sharing) may train on inputs — acceptable for v0 (public recipe text, no PII); revisit if inputs ever become sensitive. **Revisit when:** an eval number favors a specific model, free-tier limits throttle testers, or real volume makes a paid tier's economics matter. Pricing/capabilities verified 2026-07-11 across OpenAI, Gemini, DeepSeek, Qwen, GLM, Groq, Together, OpenRouter, and Claude. (Supersedes the incidental "anthropic" naming in the 2026-07-10 deps entry below — provider is now config, not a fixed dependency.)

### 2026-07-10 — Python 3.12 baseline; pinned, phase-scoped deps
`requires-python >=3.11`; Phase 1 runs on Python 3.12 (installed via Homebrew — the machine's system 3.9.6 is EOL). Deps are exact-pinned and added only when a phase uses them: Phase 1 ships `pydantic==2.10.6` + `pyyaml==6.0.2` (runtime) and `pytest==8.3.4` (dev). Streamlit / anthropic / recipe-scrapers are deferred to their phases (anti-bloat). **Revisit when:** a dep’s pin blocks a security fix, or 3.11 features are needed.

### 2026-07-09 — Streamlit for v0, FastAPI as upgrade path
Pure-Python end-to-end (recipe-scrapers is Python-only), free one-push deploy, card UI is Streamlit's sweet spot. Low UI ceiling accepted for a demo. **Revisit when:** UI needs exceed a card, or a customer needs an API.

### 2026-07-09 — No DB, no RAG, no auth, no vector store in v0
JSONL log is the only persistence. Each layer must later earn its place by moving an eval number. **Revisit when:** an eval number demands it.

### 2026-07-09 — Weights live in rubric.yaml, never in code
Tuning the rubric must never touch Python. Prompt is built from the yaml at runtime.

### 2026-07-09 — Docs system
CLAUDE.md = pointers only. ai_docs/ = source of truth per domain. working_sprint.md = live phase tracker / session handoff. Memory files = cross-session working practices only.

## Sub-agent usage model
- **Research/recon:** Explore or code-explorer agents — keep file-dumps out of the main context.
- **Phase planning:** Plan / code-architect agent produces the blueprint; main session edits + presents for approval.
- **Parallel build (Phase 2):** independent tracks (parser / scoring core / eval harness) as parallel agents in isolated worktrees, integrated on one branch afterward.
- **Quality gates:** code-reviewer agent + /security-review before any merge to main; /verify (end-to-end) before commit.
