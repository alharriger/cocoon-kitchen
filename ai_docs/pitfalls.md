# Pitfalls — Working Relationship Log

Every mistake gets logged here during the retrospective (or immediately, if it bit us mid-phase). The point is iteration: a pitfall entry isn't blame, it's a prevention rule. **Check this file before starting work; don't repeat an entry.**

## Entry format
```
### YYYY-MM-DD — short title
**What happened:** one or two sentences.
**Root cause:** the actual why, not the symptom.
**Prevention rule:** the concrete behavior change (checklist item, doc update, process step).
**Status:** Active | Retired (rule absorbed into process/memory)
```

---

### 2026-07-10 — Package name ≠ import name
**What happened:** The project/distribution is named `cocoonkitchen` (`pyproject.toml`, `pip install -e .`) but the source package — and therefore the import name — is `clean_recipe` (`src/clean_recipe/`). Writing `from cocoonkitchen import ...` fails.
**Root cause:** The `cleanplate → cocoonkitchen` rename updated docs and the distribution name but intentionally left the code package as `clean_recipe` (architecture.md target layout).
**Prevention rule:** Imports use `clean_recipe` (e.g. `from clean_recipe.schema import Verdict`). The name `cocoonkitchen` is only the pip/distribution name. Don't "fix" this mismatch — it's by design.
**Status:** Active

### 2026-07-10 — Bare `python` is not on PATH
**What happened:** `python` and `python -m pytest` fail (`command not found`); system `python3` is EOL 3.9.6 without pytest.
**Root cause:** This machine has no `python` shim; the working interpreter is the project venv.
**Prevention rule:** Run Python via `.venv/bin/python` (e.g. `.venv/bin/python -m pytest`), or activate the venv first. Don't assume a bare `python`.
**Status:** Active
