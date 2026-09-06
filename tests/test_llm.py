import pytest
from pipeline import llm

def test_parse_json_strips_fences():
    txt = 'Đây là kết quả:\n```json\n{"a": 1, "b": "x"}\n```\n'
    assert llm.parse_json_response(txt) == {"a": 1, "b": "x"}

def test_parse_json_plain_object():
    assert llm.parse_json_response('{"a": 2}') == {"a": 2}

def test_parse_json_bad_raises():
    with pytest.raises(llm.LLMError):
        llm.parse_json_response("no json here")

def test_auto_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(llm, "_claude", lambda s, u, t: (_ for _ in ()).throw(RuntimeError("no token")))
    monkeypatch.setattr(llm, "_gemini", lambda s, u, t: '{"ok": true}')
    assert llm.generate("sys", "usr", provider="auto") == '{"ok": true}'

def test_auto_all_fail_raises(monkeypatch):
    monkeypatch.setattr(llm, "_claude", lambda s, u, t: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(llm, "_gemini", lambda s, u, t: (_ for _ in ()).throw(RuntimeError("y")))
    with pytest.raises(llm.LLMError):
        llm.generate("s", "u", provider="auto")

def test_explicit_claude_only(monkeypatch):
    called = {}
    monkeypatch.setattr(llm, "_claude", lambda s, u, t: (called.__setitem__("c", True), "OUT")[1])
    monkeypatch.setattr(llm, "_gemini", lambda s, u, t: (called.__setitem__("g", True), "NOPE")[1])
    assert llm.generate("s", "u", provider="claude") == "OUT"
    assert "g" not in called


class _Resp:
    def __init__(self, text):
        self.text = text


def test_gemini_retries_on_503(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_call(client, model, contents, config):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 Service Unavailable")
        return _Resp('{"ok": true}')

    monkeypatch.setattr(llm, "_gemini_call", fake_call)
    assert llm._gemini("sys", "usr", 90) == '{"ok": true}'
    assert calls["n"] == 3


def test_gemini_gives_up_after_retries(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_call(client, model, contents, config):
        calls["n"] += 1
        raise RuntimeError("503 Service Unavailable / model is overloaded")

    monkeypatch.setattr(llm, "_gemini_call", fake_call)
    with pytest.raises(RuntimeError, match="503"):
        llm._gemini("sys", "usr", 90)
    assert calls["n"] == 3


def test_gemini_no_retry_on_client_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_call(client, model, contents, config):
        calls["n"] += 1
        raise RuntimeError("400 INVALID_ARGUMENT: bad request")

    monkeypatch.setattr(llm, "_gemini_call", fake_call)
    with pytest.raises(RuntimeError, match="400"):
        llm._gemini("sys", "usr", 90)
    assert calls["n"] == 1
