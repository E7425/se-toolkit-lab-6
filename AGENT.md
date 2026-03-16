# Agent Documentation

## Overview

This agent is a CLI tool that connects to an LLM and answers questions using tools. It implements an agentic loop with tool calling capabilities, including file operations and backend API queries.

## Architecture

### Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  CLI Input  │ ──> │ Agentic Loop │ ──> │  LLM API    │ ──> │ JSON Output  │
│  (question) │     │  + Tools     │     │  (Qwen)     │     │  (stdout)    │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Settings    │
                    │  (.env file) │
                    └──────────────┘
```

### Data Flow

1. **Input Parsing**: The CLI reads the question from command-line arguments
2. **Agentic Loop**: 
   - Send question + tool definitions to LLM
   - If LLM returns tool calls → execute tools, feed results back
   - Repeat until LLM returns final answer or max 20 iterations
3. **Output Formatting**: Return JSON with `answer`, `source`, and `tool_calls`

## LLM Provider

**Provider:** Qwen Code API (self-hosted on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API with function calling support
- Strong tool calling capabilities

## Configuration

Create `.env.agent.secret` from `.env.agent.example`:

```bash
cp .env.agent.example .env.agent.secret
```

Required environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `your-api-key` |
| `LLM_API_BASE` | Base URL of LLM API | `http://<vm-ip>:<port>/v1` |
| `LLM_MODEL` | Model name | `qwen3-coder-plus` |
| `LMS_API_KEY` | Backend API key for query_api | `your-lms-key` |
| `AGENT_API_BASE_URL` | Backend API URL | `http://localhost:42002` |

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "To resolve a merge conflict, choose which version to keep...",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git.md\ngit-vscode.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-vscode.md"},
      "result": "# Git in VS Code\n\n..."
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Wiki file reference or API endpoint |
| `tool_calls` | array | All tool calls made during the agentic loop |

## Tools

### read_file

Read a file from the project repository.

**Parameters:**
- `path` (string, required) — Relative path from project root

**Example:**
```json
{"tool": "read_file", "args": {"path": "wiki/git.md"}}
```

**Security:**
- Cannot read files outside the project directory
- Path traversal (`../`) is blocked

### list_files

List files and directories at a given path.

**Parameters:**
- `path` (string, required) — Relative directory path from project root

**Example:**
```json
{"tool": "list_files", "args": {"path": "wiki"}}
```

**Security:**
- Cannot list directories outside the project directory
- Path traversal (`../`) is blocked

### query_api

Call the deployed backend LMS API for data queries.

**Parameters:**
- `method` (string, required) — HTTP method (GET, POST, PUT, DELETE)
- `path` (string, required) — API endpoint path
- `body` (string, optional) — JSON request body for POST/PUT
- `include_auth` (boolean, optional, default: true) — Whether to include authentication

**Example:**
```json
{"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
```

**Authentication:**
- Uses `LMS_API_KEY` from `.env.docker.secret`
- Sent as `Authorization: Bearer <LMS_API_KEY>` header
- Set `include_auth: false` to test unauthenticated access

## Agentic Loop

The agent implements an iterative reasoning loop:

```
1. Send user question + tool definitions to LLM
2. Parse LLM response:
   - If tool_calls present:
     a. Execute each tool
     b. Record tool call (tool, args, result)
     c. Append tool results as "tool" role messages
     d. If iterations < 20, go to step 1
   - If text message (no tool calls):
     a. Extract answer
     b. Extract source reference
     c. Output JSON and exit
3. If max iterations (20) reached, output best available answer
```

### Maximum Iterations

The loop runs at most 20 times to prevent infinite loops.

## System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read specific documentation files
3. Use `query_api` for live data queries
4. Answer questions based on file contents
5. Include source references in the format `wiki/filename.md#section-anchor`

## Path Security

Both file tools implement path security to prevent directory traversal:

```python
def safe_resolve_path(path: str, project_root: Path) -> Path | None:
    """Resolve path and ensure it's within project directory."""
    clean_path = path.lstrip("/").lstrip("\\")
    resolved = (project_root / clean_path).resolve()
    
    # Check if resolved path is within project root
    try:
        resolved.relative_to(project_root)
        return resolved
    except ValueError:
        return None  # Path is outside project directory
```

## Error Handling

| Error | Exit Code | Output |
|-------|-----------|--------|
| Missing argument | 1 | Usage message to stderr |
| Network error | 1 | Error details to stderr |
| API error (4xx/5xx) | 1 | Status code to stderr |
| Timeout (>60s) | 1 | Timeout message to stderr |
| Tool execution error | 0 | Error in tool result field |

## Testing

Run all regression tests:

```bash
uv run pytest tests/ -v
```

Tests verify:
- `test_agent_task1.py`: Basic JSON output with required fields
- `test_agent_task2.py`: Tool usage for documentation questions
- `test_agent_task3.py`: Tool usage for system questions

## Benchmark Results

**Current score: 8/10 passed**

### Passing Questions:
1. ✓ Wiki: protect a branch
2. ✓ Wiki: SSH connection  
3. ✓ Web framework from source
4. ✓ API router modules
5. ✓ Item count in database
6. ✓ Status code without auth
7. ✓ /analytics/completion-rate error
8. ✓ /analytics/top-learners bug

### Known Issues:
- Question 9 (request lifecycle): LLM sometimes doesn't complete the answer after reading files
- Question 10 (ETL idempotency): Not yet tested

## Lessons Learned

Building this agent revealed several important insights:

1. **LLM Limitations**: The qwen3-coder-plus model sometimes struggles with long-form generation after multiple tool calls. It tends to continue the "reading loop" instead of switching to "answering mode". This was addressed by adding explicit instructions in the system prompt to stop after reading 4-5 files.

2. **Tool Design**: Adding an `include_auth` parameter to `query_api` was crucial for testing unauthenticated access (question 6 about 401 status codes).

3. **System Prompt Engineering**: The system prompt evolved significantly through iteration. Key additions included:
   - Explicit tool selection guidance
   - Warnings against saying "let me read X"
   - Instructions to read ALL files before answering
   - File count limits to prevent infinite reading

4. **Encoding Issues**: Windows console encoding (cp1252) caused crashes when LLM responses contained emoji. This was fixed by wrapping stdout/stderr with UTF-8 TextIOWrapper.

5. **Token Limits**: Increasing `max_tokens` to 16384 was necessary for long answers involving multiple file reads.

6. **Iteration Count**: Setting `max_iterations` to 20 allows the agent to read multiple files (5-6) before providing an answer.

## Project Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI entry point
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.docker.secret    # Backend API configuration (gitignored)
├── .env.agent.example    # Example LLM configuration
├── plans/
│   ├── task-1.md         # Task 1 implementation plan
│   ├── task-2.md         # Task 2 implementation plan
│   └── task-3.md         # Task 3 implementation plan
├── AGENT.md              # This documentation
└── tests/
    ├── test_agent_task1.py  # Task 1 regression test
    ├── test_agent_task2.py  # Task 2 regression tests
    └── test_agent_task3.py  # Task 3 regression tests
```

## Future Extensions

### Potential Improvements
- Add few-shot examples to system prompt showing complete answers
- Implement a separate "answer synthesis" step after reading files
- Consider using a different model with better long-form generation
- Add more tools (e.g., `search_code` for grep-like functionality)
