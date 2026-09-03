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
