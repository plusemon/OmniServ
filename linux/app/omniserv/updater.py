"""Self-updater — polls GitHub releases for new versions, compares to
the running version, and (on request) downloads the .deb and installs it via pkexec apt.
Mirrors the Windows/Mac updaters, including the ≤1-call-per-30-min throttle for automatic checks.
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

from . import __version__


def _is_github_host(url: str) -> bool:
    """Only ever download/install assets served from GitHub's own hosts."""
    host = (urlparse(url).hostname or "").lower()
    return host == "github.com" or host.endswith(".githubusercontent.com")


REPO = "plusemon/OmniServ"
THROTTLE_FILE = os.path.expanduser("~/.omniserv/run/update-check.txt")
THROTTLE_SECONDS = 30 * 60


def _tag_to_ver(tag: str) -> str:
    t = tag.strip()
    if t.startswith("linux-v"):
        return t[len("linux-v"):]
    if t.startswith("linux-"):
        return t[len("linux-"):]
    if t.startswith("v") or t.startswith("V"):
        return t[1:]
    return t


def _ver_tuple(v: str) -> tuple:
    out = []
    for part in v.strip().split("."):
        num = "".join(c for c in part if c.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _ver_tuple(remote) > _ver_tuple(local)


def throttle_due(seconds: int = THROTTLE_SECONDS) -> bool:
    try:
        return (time.time() - os.path.getmtime(THROTTLE_FILE)) >= seconds
    except OSError:
        return True


def stamp_throttle() -> None:
    try:
        os.makedirs(os.path.dirname(THROTTLE_FILE), exist_ok=True)
        with open(THROTTLE_FILE, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def latest_release() -> tuple[dict | None, str | None]:
    """Resolve the latest release → (release_dict, error_message).
    Queries the GitHub API first; falls back to the releases/latest web redirect
    if unauthenticated rate-limiting (HTTP 403) occurs.
    """
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
    data = None
    api_err = None
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "OmniServ-Linux"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        api_err = str(e)
        data = None

    if isinstance(data, list):
        best = None
        for rel in data:
            if rel.get("draft"):
                continue
            tag = rel.get("tag_name", "")
            # Skip explicit other-platform tags without linux deb assets
            if (tag.startswith("win-") or tag.startswith("mac-") or tag.startswith("darwin-")) and not any(
                a.get("name", "").endswith(".deb") for a in rel.get("assets", [])
            ):
                continue
            ver = _tag_to_ver(tag)
            deb = next((a["browser_download_url"] for a in rel.get("assets", [])
                        if a.get("name", "").endswith(".deb")
                        and _is_github_host(a.get("browser_download_url", ""))), None)
            if not deb and tag:
                deb = f"https://github.com/{REPO}/releases/download/{tag}/omniserv_{ver}_all.deb"
            cand = {"version": ver, "tag": tag, "deb_url": deb, "notes": rel.get("body", "")}
            if best is None or is_newer(ver, best["version"]):
                best = cand
        if best:
            return best, None

    # Fallback to releases/latest web redirect (avoids GitHub API 60 req/hr rate limit)
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(f"https://github.com/{REPO}/releases/latest", headers={"User-Agent": "OmniServ-Linux"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            final_url = r.geturl()
        if "/tag/" in final_url:
            tag = final_url.split("/tag/")[-1].split("/")[0].split("?")[0]
            ver = _tag_to_ver(tag)
            deb_url = f"https://github.com/{REPO}/releases/download/{tag}/omniserv_{ver}_all.deb"
            return {"version": ver, "tag": tag, "deb_url": deb_url, "notes": ""}, None
    except Exception as e:
        return None, api_err or f"Could not reach GitHub: {e}"

    return None, api_err or "No releases found."


def check(force: bool = False, local_ver: str = __version__) -> tuple[dict | None, str | None]:
    """Return (update_dict, error_msg).
    - If newer release exists: (rel_dict, None)
    - If up to date: (None, None)
    - If error: (None, error_message)
    Honours the throttle unless force=True (a manual 'Check now').
    """
    if not force and not throttle_due():
        return None, None
    stamp_throttle()
    rel, err = latest_release()
    if rel and is_newer(rel["version"], local_ver) and rel.get("deb_url"):
        return rel, None
    if err:
        return None, err
    return None, None


def download_and_install(deb_url: str, on_log=lambda s: None) -> tuple[bool, str]:
    """Download the .deb to a temp file and install it with pkexec apt (graphical sudo)."""
    if not _is_github_host(deb_url):
        return False, "Refusing to install: update is not hosted on GitHub."
    try:
        on_log("Downloading update…")
        ctx = ssl.create_default_context()
        req = urllib.request.Request(deb_url, headers={"User-Agent": "OmniServ-Linux"})
        fd, path = tempfile.mkstemp(suffix=".deb", prefix="omniserv-")
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r, os.fdopen(fd, "wb") as f:
            f.write(r.read())
        on_log("Installing (you may be asked for your password)…")
        # pkexec gives a graphical prompt. Install via `dpkg -i` (upgrades in place) then
        # `apt-get -f install` to pull any new deps — NOT `apt/apt-get install ./file.deb`,
        # which fails on apt 2.9+ (Ubuntu 25.04+) with "Unsupported file … given on commandline".
        # Pass the path as $1 so no shell-quoting of the temp path is needed.
        p = subprocess.run(
            ["pkexec", "sh", "-c", 'dpkg -i "$1"; apt-get -f install -y', "sh", path],
            capture_output=True, text=True)
        os.unlink(path) if os.path.exists(path) else None
        if p.returncode == 0:
            return True, "Update installed — restart OmniServ to use the new version."
        return False, (p.stderr or p.stdout or "Install failed.").strip()[:300]
    except Exception as e:  # noqa: BLE001
        return False, str(e)
