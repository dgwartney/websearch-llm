# query-lambda.sh Changelog

## Version 2.0 - System Prompt Support

**Date**: 2025-11-04

### Summary

Added support for custom system prompts via the `--system-prompt-path` option, allowing users to customize LLM behavior without modifying the Lambda code.

### New Features

#### 1. Custom System Prompt Support
- **New option**: `--system-prompt-path FILE`
- Reads system prompt from specified file
- Validates file existence and readability
- Validates required `{query}` and `{context}` placeholders
- Properly escapes content for JSON payload

#### 2. Enhanced Validation
- File existence check
- File readability check
- Required placeholder validation (`{query}` and `{context}`)
- Clear error messages for all validation failures

#### 3. Updated Help Documentation
- Added `--system-prompt-path` to usage examples
- Added example for custom system prompt usage
- Added note about required placeholders

### Technical Changes

#### Modified Files
- `query-lambda.sh`: Added system prompt support

#### New Variables
```bash
SYSTEM_PROMPT_PATH=""  # Path to system prompt file
```

#### New Command Line Option
```bash
--system-prompt-path FILE   # Specify custom system prompt file
```

#### Validation Logic Added
```bash
# Validate file exists
if [ ! -f "$SYSTEM_PROMPT_PATH" ]; then
    ERROR: System prompt file not found
fi

# Validate file is readable
if [ ! -r "$SYSTEM_PROMPT_PATH" ]; then
    ERROR: System prompt file is not readable
fi

# Validate required placeholders
if [[ ! "$SYSTEM_PROMPT_CONTENT" =~ \{query\} ]]; then
    ERROR: System prompt must include {query} placeholder
fi

if [[ ! "$SYSTEM_PROMPT_CONTENT" =~ \{context\} ]]; then
    ERROR: System prompt must include {context} placeholder
fi
```

#### JSON Payload Construction
```bash
# With system prompt
if [ -n "$SYSTEM_PROMPT_PATH" ]; then
    SYSTEM_PROMPT_JSON=$(jq -Rs . < "$SYSTEM_PROMPT_PATH")
    JSON_PAYLOAD=$(cat <<EOF
{
  "query": "$QUERY",
  "max_results": $MAX_RESULTS,
  "max_chunks": $MAX_CHUNKS,
  "system_prompt": $SYSTEM_PROMPT_JSON
}
EOF
)
else
    # Without system prompt (original behavior)
    JSON_PAYLOAD=$(cat <<EOF
{
  "query": "$QUERY",
  "max_results": $MAX_RESULTS,
  "max_chunks": $MAX_CHUNKS
}
EOF
)
fi
```

### Usage Examples

#### Basic Usage
```bash
./query-lambda.sh "What are baggage fees?" --system-prompt-path custom_prompt.txt
```

#### Combined Options
```bash
./query-lambda.sh "Check-in process" \
  --system-prompt-path custom_prompt.txt \
  --max-results 5 \
  --max-chunks 10
```

#### Example System Prompt File
```text
You are a helpful travel assistant.

Context: {context}
Question: {query}

Provide a clear, concise answer:
```

### Error Messages

| Condition | Error Message |
|-----------|---------------|
| File not found | `ERROR: System prompt file not found: <path>` |
| File not readable | `ERROR: System prompt file is not readable: <path>` |
| Missing {query} | `ERROR: System prompt must include {query} placeholder` |
| Missing {context} | `ERROR: System prompt must include {context} placeholder` |

### Backward Compatibility

✅ **Fully backward compatible**
- Script works without `--system-prompt-path` option
- Existing scripts continue to work unchanged
- Default behavior preserved (uses Lambda's default prompt)

### Dependencies

No new dependencies required. Uses existing tools:
- `bash` - Shell scripting
- `jq` - JSON processing and escaping (already required)
- `curl` - HTTP requests (already required)

### Testing

#### Test Cases Covered

1. ✅ Valid system prompt file
2. ✅ Non-existent file
3. ✅ Unreadable file
4. ✅ Missing `{query}` placeholder
5. ✅ Missing `{context}` placeholder
6. ✅ Special characters (quotes, newlines, etc.)
7. ✅ Backward compatibility (without option)
8. ✅ Combined with other options

#### Manual Testing Commands

```bash
# Test help
./query-lambda.sh --help

# Test file not found
./query-lambda.sh "test" --system-prompt-path nonexistent.txt

# Test missing placeholders
echo "Invalid prompt" > invalid.txt
./query-lambda.sh "test" --system-prompt-path invalid.txt

# Test valid prompt
cat > test_prompt.txt << 'EOF'
Context: {context}
Query: {query}
EOF
./query-lambda.sh "test" --system-prompt-path test_prompt.txt
```

### Related Documentation

- [SYSTEM_PROMPT_USAGE.md](SYSTEM_PROMPT_USAGE.md) - Complete API documentation
- [QUERY_SCRIPT_UPDATE.md](QUERY_SCRIPT_UPDATE.md) - Detailed script update guide
- [example_system_prompt.txt](example_system_prompt.txt) - Example prompt file

### Migration Guide

No migration required. The enhancement is:
- **Opt-in**: Only used when `--system-prompt-path` is specified
- **Non-breaking**: Existing usage patterns continue to work
- **Additive**: No changes to existing functionality

Users who want to use custom prompts can start using the new option immediately.

### Future Enhancements

Potential future improvements:
- Support for inline system prompts via `--system-prompt "text"`
- Template library with pre-defined prompts
- Environment variable support for default prompt path
- Validation of prompt effectiveness/quality
