"""Provider-profile registry (Phase 6 Task 4 bake-off): selection + activation.

No network. These cover the seam that lets `evaluate.py --provider X` point the
client at a different OpenAI-compatible endpoint without editing .env: the
registry lookup, the in-process env activation, thinking-flag hygiene between
providers, and the fail-loud/skip behaviours the bake-off relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# evals/ is not an installed package; put it on the path so we can import it.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))

import providers  # noqa: E402


def test_all_expected_providers_registered():
    assert set(providers.PROVIDERS) == {"glm", "gemini", "groq", "qwen", "deepseek"}


def test_thinking_models_disable_thinking_others_blank():
    # Reasoning models must ship thinking-off config (2026-07-11 pitfall);
    # non-thinking models carry a blank extra_body.
    assert '"thinking"' in providers.PROVIDERS["glm"].extra_body
    assert "enable_thinking" in providers.PROVIDERS["qwen"].extra_body
    assert providers.PROVIDERS["gemini"].extra_body == ""
    assert providers.PROVIDERS["groq"].extra_body == ""
    assert providers.PROVIDERS["deepseek"].extra_body == ""


def test_select_provider_returns_profile():
    p = providers.select_provider("gemini")
    assert p.name == "gemini"
    assert p.model == "gemini-3.1-flash-lite"
    assert p.key_env == "GEMINI_API_KEY"


def test_select_unknown_provider_fails_loud():
    with pytest.raises(ValueError, match="unknown provider"):
        providers.select_provider("gpt-9")


def test_activate_sets_client_env_from_profile(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-key")
    # A leftover thinking flag from a prior provider must be cleared.
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"thinking": {"type": "disabled"}}')

    providers.activate(providers.PROVIDERS["gemini"])

    import os
    assert os.environ["LLM_API_KEY"] == "sk-test-key"
    assert os.environ["LLM_BASE_URL"] == providers.PROVIDERS["gemini"].base_url
    assert os.environ["LLM_MODEL"] == "gemini-3.1-flash-lite"
    # gemini has a blank extra_body → the stale GLM flag is removed, not kept.
    assert "LLM_EXTRA_BODY" not in os.environ


def test_activate_sets_extra_body_for_thinking_model(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "sk-qwen")
    monkeypatch.delenv("LLM_EXTRA_BODY", raising=False)

    providers.activate(providers.PROVIDERS["qwen"])

    import os
    assert os.environ["LLM_EXTRA_BODY"] == '{"enable_thinking": false}'


def test_activate_missing_key_raises_missing_key_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(providers.MissingKeyError, match="DEEPSEEK_API_KEY"):
        providers.activate(providers.PROVIDERS["deepseek"])


def test_activate_blank_key_treated_as_missing(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    with pytest.raises(providers.MissingKeyError):
        providers.activate(providers.PROVIDERS["groq"])


def test_missing_key_error_does_not_leak_key_value(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "super-secret-token")
    # A blank/whitespace key triggers the error; a *present* key never reaches
    # the error path — but assert the message only ever names the env var.
    monkeypatch.setenv("QWEN_API_KEY", "")
    try:
        providers.activate(providers.PROVIDERS["qwen"])
    except providers.MissingKeyError as e:
        assert "super-secret-token" not in str(e)
        assert "QWEN_API_KEY" in str(e)
