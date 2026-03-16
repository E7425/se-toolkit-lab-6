"""Regression tests for agent.py CLI - Task 3 (System Agent)."""

import json
import subprocess
import sys
from pathlib import Path


def test_framework_question() -> None:
    """Test that agent uses read_file tool for framework question."""
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [
            sys.executable,
            str(agent_path),
            "What Python web framework does the backend use?",
        ],
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

    # Check that read_file was used
    tools_used = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tools_used, "Expected read_file tool to be used"

    # Check answer mentions FastAPI
    assert "fastapi" in output["answer"].lower(), "Answer should mention FastAPI"


def test_item_count_question() -> None:
    """Test that agent uses query_api tool for item count question."""
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "How many items are in the database?"],
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

    # Check that query_api was used
    tools_used = [tc.get("tool") for tc in output["tool_calls"]]
    assert "query_api" in tools_used, "Expected query_api tool to be used"

    # Check answer contains a number
    import re

    numbers = re.findall(r"\d+", output["answer"])
    assert len(numbers) > 0, "Answer should contain a number"
