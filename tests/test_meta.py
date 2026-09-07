import logging
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
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300

    def raise_for_status(self):
        pass

    def json(self):
        return self._p

    @property
    def text(self):
        import json as _j
        return _j.dumps(self._p)


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


def test_fb_create_post_scheduled(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    sent = {}
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (sent.update(data=data), {"id": "PID_9"})[1])
    r = m.fb_create_post("hello", ["1", "2"],
                         scheduled_publish_time=2000, now_unix=1000)
    assert r["scheduled"] is True
    assert sent["data"]["published"] == "false"
    assert sent["data"]["scheduled_publish_time"] == 2000


def test_fb_create_post_schedule_too_soon_publishes_now(monkeypatch, caplog):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK")
    sent = {}
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (sent.update(data=data), {"id": "PID_9"})[1])
    with caplog.at_level(logging.WARNING):
        r = m.fb_create_post("hi", ["1"], scheduled_publish_time=1100, now_unix=1000)
    assert r["scheduled"] is False
    assert "published" not in sent["data"] or sent["data"]["published"] == "true"
    assert any("publishing now" in r.message for r in caplog.records)


def test_fb_create_post_exact_600s_boundary_schedules(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK")
    sent = {}
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (sent.update(data=data), {"id": "PID_9"})[1])
    r = m.fb_create_post("hello", ["1", "2"],
                         scheduled_publish_time=1600, now_unix=1000)
    assert r["scheduled"] is True
    assert sent["data"]["published"] == "false"


def test_ig_publish_images_single(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    calls = []
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (calls.append((url, data)), {"id": "cid"})[1])
    r = m.ig_publish_images(["https://raw/x.jpg"], "cap")
    assert r == {"ok": True, "media_id": "cid"}
    assert any("media_publish" in u for u, _ in calls)


def test_ig_publish_images_carousel(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    seq = iter(["a", "b", "carousel", "published"])
    monkeypatch.setattr(m, "_post",
                        lambda url, data=None, files=None: {"id": next(seq)})
    r = m.ig_publish_images(["u1", "u2"], "cap")
    assert r["media_id"] == "published"


def test_fb_delete_post_calls_delete(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    seen = {}

    class _DR:
        status_code = 200
        is_success = True
        def json(self): return {"success": True}
        @property
        def text(self): return "{}"

    def fake_delete(url, params=None):
        seen["url"] = url
        seen["params"] = params
        return _DR()

    monkeypatch.setattr(m._client, "delete", fake_delete, raising=False)
    assert m.fb_delete_post("P_1") == {"success": True}
    assert seen["url"].endswith("/P_1")
    assert seen["params"]["access_token"] == "TOK"


def test_ig_delete_media_calls_delete(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")

    class _DR:
        status_code = 200
        is_success = True
        def json(self): return {"success": True}
        @property
        def text(self): return "{}"

    calls = []
    monkeypatch.setattr(m._client, "delete",
                        lambda url, params=None: (calls.append(url), _DR())[1],
                        raising=False)
    assert m.ig_delete_media("IG_9") == {"success": True}
    assert calls[0].endswith("/IG_9")


def test_fb_delete_post_raises_on_graph_error(monkeypatch):
    from pipeline.meta import Meta, MetaError
    m = Meta("PID", "TOK")

    class _ER:
        status_code = 400
        is_success = False
        def json(self): return {"error": {"code": 100, "message": "no such post"}}
        @property
        def text(self): return '{"error":{"code":100}}'
        class request:  # noqa: N801 - stub for _raise_for_graph's f-string
            method = "DELETE"
            class url:  # noqa: N801
                path = "/v21.0/P_1"

    monkeypatch.setattr(m._client, "delete",
                        lambda url, params=None: _ER(), raising=False)
    import pytest
    with pytest.raises(MetaError):
        m.fb_delete_post("P_1")
