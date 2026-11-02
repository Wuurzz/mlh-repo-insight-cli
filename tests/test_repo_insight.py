import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
import pytest
from repo_insight import GitHubError, analyze_repositories, fetch_repositories, main, render_report

def repo(name, language=None, stars=0, fork=False):
    return {"name": name, "language": language, "stargazers_count": stars, "fork": fork, "html_url": f"https://github.com/example/{name}"}

def test_analysis_excludes_forks_by_default():
    result = analyze_repositories([repo("app", "Python", 3), repo("fork", "Rust", 100, True)])
    assert result["repository_count"] == 1
    assert result["total_stars"] == 3
    assert result["languages"] == {"Python": 1}

def test_forks_can_be_included():
    result = analyze_repositories([repo("app", "Python"), repo("fork", "Rust", fork=True)], include_forks=True)
    assert result["repository_count"] == 2

def test_stars_are_ranked_with_stable_name_tiebreak():
    result = analyze_repositories([repo("z", stars=2), repo("a", stars=2), repo("top", stars=7)])
    assert [r["name"] for r in result["top_repositories"]] == ["top", "a", "z"]

def test_empty_results_render_cleanly():
    result = analyze_repositories([])
    assert "None" in render_report("someone", result)
    assert result["total_stars"] == 0

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return BytesIO(json.dumps(self.payload).encode())
    def __exit__(self, *_):
        return False

def test_fetch_parses_successful_api_response():
    with patch("repo_insight.urlopen", return_value=FakeResponse([repo("test", "Python")])):
        result = fetch_repositories("user")
    assert result[0]["name"] == "test"

def test_fetch_handles_unknown_users():
    error = HTTPError("https://api.github.com", 404, "Not Found", None, None)
    with patch("repo_insight.urlopen", side_effect=error):
        with pytest.raises(GitHubError, match="not found"):
            fetch_repositories("missing")

def test_cli_outputs_json(capsys):
    with patch("repo_insight.fetch_repositories", return_value=[repo("hello", "Python", 4)]):
        assert main(["someone", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_stars"] == 4

def test_cli_failure_has_nonzero_exit(capsys):
    with patch("repo_insight.fetch_repositories", side_effect=GitHubError("API failed")):
        assert main(["someone"]) == 1
    assert "API failed" in capsys.readouterr().err
