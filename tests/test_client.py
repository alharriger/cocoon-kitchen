"""client._extra_body: parse LLM_EXTRA_BODY env into request params (no network).

This is the provider-neutral hook that lets config disable GLM's thinking mode
(the reason score_recipe returns valid JSON instead of empty content)."""
import pytest

from clean_recipe import client


def test_extra_body_unset(monkeypatch):
    monkeypatch.delenv("LLM_EXTRA_BODY", raising=False)
    assert client._extra_body() == {}


def test_extra_body_blank(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", "   ")
    assert client._extra_body() == {}


def test_extra_body_valid_object(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"thinking": {"type": "disabled"}}')
    assert client._extra_body() == {"thinking": {"type": "disabled"}}


def test_extra_body_invalid_json_fails_loud(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", "{not valid json}")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        client._extra_body()


def test_extra_body_non_object_fails_loud(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", '["a", "b"]')
    with pytest.raises(RuntimeError, match="JSON object"):
        client._extra_body()
