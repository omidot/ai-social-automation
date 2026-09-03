from __future__ import annotations
import json, os
from pathlib import Path

import httpx


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
        self.base = f"https://api.telegram.org/bot{self.token}"
        self._client = httpx.Client(timeout=60.0)

    def _post(self, method: str, data=None, files=None) -> dict:
        payload = {}
        for k, v in (data or {}).items():
            payload[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
        r = self._client.post(f"{self.base}/{method}", data=payload, files=files)
        r.raise_for_status()
        return r.json()

    def send_message(self, text: str, buttons: list[tuple[str, str]] | None = None) -> dict:
        data = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        if buttons:
            data["reply_markup"] = {"inline_keyboard": [
                [{"text": lbl, "callback_data": cb} for lbl, cb in buttons]]}
        return self._post("sendMessage", data=data)

    def send_media_group(self, image_paths: list[str], caption: str = "") -> dict:
        media, files = [], {}
        handles = []
        for i, p in enumerate(image_paths):
            key = f"photo{i}"
            item = {"type": "photo", "media": f"attach://{key}"}
            if i == 0 and caption:
                item["caption"] = caption
            media.append(item)
            fh = open(p, "rb")
            handles.append(fh)
            files[key] = (Path(p).name, fh, "image/jpeg")
        try:
            return self._post("sendMediaGroup",
                              data={"chat_id": self.chat_id,
                                    "media": json.dumps(media, ensure_ascii=False)},
                              files=files)
        finally:
            for fh in handles:
                fh.close()

    def send_document(self, path: str, caption: str = "") -> dict:
        with open(path, "rb") as fh:
            return self._post("sendDocument",
                              data={"chat_id": self.chat_id, "caption": caption},
                              files={"document": (Path(path).name, fh)})

    def get_updates(self, offset: int, timeout: int = 0) -> list[dict]:
        resp = self._post("getUpdates", data={"offset": offset, "timeout": timeout})
        return resp.get("result", [])

    def answer_callback(self, callback_id: str, text: str = "") -> dict:
        return self._post("answerCallbackQuery",
                          data={"callback_query_id": callback_id, "text": text})
