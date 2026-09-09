from __future__ import annotations
import os
from pathlib import Path

import httpx

_API = "https://api.github.com"
_UPLOADS = "https://uploads.github.com"
RELEASE_TAG = "video-assets"


class AssetError(RuntimeError):
    pass


def _client(token: str) -> httpx.Client:
    return httpx.Client(
        timeout=300.0,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )


def _repo_token(repo: str | None, token: str | None) -> tuple[str, str]:
    repo = repo or os.environ["GITHUB_REPOSITORY"]
    token = token or os.environ["GITHUB_TOKEN"]
    return repo, token


def _get_or_create_release(c: httpx.Client, repo: str) -> dict:
    r = c.get(f"{_API}/repos/{repo}/releases/tags/{RELEASE_TAG}")
    if r.status_code == 200:
        return r.json()
    if r.status_code != 404:
        raise AssetError(f"get release -> {r.status_code}: {r.text[:300]}")
    r = c.post(f"{_API}/repos/{repo}/releases", json={
        "tag_name": RELEASE_TAG, "name": "video assets — transient",
        "body": "Auto-managed by Phase 2C. Assets are deleted after publish.",
        "prerelease": True})
    if r.status_code not in (200, 201):
        raise AssetError(f"create release -> {r.status_code}: {r.text[:300]}")
    return r.json()


def upload_release_asset(mp4: Path, name: str, *,
                         repo: str | None = None, token: str | None = None) -> str:
    repo, token = _repo_token(repo, token)
    mp4 = Path(mp4)
    with _client(token) as c:
        rel = _get_or_create_release(c, repo)
        for a in rel.get("assets", []):
            if a["name"] == name:
                c.delete(f"{_API}/repos/{repo}/releases/assets/{a['id']}")
        up = c.post(
            f"{_UPLOADS}/repos/{repo}/releases/{rel['id']}/assets",
            params={"name": name},
            headers={"Content-Type": "video/mp4"},
            content=mp4.read_bytes())
        if up.status_code not in (200, 201):
            raise AssetError(f"upload asset -> {up.status_code}: {up.text[:300]}")
    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG}/{name}"


def delete_release_asset(name: str, *,
                         repo: str | None = None, token: str | None = None) -> bool:
    repo, token = _repo_token(repo, token)
    with _client(token) as c:
        r = c.get(f"{_API}/repos/{repo}/releases/tags/{RELEASE_TAG}")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        for a in r.json().get("assets", []):
            if a["name"] == name:
                d = c.delete(f"{_API}/repos/{repo}/releases/assets/{a['id']}")
                return d.status_code in (204, 200)
    return False
