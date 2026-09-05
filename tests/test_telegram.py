import pytest
from pipeline.telegram import Telegram


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, method, data=None, files=None):
        self.calls.append((method, data, files))
        return {"ok": True, "result": {}}


def test_send_message_with_buttons(monkeypatch):
    tg = Telegram(token="T", chat_id="C")
    rec = Recorder()
    monkeypatch.setattr(tg, "_post", rec)
    tg.send_message("xin chào", buttons=[("✅ Đăng", "approve:p1"), ("❌ Bỏ", "reject:p1")])
    method, data, _ = rec.calls[0]
    assert method == "sendMessage"
    assert data["chat_id"] == "C" and data["text"] == "xin chào"
    kb = data["reply_markup"]
    assert kb["inline_keyboard"][0][0] == {"text": "✅ Đăng", "callback_data": "approve:p1"}


def test_send_media_group_builds_attachments(tmp_path, monkeypatch):
    imgs = []
    for i in range(3):
        p = tmp_path / f"{i}.jpg"
        p.write_bytes(b"x")
        imgs.append(str(p))
    tg = Telegram(token="T", chat_id="C")
    rec = Recorder()
    monkeypatch.setattr(tg, "_post", rec)
    tg.send_media_group(imgs, caption="chú thích")
    method, data, files = rec.calls[0]
    assert method == "sendMediaGroup"
    assert len(files) == 3
    assert "chú thích" in data["media"]


def test_get_updates_returns_result_list(monkeypatch):
    tg = Telegram(token="T", chat_id="C")
    monkeypatch.setattr(tg, "_post", lambda m, data=None, files=None:
                        {"ok": True, "result": [{"update_id": 5}]})
    assert tg.get_updates(offset=0) == [{"update_id": 5}]


def test_download_file_writes_bytes(tmp_path, monkeypatch):
    tg = Telegram(token="T", chat_id="C")
    monkeypatch.setattr(tg, "_post", lambda m, data=None, files=None:
                        {"ok": True, "result": {"file_path": "voice/abc.oga"}})

    class Resp:
        content = b"audio-bytes"
        def raise_for_status(self): pass

    calls = []
    monkeypatch.setattr(tg._client, "get", lambda url: (calls.append(url), Resp())[1])
    dest = tmp_path / "sub" / "out.oga"
    result = tg.download_file("FILE123", str(dest))
    assert result == str(dest)
    assert dest.read_bytes() == b"audio-bytes"
    assert calls[0] == "https://api.telegram.org/file/botT/voice/abc.oga"
