#!/usr/bin/env python3
"""
Agent CLI - Connects to an LLM and answers questions using tools.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer', 'source', and 'tool_calls' fields to stdout.
    All debug/progress output goes to stderr.
"""

# Set UTF-8 encoding for stdout/stderr before any I/O
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Configuration from .env files."""

    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).parent / ".env.agent.secret",
            Path(__file__).parent / ".env.docker.secret",
        ],
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env variables we don't need
    )

    # LLM configuration
    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"

    # Backend API configuration
    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"


SYSTEM_PROMPT = """You are a documentation and system assistant for a software engineering course.
Answer questions using the project wiki, source code, and the live backend API.

Available tools:
- list_files: List files and directories in a given path
- read_file: Read the contents of a specific file  
- query_api: Call the deployed backend LMS API for data queries

Tool selection:
- Wiki/documentation questions тЖТ list_files, then read_file
- Source code questions (framework, ports, bugs) тЖТ list_files, then read_file  
- Data questions (counts, scores, analytics) тЖТ query_api
- API errors тЖТ query_api, then read_file to find the bug

Rules:
- Read ALL relevant files before answering
- Provide COMPLETE answers in your FIRST text response after reading files
- Include source references (wiki/file.md#section or path/file.py)
- Never say 'let me read X' or 'I'll continue' - provide the full answer immediately
- For router questions: read items.py, learners.py, interactions.py, analytics.py, pipeline.py, then summarize all five
- Respond in English only
- CRITICAL: After reading 4-5 files, you MUST STOP and provide your complete final answer
- For tracing questions (docker, request lifecycle): read docker-compose.yml, Caddyfile, Dockerfile, main.py (max 4 files), then provide complete trace

Example of a complete answer after reading files:
"Based on the configuration files, here is the complete request journey:
1. Browser sends request to Caddy reverse proxy
2. Caddy forwards to FastAPI backend
3. FastAPI authenticates and routes to appropriate handler
4. Handler queries PostgreSQL database
5. Response flows back through the same path
Source: docker-compose.yml, caddy/Caddyfile, backend/app/main.py"

IMPORTANT: Your answer must start with the actual content, NOT with "Let me..." or "I'll..." or "Now I...". Start directly with the answer.
"""


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


def tool_query_api(
    method: str,
    path: str,
    body: str | None = None,
    settings: AgentSettings | None = None,
    include_auth: bool = True,
) -> str:
    """Call the backend LMS API with authentication.

    Security: only accesses the configured backend URL.
    """
    if settings is None:
        return "Error: Settings not provided"

    api_key = settings.lms_api_key
    base_url = settings.agent_api_base_url.rstrip("/")

    if not api_key and include_auth:
        return "Error: LMS_API_KEY not configured"

    url = f"{base_url}{path}"

    try:
        with httpx.Client(timeout=30.0) as client:
            headers = {"Content-Type": "application/json"}
            if include_auth and api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data: dict[str, Any] = json.loads(body) if body else {}
                response = client.post(url, json=data, headers=headers)
            elif method.upper() == "PUT":
                data: dict[str, Any] = json.loads(body) if body else {}
                response = client.put(url, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method: {method}"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result, indent=2)

    except httpx.TimeoutException:
        return "Error: API request timed out"
    except httpx.RequestError as e:
        return f"Error: Failed to connect to API: {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON body: {e}"
    except Exception as e:
        return f"Error: {e}"


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository (source code, documentation, config files)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., wiki/git.md, backend/app/main.py)",
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
                        "description": "Relative directory path from project root (e.g., wiki, backend/app/routers)",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the deployed backend LMS API for data queries. Use for: item counts, scores, analytics, checking API responses, reproducing errors. Do NOT use for reading source code files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., /items/, /analytics/completion-rate)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body for POST/PUT requests",
                    },
                    "include_auth": {
                        "type": "boolean",
                        "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access.",
                        "default": True,
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]


def execute_tool(
    tool_name: str, args: dict[str, Any], project_root: Path, settings: AgentSettings
) -> str:
    """Execute a tool and return its result."""
    if tool_name == "read_file":
        path = args.get("path", "")
        return tool_read_file(path, project_root)
    elif tool_name == "list_files":
        path = args.get("path", "")
        return tool_list_files(path, project_root)
    elif tool_name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        include_auth = args.get("include_auth", True)
        return tool_query_api(method, path, body, settings, include_auth)
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
            "max_tokens": 16384,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]


def extract_source_from_answer(answer: str) -> str:
    """Try to extract a source reference from the answer.

    Looks for patterns like wiki/filename.md, backend/app/file.py, or /api/endpoint
    """
    import re

    # Look for wiki file references with optional anchor
    match = re.search(r"(wiki/[\w-]+\.md(?:#[\w-]+)?)", answer)
    if match:
        return match.group(1)

    # Look for backend file references
    match = re.search(r"(backend/[\w/.]+\.py)", answer)
    if match:
        return match.group(1)

    # Look for API endpoint references
    match = re.search(r"(/[\w/-]+/[\w/-]+)", answer)
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
    max_iterations = 12
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

                print(f"  Executing tool: {tool_name}", file=sys.stderr)

                # Execute tool
                result = execute_tool(tool_name, tool_args, project_root, settings)

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

            # Continue loop - LLM will decide next action
            continue

        # No tool calls - we have a final answer
        answer = response.get("content") or ""
        state.answer = answer

        # Try to extract source from answer
        state.source = extract_source_from_answer(answer)

        # If no source found in answer, try to infer from last tool call
        if not state.source and state.tool_calls:
            last_call = state.tool_calls[-1]
            if last_call.tool == "read_file":
                path = last_call.args.get("path", "")
                if path.startswith("wiki/") or path.startswith("backend/"):
                    state.source = path
            elif last_call.tool == "query_api":
                path = last_call.args.get("path", "")
                state.source = path

        # Print without emoji that may cause encoding issues on Windows
        source_display = state.source or "(not specified)"
        print(
            f"Final answer received. Source: {source_display}",
            file=sys.stderr,
        )
        break
    else:
        # Max iterations reached
        print("Max iterations reached. Using best available answer.", file=sys.stderr)
        if not state.answer and messages:
            # Try to get answer from last assistant message
            for msg in reversed(messages):
                content = msg.get("content")
                if msg.get("role") == "assistant" and content:
                    state.answer = content
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
        print(f"API Base: {settings.agent_api_base_url}", file=sys.stderr)

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
