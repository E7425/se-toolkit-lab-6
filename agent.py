#!/usr/bin/env python3
"""
Agent CLI - Connects to an LLM and answers questions.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer' and 'tool_calls' fields to stdout.
    All debug/progress output goes to stderr.
"""

import json
import sys
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


SYSTEM_PROMPT = """You are a helpful assistant. Answer the user's question concisely.
Respond with only the answer, no explanations."""


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


def call_lllm(client: httpx.Client, settings: AgentSettings, question: str) -> str:
    """Call LLM API and return the answer."""
    response = client.post(
        "/chat/completions",
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "temperature": 0.7,
            "max_tokens": 1024,
        },
    )
    response.raise_for_status()
    data = response.json()
    return str(data["choices"][0]["message"]["content"])


def main() -> int:
    """Main entry point."""
    # Parse command-line argument
    if len(sys.argv) != 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        return 1

    question = sys.argv[1]

    try:
        # Load settings
        settings = AgentSettings()  # type: ignore[call-arg]
        print(f"Using model: {settings.llm_model}", file=sys.stderr)

        # Call LLM
        print("Calling LLM...", file=sys.stderr)
        with create_llm_client(settings) as client:
            answer = call_lllm(client, settings, question)

        # Format output
        result: dict[str, Any] = {
            "answer": answer,
            "tool_calls": [],
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
    except KeyError as e:
        print(f"Error: Unexpected LLM response format: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
