from __future__ import annotations
import json, os, time, logging
from pathlib import Path

import httpx

BASE = "https://graph.facebook.com/v21.0"

log = logging.getLogger("meta")


class MetaError(RuntimeError):
    """Graph API error that carries the response body (error.message / code / subcode)."""


def _raise_for_graph(r: httpx.Response) -> None:
    if r.is_success:
        return
    detail = r.text[:600]
    try:
        e = r.json().get("error", {})
        detail = (f"({e.get('code')}/{e.get('error_subcode')}) {e.get('message')} "
                  f"| type={e.get('type')} fbtrace_id={e.get('fbtrace_id')}")
    except Exception:  # noqa: BLE001
        pass
    raise MetaError(f"Graph {r.request.method} {r.request.url.path} -> {r.status_code}: {detail}")


class Meta:
    def __init__(self, page_id: str, page_token: str, ig_id: str | None = None):
        self.page_id = page_id
        self.token = page_token
        self.ig_id = ig_id
        self._client = httpx.Client(timeout=120.0)

    @classmethod
    def from_env(cls) -> "Meta":
        return cls(os.environ["META_PAGE_ID"], os.environ["META_PAGE_TOKEN"],
                   os.environ.get("IG_BUSINESS_ID"))

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "access_token": self.token}
        r = self._client.get(f"{BASE}/{path}", params=params)
        _raise_for_graph(r)
        return r.json()

    def _post(self, url: str, data=None, files=None) -> dict:
        r = self._client.post(url, data=data, files=files)
        _raise_for_graph(r)
        return r.json()

    # ---------- Facebook ----------
    def fb_upload_photo(self, image_path: str) -> str:
        with open(image_path, "rb") as fh:
            res = self._post(f"{BASE}/{self.page_id}/photos",
                             data={"published": "false", "access_token": self.token},
                             files={"source": (Path(image_path).name, fh, "image/jpeg")})
        return str(res["id"])

    def fb_create_post(self, message: str, media_fbids: list[str],
                       scheduled_publish_time: int | None = None,
                       now_unix: int | None = None) -> dict:
        data = {"message": message, "access_token": self.token}
        for i, fbid in enumerate(media_fbids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": str(fbid)},
                                                      separators=(",", ":"))
        scheduled = False
        if scheduled_publish_time is not None:
            lead = scheduled_publish_time - int(now_unix if now_unix is not None else time.time())
            if lead >= 600:
                data["published"] = "false"
                data["scheduled_publish_time"] = scheduled_publish_time
                scheduled = True
            else:
                log.warning("scheduled_publish_time only %ss ahead; publishing now", lead)
        res = self._post(f"{BASE}/{self.page_id}/feed", data=data)
        pid = str(res["id"])
        return {"id": pid, "url": f"https://facebook.com/{pid}", "scheduled": scheduled}

    def fb_publish_reel(self, video_url: str, description: str) -> dict:
        import time as _t
        start = self._post(f"{BASE}/{self.page_id}/video_reels",
                           data={"upload_phase": "start", "access_token": self.token})
        vid = str(start["video_id"])
        up = self._client.post(start["upload_url"],
                               headers={"Authorization": f"OAuth {self.token}",
                                        "file_url": video_url})
        _raise_for_graph(up)
        self._post(f"{BASE}/{self.page_id}/video_reels",
                   data={"upload_phase": "finish", "video_id": vid,
                         "video_state": "PUBLISHED", "description": description,
                         "access_token": self.token})
        deadline = _t.time() + 300
        while _t.time() < deadline:
            st = self._get(vid, {"fields": "status"})
            vs = (st.get("status") or {}).get("video_status")
            if vs in ("ready", "published"):
                return {"id": vid, "url": f"https://facebook.com/reel/{vid}"}
            if vs == "error":
                raise MetaError(f"fb reel {vid} processing error: {st}")
            _t.sleep(10)
        raise MetaError(f"fb reel {vid} not ready after 300s")

    # ---------- Instagram ----------
    def ig_publish_reel(self, video_url: str, caption: str) -> dict:
        import time as _t
        res = self._post(f"{BASE}/{self.ig_id}/media",
                         data={"media_type": "REELS", "video_url": video_url,
                               "caption": caption, "share_to_feed": "true",
                               "access_token": self.token})
        creation = str(res["id"])
        deadline = _t.time() + 300
        while _t.time() < deadline:
            st = self._get(creation, {"fields": "status_code"})
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code == "ERROR":
                raise MetaError(f"ig reel {creation} processing ERROR: {st}")
            _t.sleep(10)
        else:
            raise MetaError(f"ig reel {creation} not FINISHED after 300s")
        pub = self._post(f"{BASE}/{self.ig_id}/media_publish",
                         data={"creation_id": creation, "access_token": self.token})
        mid = str(pub["id"])
        try:
            link = self._get(mid, {"fields": "permalink"}).get("permalink")
        except Exception:  # noqa: BLE001
            link = None
        return {"id": mid, "url": link or f"https://instagram.com/reel/{mid}"}

    def ig_upload_temp(self, image_path: str) -> str:
        with open(image_path, "rb") as fh:
            res = self._post("https://tmpfiles.org/api/v1/upload",
                             files={"file": (Path(image_path).name, fh, "image/jpeg")})
        url = res["data"]["url"]           # https://tmpfiles.org/12345/pic.jpg
        return url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)

    def ig_create_item(self, image_url: str) -> str:
        res = self._post(f"{BASE}/{self.ig_id}/media",
                         data={"image_url": image_url, "is_carousel_item": "true",
                               "access_token": self.token})
        return str(res["id"])

    def ig_create_carousel(self, child_ids: list[str], caption: str) -> str:
        res = self._post(f"{BASE}/{self.ig_id}/media",
                         data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
                               "caption": caption, "access_token": self.token})
        return str(res["id"])

    def ig_publish(self, creation_id: str) -> dict:
        return self._post(f"{BASE}/{self.ig_id}/media_publish",
                          data={"creation_id": creation_id, "access_token": self.token})

    def ig_publish_images(self, image_urls: list[str], caption: str) -> dict:
        if len(image_urls) == 1:
            res = self._post(f"{BASE}/{self.ig_id}/media",
                             data={"image_url": image_urls[0], "caption": caption,
                                   "access_token": self.token})
            pub = self.ig_publish(str(res["id"]))
            return {"ok": True, "media_id": str(pub["id"])}
        child_ids = [self.ig_create_item(u) for u in image_urls[:10]]
        caro = self.ig_create_carousel(child_ids, caption)
        pub = self.ig_publish(caro)
        return {"ok": True, "media_id": str(pub["id"])}

    def fb_delete_post(self, post_id: str) -> dict:
        r = self._client.delete(f"{BASE}/{post_id}",
                                params={"access_token": self.token})
        _raise_for_graph(r)
        return r.json()

    def ig_delete_media(self, media_id: str) -> dict:
        r = self._client.delete(f"{BASE}/{media_id}",
                                params={"access_token": self.token})
        _raise_for_graph(r)
        return r.json()

    # ---------- tokens ----------
    def exchange_long_lived_token(self, app_id: str, app_secret: str, short_token: str) -> dict:
        return self._get("oauth/access_token",
                         {"grant_type": "fb_exchange_token", "client_id": app_id,
                          "client_secret": app_secret, "fb_exchange_token": short_token})

    def debug_token(self, token: str) -> dict:
        return self._get("debug_token", {"input_token": token})
