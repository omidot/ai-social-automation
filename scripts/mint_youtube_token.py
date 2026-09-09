"""One-time: mint a YouTube Data API refresh token.

Prereq: a Google Cloud project with the YouTube Data API v3 enabled, an OAuth
client of type "Desktop app", and the OAuth consent screen set to **Production**
(Testing-mode refresh tokens expire after 7 days). Add scope
https://www.googleapis.com/auth/youtube.upload

Usage:
    python scripts/mint_youtube_token.py --client-id XXX --client-secret YYY

It opens a browser, you approve, and it prints the three secret values to put in
GitHub → Settings → Secrets and variables → Actions:
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
"""
from __future__ import annotations
import argparse
import http.server
import secrets
import urllib.parse
import webbrowser

import httpx

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
_REDIRECT = "http://localhost:8765/"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    state = secrets.token_urlsafe(16)
    q = urllib.parse.urlencode({
        "client_id": args.client_id, "redirect_uri": _REDIRECT,
        "response_type": "code", "scope": _SCOPE, "state": state,
        "access_type": "offline", "prompt": "consent"})
    code_box: dict[str, str] = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            p = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(p.query)
            if qs.get("state", [""])[0] == state and "code" in qs:
                code_box["code"] = qs["code"][0]
                self.send_response(200); self.end_headers()
                self.wfile.write(b"OK - close this tab.")
            else:
                self.send_response(400); self.end_headers()
        def log_message(self, *a):  # noqa: A003
            pass

    print("Opening browser for Google consent...")
    webbrowser.open(f"{_AUTH}?{q}")
    srv = http.server.HTTPServer(("localhost", 8765), H)
    while "code" not in code_box:
        srv.handle_request()

    r = httpx.post(_TOKEN, data={
        "client_id": args.client_id, "client_secret": args.client_secret,
        "code": code_box["code"], "grant_type": "authorization_code",
        "redirect_uri": _REDIRECT})
    r.raise_for_status()
    rt = r.json()["refresh_token"]
    print("\n=== GitHub Secrets ===")
    print(f"YOUTUBE_CLIENT_ID={args.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={args.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={rt}")


if __name__ == "__main__":
    main()
