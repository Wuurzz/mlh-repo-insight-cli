"""Analyze public GitHub repositories without third-party dependencies."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"

class GitHubError(Exception):
    """Raised when data cannot be retrieved from GitHub."""

def fetch_repositories(username: str, *, max_pages: int = 3) -> list[dict[str, Any]]:
    """Fetch up to max_pages of a user's public repositories (100 per page)."""
    repositories: list[dict[str, Any]] = []
    safe_username = quote(username, safe="")
    for page in range(1, max_pages + 1):
        url = f"{API_ROOT}/users/{safe_username}/repos?per_page=100&page={page}&sort=updated"
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "repo-insight-cli"})
        try:
            with urlopen(request, timeout=12) as response:
                batch = json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                raise GitHubError(f"GitHub user {username!r} was not found.") from exc
            if exc.code == 403:
                raise GitHubError("GitHub API access was denied or rate-limited. Try again later.") from exc
            raise GitHubError(f"GitHub returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise GitHubError(f"Could not retrieve GitHub data: {exc}") from exc
        if not isinstance(batch, list):
            raise GitHubError("GitHub returned an unexpected response format.")
        repositories.extend(batch)
        if len(batch) < 100:
            break
    return repositories

def analyze_repositories(repositories: list[dict[str, Any]], *, include_forks: bool = False) -> dict[str, Any]:
    """Produce a summary from public repository metadata."""
    selected = [repo for repo in repositories if include_forks or not repo.get("fork", False)]
    languages = Counter(repo["language"] for repo in selected if repo.get("language"))
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in selected)
    ranked = sorted(selected, key=lambda repo: (-int(repo.get("stargazers_count") or 0), repo.get("name", "")))
    return {
        "repository_count": len(selected),
        "total_stars": stars,
        "languages": dict(languages.most_common()),
        "top_repositories": [
            {"name": repo.get("name", "(unnamed)"), "stars": int(repo.get("stargazers_count") or 0), "url": repo.get("html_url", "")}
            for repo in ranked[:5]
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

def render_report(username: str, summary: dict[str, Any]) -> str:
    """Format a human-readable analysis."""
    languages = ", ".join(f"{language} ({count})" for language, count in summary["languages"].items()) or "No languages reported"
    lines = [
        f"GitHub overview for {username}",
        f"Repositories: {summary['repository_count']}",
        f"Total stars: {summary['total_stars']}",
        f"Languages: {languages}",
        "Top repositories:",
    ]
    if not summary["top_repositories"]:
        lines.append("  None")
    else:
        for repo in summary["top_repositories"]:
            lines.append(f"  {repo['name']}: {repo['stars']} stars — {repo['url']}")
    return "\n".join(lines)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze GitHub public repositories")
    parser.add_argument("username", help="GitHub username to analyze")
    parser.add_argument("--include-forks", action="store_true", help="Include forked repositories")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a text report")
    args = parser.parse_args(argv)
    try:
        repositories = fetch_repositories(args.username)
        result = analyze_repositories(repositories, include_forks=args.include_forks)
    except GitHubError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"username": args.username, **result}, indent=2))
    else:
        print(render_report(args.username, result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
