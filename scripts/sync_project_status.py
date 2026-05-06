#!/usr/bin/env python3
"""Fetch VCSE .velarium/status.json and enrich with latest commit; write data/projects/."""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PROJECTS_DIR = REPO_ROOT / "data" / "projects"
DATA_DIR = REPO_ROOT / "data"

VCSE_STATUS_URL = "https://raw.githubusercontent.com/VRM-AI/vcse/main/.velarium/status.json"
VCSE_COMMITS_URL = "https://api.github.com/repos/VRM-AI/vcse/commits/main"

REQUIRED_FIELDS = [
    "current_version", "latest_release_tag", "latest_release_url",
    "latest_validated_release", "validation", "capabilities", "roadmap",
    "immediate_focus",
]


def fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "velariumai-site/1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_vcse_status():
    try:
        return fetch_json(VCSE_STATUS_URL)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        sys.exit(f"ERROR: failed to fetch VCSE status from {VCSE_STATUS_URL}: {exc}")


def fetch_latest_commit():
    try:
        data = fetch_json(VCSE_COMMITS_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "velariumai-site/1",
        })
        sha = data["sha"]
        message = data["commit"]["message"].splitlines()[0]
        committed_at = data["commit"]["committer"]["date"]
        url = data["html_url"]
        return {"sha": sha, "short_sha": sha[:7], "message": message, "url": url, "committed_at": committed_at}
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        print(f"WARNING: GitHub API unavailable ({exc}); latest_commit will be absent.", file=sys.stderr)
        return None


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text() == content:
        return False
    path.write_text(content)
    return True


def main():
    status = fetch_vcse_status()

    for field in REQUIRED_FIELDS:
        if field not in status:
            sys.exit(f"ERROR: .velarium/status.json missing required field: {field}")

    latest_commit = fetch_latest_commit()

    project = {
        "project_id": status.get("project_id", "vcse"),
        "project_name": status.get("project_name", "VCSE"),
        "project_full_name": status.get("project_full_name", ""),
        "organization": status.get("organization", "VRM-AI"),
        "repo": status.get("repo", "VRM-AI/vcse"),
        "public_url": status.get("public_url", "https://github.com/VRM-AI/vcse"),
        "current_version": status["current_version"],
        "latest_release_tag": status["latest_release_tag"],
        "latest_release_url": status["latest_release_url"],
        "latest_validated_release": status["latest_validated_release"],
        "validation": status["validation"],
        "capabilities": status["capabilities"],
        "roadmap": status["roadmap"],
        "immediate_focus": status["immediate_focus"],
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if latest_commit:
        project["latest_commit"] = latest_commit

    DATA_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    vcse_json = json.dumps(project, indent=2) + "\n"
    index_json = json.dumps([project], indent=2) + "\n"

    changed_vcse = write_if_changed(DATA_PROJECTS_DIR / "vcse.json", vcse_json)
    changed_index = write_if_changed(DATA_DIR / "projects.json", index_json)

    if changed_vcse:
        print(f"Updated: {DATA_PROJECTS_DIR / 'vcse.json'}")
    if changed_index:
        print(f"Updated: {DATA_DIR / 'projects.json'}")
    if not changed_vcse and not changed_index:
        print("No changes.")

    commit_info = (
        f"{latest_commit['short_sha']} — {latest_commit['message']}"
        if latest_commit else "(commit unavailable)"
    )
    print(f"VCSE {status['current_version']} | Latest commit: {commit_info}")


if __name__ == "__main__":
    main()
