#!/usr/bin/env python3
import datetime
import json
import os
import urllib.error
import urllib.request

PROJECTS = {
    "pdv": {
        "repo": "VelariumAI/pdv",
        "name": "PDV",
        "url": "https://github.com/VelariumAI/pdv",
        "fallback_description": "PDV is a self-hosted download manager with a persistent queue, retry/backoff worker engine, REST API, and CLI.",
    },
    "alembic-cli": {
        "repo": "VelariumAI/alembic-cli",
        "name": "Alembic CLI",
        "url": "https://github.com/VelariumAI/alembic-cli",
        "fallback_description": "Project Alembic – Universal Transformer-to-SSM distillation with in-training CompreSSM compression (ICLR 2026).",
    },
    "go-webinspect": {
        "repo": "VelariumAI/go-webinspect",
        "name": "Go WebInspect",
        "url": "https://github.com/VelariumAI/go-webinspect",
        "fallback_description": "go-webinspect is a professional-grade, open-source framework written entirely in Go that provides a complete, high-powered suite of web inspection, traffic analysis, and reverse-engineering tools.",
    },
    "go-ddgs": {
        "repo": "VelariumAI/go-ddgs",
        "name": "Go DDGS",
        "url": "https://github.com/VelariumAI/go-ddgs",
        "fallback_description": "DuckDuckGoSearch in Go.",
    },
    "go-ddgs-stealth": {
        "repo": "VelariumAI/go-ddgs-stealth",
        "name": "Go DDGS Stealth",
        "url": "https://github.com/VelariumAI/go-ddgs-stealth",
        "fallback_description": "Advanced stealth web scraping framework for Go, extending go-ddgs with browser-level evasion, StealthyFetcher, and resilient anti-bot capabilities.",
    },
    "gorkbot": {
        "repo": "VelariumAI/gorkbot",
        "name": "Gorkbot",
        "url": "https://github.com/VelariumAI/gorkbot",
        "fallback_description": "Gorkbot is an AI-powered orchestration platform that unifies multiple large language models into a single terminal interface.",
    },
    "vcse": {
        "repo": "VRM-AI/vcse",
        "name": "VCSE",
        "url": "https://github.com/VRM-AI/vcse",
        "fallback_description": "VCSE (Verifier-Centered Symbolic Engine) is the verification and reasoning engine for Correctness Models (CMs).",
        "canonical_description": "VCSE (Verifier-Centered Symbolic Engine) is the verification and reasoning engine for Correctness Models (CMs).",
    },
}


def fetch_json(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_latest_release_tag(repo, token):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        data = fetch_json(url, token)
        return data.get("tag_name")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    projects_out = {}
    for key, cfg in PROJECTS.items():
        repo_data = fetch_json(f"https://api.github.com/repos/{cfg['repo']}", token)
        description = repo_data.get("description") or cfg["fallback_description"]
        if "canonical_description" in cfg:
            description = cfg["canonical_description"]

        projects_out[key] = {
            "repo": cfg["repo"],
            "name": cfg["name"],
            "url": cfg["url"],
            "description": description,
            "latest_release": get_latest_release_tag(cfg["repo"], token),
            "updated_at": repo_data.get("updated_at"),
        }

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "projects": projects_out,
    }

    with open("projects.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
        f.write("\n")


if __name__ == "__main__":
    main()
