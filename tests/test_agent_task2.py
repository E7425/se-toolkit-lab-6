"""Regression tests for agent.py CLI - Task 2 (Documentation Agent)."""

import json
import subprocess
import sys
from pathlib import Path


def test_merge_conflict_question() -> None:
    """Test that agent uses read_file tool and returns wiki source for merge conflict question."""
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=120,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    output = json.loads(result.stdout)

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"

    assert "source" in output, "Missing 'source' field in output"
    assert isinstance(output["source"], str), "'source' must be a string"
    assert "wiki/" in output["source"], "Source should reference wiki/ directory"

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"

    # Check that read_file was used
    tools_used = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tools_used, "Expected read_file tool to be used"

    # Check source references git-workflow or git-vscode (merge conflict docs)
    source = output["source"].lower()
    assert "git" in source, "Source should reference git documentation"


def test_wiki_listing_question() -> None:
    """Test that agent uses list_files tool for wiki listing question."""
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "What files are in the wiki?"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=120,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    output = json.loads(result.stdout)

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"

    # Check that list_files was used
    tools_used = [tc.get("tool") for tc in output["tool_calls"]]
    assert "list_files" in tools_used, "Expected list_files tool to be used"
