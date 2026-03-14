# Agent Documentation

## Overview

This agent is a CLI tool that connects to an LLM and answers questions. It forms the foundation for the agentic system that will be extended with tools and domain knowledge in subsequent tasks.

## Architecture

### Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  CLI Input  │ ──> │  LLM Client  │ ──> │  LLM API    │ ──> │ JSON Output  │
│  (question) │     │  (httpx)     │     │  (Qwen)     │     │  (stdout)    │
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
2. **Configuration**: Settings are loaded from `.env.agent.secret`
3. **LLM Call**: HTTP POST request to the LLM's chat completions endpoint
4. **Response Parsing**: Extract the answer from the LLM response
5. **Output Formatting**: Return JSON with `answer` and `tool_calls` fields

## LLM Provider

**Provider:** Qwen Code API (self-hosted on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API
- Strong tool calling support for future tasks

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
uv run agent.py "What does REST stand for?"
```

### Output Format

The agent outputs a single JSON line to stdout:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `tool_calls` | array | Empty for Task 1, populated in Task 2 |

### Error Handling

| Error | Exit Code | Output |
|-------|-----------|--------|
| Missing argument | 1 | Usage message to stderr |
| Network error | 1 | Error details to stderr |
| API error (4xx/5xx) | 1 | Status code to stderr |
| Timeout (>60s) | 1 | Timeout message to stderr |

## System Prompt

The current system prompt is minimal:

```
You are a helpful assistant. Answer the user's question concisely.
Respond with only the answer, no explanations.
```

This will be expanded in Task 3 with domain knowledge and tool definitions.

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent_task1.py -v
```

The test verifies:
- `agent.py` runs successfully with a question argument
- Output is valid JSON
- `answer` field exists and is non-empty
- `tool_calls` field exists and is an empty list

## Project Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI entry point
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.agent.example    # Example configuration
├── plans/task-1.md       # Implementation plan
├── AGENT.md              # This documentation
└── backend/tests/unit/
    └── test_agent_task1.py  # Regression test
```

## Future Extensions

### Task 2: Add Tools
- Define tool schemas
- Implement tool execution
- Populate `tool_calls` in output

### Task 3: Agentic Loop
- Add system prompt with domain knowledge
- Implement multi-turn conversation
- Add tool selection logic
