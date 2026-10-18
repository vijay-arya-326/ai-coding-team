"""Tests for the inspect/read tools: path validation, inputs, and file ops.

A temporary directory is made the active workspace so tools resolve paths
against it without touching the project or the database.
"""

import os

import pytest

from app import workspace as ws_mod
from app.tools import (
    get_project_structure,
    list_files,
    read_file,
    resolve_project_path,
    search_code,
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
