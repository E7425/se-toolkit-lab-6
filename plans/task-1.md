# Task 1 Plan: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**
- 1000 free requests per day (sufficient for development and testing)
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API (easy integration with `httpx`)
- Strong tool calling support (needed for Task 2)

## Environment Configuration

The agent will read configuration from `.env.agent.secret`:
- `LLM_API_KEY` — API key for authentication
- `LLM_API_BASE` — Base URL (e.g., `http://<vm-ip>:<port>/v1`)
- `LLM_MODEL` — Model name (`qwen3-coder-plus`)

## Agent Architecture

### Components

1. **CLI Entry Point**
   - Parse command-line argument (the question)
   - Handle missing argument with usage message to stderr
   - Exit with code 1 on error

2. **LLM Client**
   - Use `httpx` (already in project dependencies) for HTTP requests
   - Call OpenAI-compatible `/v1/chat/completions` endpoint
   - Send system prompt + user question
   - Set 60-second timeout

3. **Response Parser**
   - Extract answer from LLM response
   - Format as required JSON structure
   - Ensure `answer` and `tool_calls` fields are present

4. **Output Formatter**
   - Write valid JSON to stdout (single line)
   - Write debug/progress info to stderr
   - Exit code 0 on success

### System Prompt (minimal for Task 1)

```
You are a helpful assistant. Answer the user's question concisely.
Respond with only the answer, no explanations.
```

### Output Format

The agent will output a single JSON line:
```json
{"answer": "<LLM response>", "tool_calls": []}
```

### Error Handling

- Network errors: print to stderr, exit code 1
- Invalid API response: print to stderr, exit code 1
- Missing question argument: print usage to stderr, exit code 1
- Timeout (>60s): print to stderr, exit code 1

## Testing Strategy

Create one regression test (`backend/tests/unit/test_agent_task1.py`):
1. Run `agent.py` as subprocess with a test question
2. Parse stdout as JSON
3. Assert `answer` field exists and is non-empty string
4. Assert `tool_calls` field exists and is empty list

## Implementation Order

1. Create this plan file
2. Create `.env.agent.secret` from example
3. Implement `agent.py`
4. Test manually with sample questions
5. Create regression test
6. Update `AGENT.md` documentation
