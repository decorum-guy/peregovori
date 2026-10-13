#!/usr/bin/env python3
"""Upload private experiment archives as GitHub Release assets WITHOUT git push.

The owner creates a SEPARATE PRIVATE repository with a README first.
One-time setup stores only repo + PAT in ~/.config/peregovori/github_artifacts.json
(mode 0600), never in the public source repo, command-line args, or logs.
No non-stdlib dependencies. On failed upload, archives stay on the VM disk.
"""
import argparse
import getpass
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "peregovori" / "github_artifacts.json"
API = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request(url, token, *, method="GET", payload=None, content_type="application/vnd.github+json", timeout=120):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "peregovori-private-artifacts/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as e:
        # The HTTP body is not printed: error messages can contain sensitive paths.
        raise RuntimeError(f"GitHub API HTTP {e.code} during {method} request") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"GitHub API network failure ({type(e.reason).__name__})") from None


def config():
    if not CONFIG.is_file() or (CONFIG.stat().st_mode & 0o077):
        raise RuntimeError("Missing/insecure token config. Run configure; chmod 600 required")
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not REPO_RE.fullmatch(c.get("repo", "")) or not c.get("token", ""):
        raise RuntimeError("Invalid private artifact repository/token config")
    return c


def check(c):
    info = request(f"{API}/repos/{c['repo']}", c["token"])
    if info.get("full_name", "").lower() != c["repo"].lower():
        raise RuntimeError("GitHub repository name mismatch")
    if not info.get("private", False):
        raise RuntimeError("REFUSING upload: repository is PUBLIC. Use a SEPARATE PRIVATE repo")
    if "permissions" in info and not info["permissions"].get("push", False):
        raise RuntimeError("PAT does not have write access to private repo")
    print(f"PRIVATE repo verified: {info['full_name']}; credential remains outside Git", flush=True)


def get_or_create_release(c, tag):
    repo, token = c["repo"], c["token"]
    url = f"{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}"
    try:
        return request(url, token)
    except RuntimeError as e:
        if "HTTP 404" not in str(e):
            raise
    payload = json.dumps({
        "tag_name": tag,
        "target_commitish": "main",
        "name": tag,
        "body": "Automated PRIVATE QLoRA experiment backup. Not part of public TRAIN repository.",
        "draft": False,
        "prerelease": True,
    }).encode("utf-8")
    try:
        return request(f"{API}/repos/{repo}/releases", token, method="POST",
                       payload=payload, content_type="application/json")
    except RuntimeError:
        # If a previous attempt created the release, retry lookup before failing.
        return request(url, token)


def upload_one(c, release, path):
    name = path.name
    existing = {asset["name"]: asset for asset in release.get("assets", [])}
    if name in existing:
        asset = existing[name]
        actual_hash = asset.get("digest")
        expected_hash = "sha256:" + digest(path)
        if asset.get("state") == "uploaded" and asset.get("size") == path.stat().st_size and (
            not actual_hash or actual_hash == expected_hash
        ):
            print(f"ALREADY PRESENT {name}: size verified"
                  + (", digest verified" if actual_hash else ", digest unavailable"), flush=True)
            return
        raise RuntimeError(f"Existing release asset {name} conflicts; not overwriting")
    if path.stat().st_size >= 2 * 1024**3:
        raise RuntimeError(f"Asset exceeds GitHub 2GiB limit: {name}")
    raw_upload_url = release["upload_url"].split("{", 1)[0]
    url = raw_upload_url + "?" + urllib.parse.urlencode({"name": name})
    # Largest artifact in this experiment ~160 MiB; fits within 32 GiB VM RAM.
    # Avoid printing bearer token or including it in argv, shell history, or logs.
    data = path.read_bytes()
    asset = request(url, c["token"], method="POST", payload=data,
                    content_type="application/octet-stream", timeout=600)
    if asset.get("size") != len(data) or asset.get("state") != "uploaded":
        raise RuntimeError(f"GitHub reported incomplete upload: {name}")
    sha = "sha256:" + hashlib.sha256(data).hexdigest()
    if asset.get("digest") and asset["digest"] != sha:
        raise RuntimeError(f"GitHub digest mismatch: {name}")
    print(f"UPLOADED {name}: {len(data)} bytes, SHA256={sha.split(':')[1]}", flush=True)


def main():
    cli = argparse.ArgumentParser()
    sub = cli.add_subparsers(dest="action", required=True)
    c = sub.add_parser("configure", help="one-time setup, prompts for token without echo")
    c.add_argument("--repo", required=True, help="SEPARATE PRIVATE owner/repository")
    sub.add_parser("check", help="refuse public repo and test auth (before training)")
    u = sub.add_parser("upload", help="upload archives/checksums as private release assets")
    u.add_argument("--tag", required=True)
    u.add_argument("--file", action="append", required=True)
    args = cli.parse_args()
    if args.action == "configure":
        if not REPO_RE.fullmatch(args.repo):
            cli.error("repository must have owner/name format")
        token = getpass.getpass("GitHub fine-grained PAT for private artifacts (hidden): ").strip()
        if not token:
            cli.error("Token cannot be empty")
        candidate = {"repo": args.repo, "token": token}
        check(candidate)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(CONFIG.parent, 0o700)
        fd = os.open(str(CONFIG), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(candidate, fh)
            fh.write("\n")
        os.chmod(CONFIG, 0o600)
        print("Saved private token config with permissions 0600", flush=True)
    elif args.action == "check":
        check(config())
    else:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", args.tag):
            cli.error("Invalid GitHub release tag")
        files = [Path(name).resolve() for name in args.file]
        if any(not f.is_file() for f in files):
            raise SystemExit("STOP: one or more required artifact files missing")
        if len({f.name for f in files}) != len(files):
            raise SystemExit("STOP: duplicate artifact basenames")
        c = config()
        check(c)
        release = get_or_create_release(c, args.tag)
        for path in files:
            # Refresh release assets after each upload to allow safe retry.
            release = request(f"{API}/repos/{c['repo']}/releases/tags/{args.tag}", c["token"])
            upload_one(c, release, path)
        latest = request(f"{API}/repos/{c['repo']}/releases/tags/{args.tag}", c["token"])
        names = {a["name"] for a in latest.get("assets", []) if a.get("state") == "uploaded"}
        if not all(f.name in names for f in files):
            raise RuntimeError("Release verification failed: missing uploaded asset")
        print("ALL PRIVATE ARTIFACTS UPLOADED:", latest.get("html_url"), flush=True)


if __name__ == "__main__":
    main()
