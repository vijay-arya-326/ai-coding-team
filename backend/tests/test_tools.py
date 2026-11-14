"""Tests for the inspect/read tools: path validation, inputs, and file ops.

A temporary directory is made the active workspace so tools resolve paths
against it without touching the project or the database.
"""

import os
import httpx

import pytest

from app import workspace as ws_mod
from app.tools import (
    get_project_structure,
    list_files,
    read_file,
    resolve_project_path,
    search_code,
    search_web,
    fetch_rendered_page,
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "README.md").write_text("# Demo\nhello world\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("hello world junk\n")
    ws = ws_mod.make_workspace(ws_id="test", name="test", root_path=str(tmp_path))
    ws_mod.set_current(ws)
    yield tmp_path
    ws_mod.set_current(None)


def test_resolve_rejects_traversal(workspace):
    with pytest.raises(ValueError):
        resolve_project_path("../outside.txt")


def test_resolve_allows_relative_inside(workspace):
    resolved = resolve_project_path("pkg/mod.py")
    assert resolved == os.path.join(str(workspace), "pkg", "mod.py")


def test_read_file_returns_contents(workspace):
    out = read_file.invoke({"path": "pkg/mod.py"})
    assert "def add" in out
    assert "(2 lines shown from 1)" in out


def test_read_file_window(workspace):
    out = read_file.invoke({"path": "pkg/mod.py", "start_line": 2, "max_lines": 1})
    assert "return a + b" in out
    assert "def add" not in out


def test_read_file_rejects_traversal(workspace):
    out = read_file.invoke({"path": "../../etc/hosts"})
    assert out.startswith("ERROR:")


def test_read_file_missing(workspace):
    out = read_file.invoke({"path": "nope.txt"})
    assert out.startswith("ERROR:")


def test_list_files_shows_dirs_with_slash(workspace):
    out = list_files.invoke({"path": "."})
    assert "pkg/" in out
    assert "README.md" in out


def test_list_files_pattern(workspace):
    out = list_files.invoke({"path": "pkg", "pattern": "*.py"})
    assert "mod.py" in out
    assert "README.md" not in out


def test_list_files_not_a_dir(workspace):
    out = list_files.invoke({"path": "does/not/exist"})
    assert out.startswith("ERROR:")


def test_search_code_finds_match(workspace):
    out = search_code.invoke({"query": "return a + b"})
    assert "pkg/mod.py:2:" in out


def test_search_code_skips_ignored_dirs(workspace):
    out = search_code.invoke({"query": "hello world"})
    assert "README.md" in out
    assert "node_modules" not in out


def test_search_code_pattern_filter(workspace):
    out = search_code.invoke({"query": "hello", "pattern": "*.md"})
    assert "README.md" in out


def test_search_code_empty_query(workspace):
    out = search_code.invoke({"query": ""})
    assert out.startswith("ERROR:")


def test_project_structure_lists_tree(workspace):
    out = get_project_structure.invoke({"path": "."})
    assert "pkg/" in out
    assert "mod.py" in out
    assert "node_modules" not in out


def test_search_web_returns_capped_validated_results(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"title": "Result one", "url": "https://example.com/one", "content": "First result."},
                    {"title": "Result two", "url": "https://example.com/two", "content": "Second result."},
                ]
            }

    monkeypatch.setattr("app.tools.httpx.get", lambda *args, **kwargs: Response())
    monkeypatch.setattr("app.tools._await_approval", lambda payload: {"approved": True})
    out = search_web.invoke({"query": "example", "max_results": 1})
    assert "Research summary for: example" in out
    assert "[1]" in out
    assert "Result one" in out
    assert "Result two" not in out
    assert "https://example.com/one" in out


def test_search_web_uses_obscura_when_searxng_json_fails(monkeypatch):
    class Result:
        returncode = 0
        stdout = "Rendered SearXNG result"
        stderr = ""

    def fail_request(*args, **kwargs):
        raise httpx.HTTPError("json unavailable")

    monkeypatch.setattr("app.tools.httpx.get", fail_request)
    monkeypatch.setattr("app.tools._await_approval", lambda payload: {"approved": True})
    monkeypatch.setattr("app.tools.subprocess.run", lambda *args, **kwargs: Result())
    out = search_web.invoke({"query": "example"})
    assert "SearXNG rendered via Obscura" in out
    assert "Rendered SearXNG result" in out


def test_search_web_stops_when_rejected(monkeypatch):
    monkeypatch.setattr("app.tools._await_approval", lambda payload: {"approved": False})
    out = search_web.invoke({"query": "example"})
    assert out.startswith("User rejected this web search")


def test_fetch_rendered_page_uses_obscura_and_caps_output(monkeypatch):
    class Result:
        returncode = 0
        stdout = "Rendered page text"
        stderr = ""

    monkeypatch.setattr("app.tools._validate_public_web_url", lambda url: None)
    monkeypatch.setattr("app.tools.subprocess.run", lambda *args, **kwargs: Result())
    out = fetch_rendered_page.invoke({"url": "https://example.com"})
    assert "Rendered page text" in out


def test_fetch_rendered_page_rejects_private_hosts():
    out = fetch_rendered_page.invoke({"url": "http://127.0.0.1:3000"})
    assert out.startswith("ERROR:")
