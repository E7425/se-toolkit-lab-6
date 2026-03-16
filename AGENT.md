# Agent Documentation

## Overview

This agent is a CLI tool that connects to an LLM and answers questions using the project wiki documentation. It implements an agentic loop with tool calling capabilities.

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
   - Repeat until LLM returns final answer or max 10 iterations
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
| `source` | string | Wiki file reference (e.g., `wiki/file.md#section`) |
| `tool_calls` | array | All tool calls made during the agentic loop |

### Tool Call Structure

Each entry in `tool_calls` contains:

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool (`read_file` or `list_files`) |
| `args` | object | Arguments passed to the tool |
| `result` | string | The tool's output or error message |

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

## Agentic Loop

The agent implements an iterative reasoning loop:

```
1. Send user question + tool definitions to LLM
2. Parse LLM response:
   - If tool_calls present:
     a. Execute each tool
     b. Record tool call (tool, args, result)
     c. Append tool results as "tool" role messages
     d. If iterations < 10, go to step 1
   - If text message (no tool calls):
     a. Extract answer
     b. Extract source reference
     c. Output JSON and exit
3. If max iterations (10) reached, output best available answer
```

### Maximum Iterations

The loop runs at most 10 times to prevent infinite loops.

## System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read specific documentation files
3. Answer questions based on file contents
4. Include source references in the format `wiki/filename.md#section-anchor`

## Path Security

Both tools implement path security to prevent directory traversal:

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

## Project Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI entry point
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.agent.example    # Example configuration
├── plans/
│   ├── task-1.md         # Task 1 implementation plan
│   └── task-2.md         # Task 2 implementation plan
├── AGENT.md              # This documentation
└── tests/
    ├── test_agent_task1.py  # Task 1 regression test
    └── test_agent_task2.py  # Task 2 regression tests
```

## Future Extensions

### Task 3: Domain Knowledge
- Expand system prompt with domain-specific knowledge
- Add more tools (e.g., `query_api` for backend queries)
- Implement better source extraction and citation
