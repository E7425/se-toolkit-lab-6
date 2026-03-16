#!/usr/bin/env python3
"""
Agent CLI - Connects to an LLM and answers questions using tools.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer', 'source', and 'tool_calls' fields to stdout.
    All debug/progress output goes to stderr.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """LLM configuration from .env.agent.secret."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env.agent.secret",
        env_file_encoding="utf-8",
    )

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"


SYSTEM_PROMPT = """You are a documentation assistant for a software engineering course.
Answer questions using the project wiki files.

Available tools:
- list_files: List files and directories in a given path
- read_file: Read the contents of a specific file

Process:
1. Use list_files to discover relevant wiki files
2. Use read_file to read the content of specific files
3. Answer the question based on the file contents
4. Always include a source reference in the format: wiki/filename.md#section-anchor

Rules:
- Only access files within the project directory
- Prefer wiki/ directory for documentation questions
- Include specific section anchors when referencing content
- If you cannot find the answer, say so honestly"""


@dataclass
class ToolCallOutput:
    """Record of a tool call and its result."""

    tool: str
    args: dict[str, Any]
    result: str


@dataclass
class AgentState:
    """State of the agentic loop."""

    tool_calls: list[ToolCallOutput] = field(default_factory=list)  # type: ignore[misc]
    answer: str = ""
    source: str = ""


def safe_resolve_path(path: str, project_root: Path) -> Path | None:
    """Resolve path and ensure it's within project directory.

    Returns None if path is outside project directory (security violation).
    """
    # Remove leading slashes to make path relative
    clean_path = path.lstrip("/").lstrip("\\")
    resolved = (project_root / clean_path).resolve()

    # Check if resolved path is within project root
    try:
        resolved.relative_to(project_root)
        return resolved
    except ValueError:
        return None  # Path is outside project directory


def tool_read_file(path: str, project_root: Path) -> str:
    """Read a file from the project repository.

    Security: prevents reading files outside project directory.
    """
    resolved = safe_resolve_path(path, project_root)
    if resolved is None:
        return "Error: Access denied - path is outside project directory"

    if not resolved.is_file():
        return f"Error: File not found: {path}"

    try:
        return resolved.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error: Cannot read file: {e}"


def tool_list_files(path: str, project_root: Path) -> str:
    """List files and directories at a given path.

    Security: prevents listing directories outside project directory.
    """
    resolved = safe_resolve_path(path, project_root)
    if resolved is None:
        return "Error: Access denied - path is outside project directory"

    if not resolved.is_dir():
        return f"Error: Directory not found: {path}"

    try:
        entries = sorted(resolved.iterdir())
        lines = [e.name for e in entries]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: Cannot list directory: {e}"


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
]


def execute_tool(tool_name: str, args: dict[str, Any], project_root: Path) -> str:
    """Execute a tool and return its result."""
    if tool_name == "read_file":
        path = args.get("path", "")
        return tool_read_file(path, project_root)
    elif tool_name == "list_files":
        path = args.get("path", "")
        return tool_list_files(path, project_root)
    else:
        return f"Error: Unknown tool: {tool_name}"


def create_llm_client(settings: AgentSettings) -> httpx.Client:
    """Create HTTP client for LLM API."""
    return httpx.Client(
        base_url=settings.llm_api_base,
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )


def call_llm_with_tools(
    client: httpx.Client,
    settings: AgentSettings,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call LLM API with tool support and return the response."""
    response = client.post(
        "/chat/completions",
        json={
            "model": settings.llm_model,
            "messages": messages,
            "tools": TOOLS_SCHEMA,
            "tool_choice": "auto",
            "temperature": 0.7,
            "max_tokens": 2048,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]


def extract_source_from_answer(answer: str) -> str:
    """Try to extract a source reference from the answer.

    Looks for patterns like wiki/filename.md or wiki/filename.md#section
    """
    import re

    # Look for wiki file references with optional anchor
    match = re.search(r"(wiki/[\w-]+\.md(?:#[\w-]+)?)", answer)
    if match:
        return match.group(1)

    # Look for just wiki file references
    match = re.search(r"(wiki/[\w-]+\.md)", answer)
    if match:
        return match.group(1)

    return ""


def run_agentic_loop(
    client: httpx.Client,
    settings: AgentSettings,
    question: str,
    project_root: Path,
) -> AgentState:
    """Run the agentic loop until we get an answer or hit max iterations."""
    max_iterations = 10
    state = AgentState()

    # Initialize messages with system prompt and user question
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    print(
        f"Starting agentic loop (max {max_iterations} iterations)...", file=sys.stderr
    )

    for iteration in range(max_iterations):
        print(f"Iteration {iteration + 1}/{max_iterations}", file=sys.stderr)

        # Call LLM
        response = call_llm_with_tools(client, settings, messages)

        # Check for tool calls
        tool_calls: list[dict[str, Any]] | None = response.get("tool_calls")

        if tool_calls:
            # Add assistant message with tool calls to history
            messages.append(response)

            # Execute each tool
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                tool_id = tc["id"]

                print(f"  Executing tool: {tool_name}({tool_args})", file=sys.stderr)

                # Execute tool
                result = execute_tool(tool_name, tool_args, project_root)

                # Record tool call
                state.tool_calls.append(
                    ToolCallOutput(tool=tool_name, args=tool_args, result=result)
                )

                # Add tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_id,
                    }
                )

                print(f"  Result: {result[:100]}...", file=sys.stderr)

            # Continue loop - LLM will decide next action
            continue

        # No tool calls - we have a final answer
        answer = response.get("content", "")
        state.answer = answer

        # Try to extract source from answer
        state.source = extract_source_from_answer(answer)

        # If no source found in answer, try to infer from last tool call
        if not state.source and state.tool_calls:
            last_call = state.tool_calls[-1]
            if last_call.tool == "read_file":
                path = last_call.args.get("path", "")
                if path.startswith("wiki/"):
                    state.source = path

        print(
            f"Final answer received. Source: {state.source or '(not specified)'}",
            file=sys.stderr,
        )
        break
    else:
        # Max iterations reached
        print("Max iterations reached. Using best available answer.", file=sys.stderr)
        if not state.answer and messages:
            # Try to get answer from last assistant message
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    state.answer = msg["content"]
                    state.source = extract_source_from_answer(state.answer)
                    break

    return state


def main() -> int:
    """Main entry point."""
    # Parse command-line argument
    if len(sys.argv) != 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        return 1

    question = sys.argv[1]
    project_root = Path(__file__).parent

    try:
        # Load settings
        settings = AgentSettings()  # type: ignore[call-arg]
        print(f"Using model: {settings.llm_model}", file=sys.stderr)

        # Create LLM client
        with create_llm_client(settings) as client:
            # Run agentic loop
            state = run_agentic_loop(client, settings, question, project_root)

        # Format output
        result: dict[str, Any] = {
            "answer": state.answer,
            "source": state.source,
            "tool_calls": [
                {"tool": tc.tool, "args": tc.args, "result": tc.result}
                for tc in state.tool_calls
            ],
        }

        # Output JSON to stdout
        print(json.dumps(result, ensure_ascii=False))
        print("Done.", file=sys.stderr)

        return 0

    except httpx.TimeoutException:
        print("Error: LLM request timed out (>60s)", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as e:
        print(f"Error: LLM API returned {e.response.status_code}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Error: Failed to connect to LLM: {e}", file=sys.stderr)
        return 1
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error: Unexpected LLM response format: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
