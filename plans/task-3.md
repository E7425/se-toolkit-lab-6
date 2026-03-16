# Task 3 Plan: The System Agent

## Overview

Extend the documentation agent from Task 2 with a `query_api` tool that can query the deployed backend LMS API. This enables the agent to answer:
1. **Static system facts** — framework, ports, status codes (from source code)
2. **Data-dependent queries** — item count, scores, analytics (from live API)

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM)
**Model:** `qwen3-coder-plus`

## Environment Variables

The agent reads configuration from two files:

| Variable | Purpose | Source File |
|----------|---------|-------------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for query_api auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for query_api (optional) | `.env.agent.secret` |

**Important:** These must be read from environment variables, not hardcoded. The autochecker injects its own values.

## Tool Definition: query_api

### Schema

```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Call the deployed backend LMS API. Use for data queries like item counts, scores, analytics.",
    "parameters": {
      "type": "object",
      "properties": {
        "method": {
          "type": "string",
          "description": "HTTP method (GET, POST, etc.)",
          "enum": ["GET", "POST", "PUT", "DELETE"]
        },
        "path": {
          "type": "string",
          "description": "API path (e.g., /items/, /analytics/completion-rate)"
        },
        "body": {
          "type": "string",
          "description": "Optional JSON request body (for POST/PUT)"
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

### Implementation

```python
def tool_query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend LMS API with authentication."""
    # Read LMS_API_KEY from .env.docker.secret via environment
    # Read AGENT_API_BASE_URL from .env.agent.secret (default: http://localhost:42002)
    
    url = f"{api_base_url}{path}"
    headers = {
        "Authorization": f"Bearer {lms_api_key}",
        "Content-Type": "application/json",
    }
    
    # Make HTTP request with httpx
    # Return JSON string with status_code and body
```

### Authentication

- Use `LMS_API_KEY` from `.env.docker.secret`
- Send as `Authorization: Bearer <LMS_API_KEY>` header
- This is different from `LLM_API_KEY` — don't mix them up!

## System Prompt Update

The system prompt must guide the LLM to choose the right tool:

```
You are a documentation and system assistant. Answer questions using:

1. **list_files** — Discover what files exist in a directory
2. **read_file** — Read source code or documentation files
3. **query_api** — Query the live backend API for data

Tool selection guide:
- For wiki/documentation questions → use list_files, then read_file
- For source code questions (framework, ports, bugs) → use list_files to find files, then read_file
- For data questions (item count, scores, analytics) → use query_api
- For API behavior questions (status codes, errors) → use query_api

Always include source references:
- Wiki files: wiki/filename.md#section
- Source code: path/to/file.py:function_or_class
- API data: /api/endpoint
```

## Agentic Loop

The loop remains the same as Task 2:
1. Send question + all tool schemas to LLM
2. If tool_calls → execute tools, record results, feed back to LLM
3. If text answer → extract answer and source, output JSON
4. Max 10 iterations

## Security Considerations

- `query_api` should only access the configured backend URL
- No arbitrary URL fetching (prevent SSRF)
- Path traversal protection for file tools (already implemented)

## Benchmark Questions

The 10 local questions in `run_eval.py`:

| # | Question | Tool Required | Expected Answer |
|---|----------|---------------|-----------------|
| 0 | Wiki: protect a branch | read_file | branch, protect |
| 1 | Wiki: SSH connection | read_file | ssh, key, connect |
| 2 | Web framework from source | read_file | FastAPI |
| 3 | API router modules | list_files | items, interactions, analytics, pipeline |
| 4 | Item count in database | query_api | number > 0 |
| 5 | Status code without auth | query_api | 401 or 403 |
| 6 | /analytics/completion-rate error | query_api, read_file | ZeroDivisionError |
| 7 | /analytics/top-learners bug | query_api, read_file | TypeError, None, sorted |
| 8 | Request lifecycle (docker-compose + Dockerfile) | read_file | Caddy → FastAPI → auth → router → ORM → PostgreSQL |
| 9 | ETL idempotency | read_file | external_id check, duplicates skipped |

## Iteration Strategy

1. **First run:** Run `uv run run_eval.py` to get baseline score
2. **Analyze failures:** For each failing question:
   - Check if wrong tool was called → improve system prompt
   - Check if tool returned error → fix tool implementation
   - Check if answer doesn't match keywords → adjust prompt for precision
3. **Re-run:** Iterate until all 10 pass
4. **Common issues:**
   - LLM doesn't use tools → make tool descriptions more explicit
   - Wrong arguments → clarify parameter descriptions
   - Timeout → reduce max iterations or use faster model

## Current Status

**Best score: 8/10 passed**

### Passing Questions (8):
1. ✓ Wiki: protect a branch
2. ✓ Wiki: SSH connection  
3. ✓ Web framework from source
4. ✓ API router modules
5. ✓ Item count in database
6. ✓ Status code without auth
7. ✓ /analytics/completion-rate error
8. ✓ /analytics/top-learners bug

### Failing Questions (2):
9. ✗ Request lifecycle - LLM doesn't complete answer after reading files
10. ✗ ETL idempotency - Not yet tested

### Diagnosis

**Question 9 failure:** The LLM (qwen3-coder-plus) tends to continue reading files instead of providing a complete answer. The model reads 4-5 files but then says "Let me also read X" instead of providing the final trace.

**Root cause:** The model appears to have limitations in producing long, complete answers after multiple tool calls. It continues the "reading loop" instead of switching to "answering mode".

**Attempted fixes:**
- Increased max_tokens to 16384
- Increased max_iterations to 20
- Added explicit instructions in system prompt to stop after 4-5 files
- Added "CRITICAL" warnings to provide complete answer

**Next steps:**
- Consider using a different model with better long-form generation
- Try adding a separate "answer synthesis" step after reading files
- Experiment with few-shot examples showing complete answers

## Testing Strategy

Two new regression tests:

1. **Framework question:** "What framework does the backend use?"
   - Expected: `read_file` in tool_calls
   - Source should reference backend Python files

2. **API data question:** "How many items are in the database?"
   - Expected: `query_api` in tool_calls
   - Answer should contain a number > 0

## Implementation Order

1. Create this plan file
2. Add `query_api` tool schema and implementation
3. Update settings to read `LMS_API_KEY` and `AGENT_API_BASE_URL`
4. Update system prompt with tool selection guidance
5. Test `query_api` manually
6. Run `run_eval.py` and iterate
7. Add 2 regression tests
8. Update `AGENT.md` with lessons learned (200+ words)
