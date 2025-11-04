# System Prompt Usage Guide

## Overview

The AWS Lambda now supports passing a custom system prompt through the REST API interface. This allows clients to customize how the LLM responds without modifying the Lambda code.

## API Changes

### New Optional Parameter: `system_prompt`

The Lambda handler now accepts an optional `system_prompt` parameter in the request body.

**Requirements:**
- Must be a string
- Must include `{query}` placeholder
- Must include `{context}` placeholder

If not provided, the default WestJet-specific system prompt will be used.

## Request Examples

### Using Default System Prompt

```json
{
  "query": "What are the baggage fees?",
  "max_results": 5,
  "max_chunks": 10
}
```

### Using Custom System Prompt

```json
{
  "query": "What are the baggage fees?",
  "max_results": 5,
  "max_chunks": 10,
  "system_prompt": "You are a helpful travel assistant. Use the following context to answer the question.\n\nContext: {context}\n\nQuestion: {query}\n\nProvide a clear and concise answer:"
}
```

### Custom System Prompt Template Example

```json
{
  "query": "How do I check in?",
  "system_prompt": "You are an airline customer service agent. Be friendly and concise.\n\nContext from our website:\n{context}\n\nCustomer question: {query}\n\nYour response:"
}
```

## Error Responses

### Missing Query Placeholder

```json
{
  "statusCode": 400,
  "body": {
    "error": "system_prompt must include {query} and {context} placeholders"
  }
}
```

### Missing Context Placeholder

```json
{
  "statusCode": 400,
  "body": {
    "error": "system_prompt must include {query} and {context} placeholders"
  }
}
```

### Invalid Type

```json
{
  "statusCode": 400,
  "body": {
    "error": "system_prompt must be a string"
  }
}
```

## Implementation Details

### Files Modified

1. **src/bedrock_service.py** (line 93)
   - Updated `generate_answer()` method to accept optional `system_prompt` parameter
   - Validates placeholders before use
   - Falls back to default template if not provided

2. **src/app.py** (line 62)
   - Updated `process_query()` method to accept and pass `system_prompt`
   - Lambda handler extracts `system_prompt` from request body (line 220)
   - Added validation for `system_prompt` parameter (lines 241-258)
   - Passes to `process_query()` (line 261)

### Testing

Comprehensive tests have been added:

- `test_bedrock_service.py`: Tests for custom prompt handling, validation, and default behavior
- `test_app.py`: Tests for Lambda handler with various system prompt scenarios

Run tests with:
```bash
pytest src/tests/test_bedrock_service.py -v
pytest src/tests/test_app.py::TestLambdaHandler -v
```

## Use Cases

### 1. Different Brand/Company
Replace WestJet-specific branding with your own company's voice.

### 2. Different Response Style
Adjust tone (formal vs casual), length (concise vs detailed), or format (bullet points vs paragraphs).

### 3. Multi-language Support
Include instructions for responding in different languages.

### 4. Specific Domain Knowledge
Add domain-specific instructions for technical, medical, or legal content.

### 5. A/B Testing
Test different prompt variations to optimize response quality.

## Best Practices

1. **Keep it concise**: Shorter prompts are processed faster and more efficiently
2. **Be specific**: Clear instructions lead to better responses
3. **Test thoroughly**: Validate your custom prompt with various queries
4. **Include examples**: Show the LLM what good responses look like
5. **Monitor results**: Track response quality and adjust as needed

## Using the query-lambda.sh Script

The `query-lambda.sh` script has been updated to support custom system prompts via the `--system-prompt-path` option.

### Create a System Prompt File

Create a text file with your custom prompt. It must include `{query}` and `{context}` placeholders:

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

### Use the Script with Custom Prompt

```bash
# Set your API key
export LAMBDA_API_KEY="your-api-key-here"

# Query with custom system prompt
./query-lambda.sh "What are the baggage fees?" --system-prompt-path custom_prompt.txt

# Combine with other options
./query-lambda.sh "Check-in process" \
  --system-prompt-path custom_prompt.txt \
  --max-results 5 \
  --max-chunks 10
```

### Script Validation

The script validates:
- File exists and is readable
- Includes `{query}` placeholder
- Includes `{context}` placeholder

Example error messages:
```bash
ERROR: System prompt file not found: nonexistent.txt
ERROR: System prompt must include {query} placeholder
ERROR: System prompt must include {context} placeholder
```

## Backward Compatibility

The change is fully backward compatible. Existing API calls without `system_prompt` will continue to work with the default WestJet prompt.

The `query-lambda.sh` script works with and without the `--system-prompt-path` option.
