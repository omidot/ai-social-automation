import pytest
from pipeline.meta import Meta


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.log = []

    def _next(self, url, **kw):
        self.log.append((url, kw))
        return _R(self.responses.pop(0))


class _R:
    def __init__(self, payload):
        self._p = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _meta(http):
    m = Meta(page_id="PID", page_token="TOK", ig_id="IGID")
    m._client = http
    return m


def test_fb_upload_photo_returns_fbid(monkeypatch):
    http = FakeHTTP([{"id": "111"}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    monkeypatch.setattr("builtins.open", lambda *a, **k: __import__("io").BytesIO(b"x"))
    assert m.fb_upload_photo("x.jpg") == "111"
    url, kw = http.log[0]
    assert "PID/photos" in url
    assert kw["data"]["published"] == "false"


def test_fb_create_post_builds_attached_media(monkeypatch):
    http = FakeHTTP([{"id": "999_888"}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    res = m.fb_create_post("nội dung", ["1", "2"])
    assert res["id"] == "999_888"
    assert res["url"].endswith("999_888")
    url, kw = http.log[0]
    assert "PID/feed" in url
    assert kw["data"]["attached_media[0]"] == '{"media_fbid":"1"}'
    assert kw["data"]["attached_media[1]"] == '{"media_fbid":"2"}'


def test_ig_upload_temp_returns_dl_url(monkeypatch):
    http = FakeHTTP([{"data": {"url": "https://tmpfiles.org/12345/pic.jpg"}}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    monkeypatch.setattr("builtins.open", lambda *a, **k: __import__("io").BytesIO(b"x"))
    assert m.ig_upload_temp("pic.jpg") == "https://tmpfiles.org/dl/12345/pic.jpg"


def test_ig_carousel_flow(monkeypatch):
    http = FakeHTTP([{"id": "c1"}, {"id": "c2"}, {"id": "caro"}, {"id": "pub"}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    a = m.ig_create_item("http://img/1.jpg")
    b = m.ig_create_item("http://img/2.jpg")
    caro = m.ig_create_carousel([a, b], "chú thích")
    pub = m.ig_publish(caro)
    assert (a, b, caro) == ("c1", "c2", "caro")
    assert pub["id"] == "pub"
