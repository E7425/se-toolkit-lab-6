# Task 2 Plan: The Documentation Agent

## Overview

Transform the CLI from Task 1 into an agentic system that can call tools to read project documentation and answer questions with source references.

## Tool Definitions

### read_file

**Purpose:** Read a file from the project repository.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Resolve path relative to project root
- Security check: ensure resolved path is within project directory (no `../` traversal)
- Read file content and return as string
- Return error message if file doesn't exist

### list_files

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories in a directory",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Resolve path relative to project root
- Security check: ensure resolved path is within project directory
- List directory entries (files and subdirectories)
- Return newline-separated listing
- Return error message if directory doesn't exist

## Path Security

Both tools must prevent directory traversal attacks:

```python
def safe_resolve_path(path: str, project_root: Path) -> Path | None:
    """Resolve path and ensure it's within project directory."""
    # Remove leading slashes to make path relative
    clean_path = path.lstrip("/")
    resolved = (project_root / clean_path).resolve()
    
    # Check if resolved path is within project root
    try:
        resolved.relative_to(project_root)
        return resolved
    except ValueError:
        return None  # Path is outside project directory
```

## Agentic Loop

The loop executes until the LLM provides a final answer or max iterations reached:

```
1. Send messages (including user question) to LLM with tool definitions
2. Parse response:
   - If tool_calls present:
     a. Execute each tool
     b. Record tool call (tool, args, result) in tool_calls list
     c. Append tool results as "tool" role messages
     d. If iterations < 10, go to step 1
   - If text message (no tool calls):
     a. Extract answer from message content
     b. Extract source reference from answer or last tool result
     c. Output JSON and exit
3. If max iterations (10) reached, output best available answer
```

## System Prompt

The system prompt will instruct the LLM to:

1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific documentation files
3. Include source references in the answer (file path + section anchor)
4. Call tools iteratively until it has enough information

Example:
```
You are a documentation assistant. Answer questions using the project wiki.

Use these tools:
- list_files: Discover what files exist in a directory
- read_file: Read the contents of a specific file

Process:
1. First use list_files to find relevant wiki files
2. Then use read_file to read the content
3. Answer the question with information from the files
4. Always include the source as: wiki/filename.md#section-anchor

Rules:
- Only access files in the wiki/ directory
- Include specific section anchors when referencing content
- If you don't find the answer, say so honestly
```

## Output Format

```json
{
  "answer": "The answer text from the LLM",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Data Structures

### ToolCall (for output)
```python
@dataclass
class ToolCallOutput:
    tool: str
    args: dict[str, Any]
    result: str
```

### Message types for LLM API
```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": result, "tool_call_id": "..."},
]
```

## Error Handling

- Tool execution errors: return error message as tool result
- Path security violations: return "Access denied" error
- LLM API errors: exit with error code 1
- Max iterations reached: output partial answer with available information

## Testing Strategy

Two regression tests:

1. **Test merge conflict question:**
   - Question: "How do you resolve a merge conflict?"
   - Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

2. **Test wiki listing question:**
   - Question: "What files are in the wiki?"
   - Expected: `list_files` in tool_calls

## Implementation Order

1. Create this plan file
2. Implement `read_file` and `list_files` tools with path security
3. Define tool schemas for LLM function calling
4. Implement agentic loop with max 10 iterations
5. Update output format to include `source` field
6. Update system prompt
7. Test manually with wiki questions
8. Create 2 regression tests
9. Update `AGENT.md` documentation
