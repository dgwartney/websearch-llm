# query-lambda.sh Update - Custom System Prompt Support

## Overview

The `query-lambda.sh` script has been enhanced to support custom system prompts via the `--system-prompt-path` option. This allows you to customize the LLM's behavior without modifying the Lambda code.

## What's New

### New Option: `--system-prompt-path FILE`

Specify a file containing a custom system prompt to override the default WestJet prompt.

```bash
./query-lambda.sh "Your question" --system-prompt-path custom_prompt.txt
```

## Quick Start

### 1. Create a System Prompt File

```bash
cat > custom_prompt.txt << 'EOF'
You are a helpful travel assistant providing clear and concise information.

Context from website:
{context}

Customer question: {query}

Instructions:
1. Provide direct, accurate answers based on the context
2. Be friendly and professional
3. Keep responses concise (2-3 sentences maximum)

Your answer:
EOF
```

**Important**: Your prompt MUST include:
- `{context}` - Where the scraped web content will be inserted
- `{query}` - Where the user's question will be inserted

### 2. Use It

```bash
export LAMBDA_API_KEY="your-api-key-here"
./query-lambda.sh "What are the baggage fees?" --system-prompt-path custom_prompt.txt
```

## Features

### Validation

The script automatically validates:
- ✅ File exists
- ✅ File is readable
- ✅ Contains `{query}` placeholder
- ✅ Contains `{context}` placeholder

### Error Handling

Clear error messages guide you:

```bash
# If file doesn't exist
ERROR: System prompt file not found: nonexistent.txt

# If missing required placeholder
ERROR: System prompt must include {query} placeholder
ERROR: System prompt must include {context} placeholder

# If file isn't readable
ERROR: System prompt file is not readable: custom_prompt.txt
```

### JSON Escaping

The script properly escapes the system prompt content for JSON, handling:
- Newlines
- Quotes
- Special characters

## Usage Examples

### Basic Usage

```bash
./query-lambda.sh "What are baggage fees?" --system-prompt-path custom_prompt.txt
```

### Combined with Other Options

```bash
./query-lambda.sh "Check-in process" \
  --system-prompt-path custom_prompt.txt \
  --max-results 5 \
  --max-chunks 10
```

### Without Custom Prompt (Default Behavior)

```bash
# Still works exactly as before
./query-lambda.sh "What are baggage fees?"
```

## Example System Prompts

### Concise Responses

```text
You are a customer service agent. Be brief and direct.

Context: {context}
Question: {query}

Provide a 1-2 sentence answer:
```

### Detailed Technical Responses

```text
You are a technical support specialist. Provide comprehensive answers.

Context from documentation:
{context}

User question: {query}

Provide a detailed answer with step-by-step instructions:
```

### Multi-language Support

```text
You are a multilingual travel assistant.

Context: {context}
Question: {query}

If the question is in Spanish, respond in Spanish.
If the question is in French, respond in French.
Otherwise, respond in English.

Answer:
```

## Testing

### Test File Validation

```bash
# Test missing file
./query-lambda.sh "test" --system-prompt-path nonexistent.txt
# Expected: ERROR: System prompt file not found

# Test missing placeholders
echo "Invalid prompt" > invalid.txt
./query-lambda.sh "test" --system-prompt-path invalid.txt
# Expected: ERROR: System prompt must include {query} placeholder
```

### Test Valid Prompt

```bash
# Create valid prompt
cat > test_prompt.txt << 'EOF'
Simple prompt.
Context: {context}
Query: {query}
EOF

# Test (will fail on API key if not set, which is expected)
./query-lambda.sh "test" --system-prompt-path test_prompt.txt
```

## Implementation Details

### JSON Payload Construction

Without custom prompt:
```json
{
  "query": "What are baggage fees?",
  "max_results": 3,
  "max_chunks": 5
}
```

With custom prompt:
```json
{
  "query": "What are baggage fees?",
  "max_results": 3,
  "max_chunks": 5,
  "system_prompt": "Your custom prompt...\n{context}\n{query}"
}
```

### Key Script Changes

1. **New variable**: `SYSTEM_PROMPT_PATH`
2. **New option parsing**: `--system-prompt-path`
3. **Validation logic**: File checks and placeholder validation
4. **JSON building**: Conditional payload construction with `jq` for proper escaping

## Backward Compatibility

✅ Fully backward compatible - existing scripts continue to work without modification
✅ Optional parameter - no changes required to existing deployments
✅ Default behavior preserved - uses WestJet prompt when not specified

## Requirements

The script requires:
- `bash` (any modern version)
- `jq` (for JSON processing and escaping)
- `curl` (for API requests)

## Help

View updated help:
```bash
./query-lambda.sh --help
```

## See Also

- [SYSTEM_PROMPT_USAGE.md](SYSTEM_PROMPT_USAGE.md) - Complete system prompt documentation
- [example_system_prompt.txt](example_system_prompt.txt) - Example prompt file
