# Dynamic Configuration Update

## Overview

The Lambda function now supports passing configuration parameters through the REST API payload, allowing per-request customization of:

- **target_domain** - Domain to search
- **bedrock_model_id** - AWS Bedrock model to use
- **chunk_size** - Text chunk size for processing
- **chunk_overlap** - Overlap between text chunks
- **log_level** - Logging level for the request

## What Changed

### Before
Configuration was hardcoded in the Lambda initialization from environment variables only.

### After
Configuration can be provided per-request via API payload, with environment variables as fallbacks.

## API Request Format

### Complete Example

```json
{
  "query": "What are the baggage fees?",
  "max_results": 5,
  "max_chunks": 10,
  "system_prompt": "Custom prompt with {context} and {query}",
  "target_domain": "westjet.com",
  "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
  "chunk_size": 1500,
  "chunk_overlap": 300,
  "log_level": "DEBUG"
}
```

### Minimal Example (All Optional Except Query)

```json
{
  "query": "What are the baggage fees?"
}
```

## New Parameters

### target_domain

**Description**: Domain to search for information
**Type**: String
**Default**: From `TARGET_DOMAIN` environment variable (default: `example.com`)
**Validation**: Non-empty string
**Example**: `"westjet.com"`, `"example.org"`

```json
{
  "query": "pricing info",
  "target_domain": "mycompany.com"
}
```

### bedrock_model_id

**Description**: AWS Bedrock model ID to use for answer generation
**Type**: String
**Default**: From `BEDROCK_MODEL_ID` environment variable (default: `anthropic.claude-3-haiku-20240307-v1:0`)
**Validation**: Non-empty string
**Common Values**:
- `anthropic.claude-3-haiku-20240307-v1:0` (fastest, cheapest)
- `anthropic.claude-3-sonnet-20240229-v1:0` (balanced)
- `anthropic.claude-3-opus-20240229-v1:0` (most capable)

```json
{
  "query": "complex analysis",
  "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0"
}
```

### chunk_size

**Description**: Size of text chunks in characters for processing
**Type**: Integer
**Default**: From `CHUNK_SIZE` environment variable (default: `1000`)
**Validation**: Between 100 and 10,000
**Guidance**:
- Smaller (500-800): Better for precise matching, more chunks
- Medium (1000-1500): Balanced performance
- Larger (2000-3000): More context per chunk, fewer chunks

```json
{
  "query": "detailed explanation",
  "chunk_size": 2000
}
```

### chunk_overlap

**Description**: Number of characters to overlap between consecutive chunks
**Type**: Integer
**Default**: From `CHUNK_OVERLAP` environment variable (default: `200`)
**Validation**: Between 0 and 1,000, must be less than `chunk_size`
**Guidance**:
- Prevents information loss at chunk boundaries
- Typically 10-20% of chunk_size
- Higher overlap = more redundancy but better coverage

```json
{
  "query": "information",
  "chunk_size": 1500,
  "chunk_overlap": 300
}
```

### log_level

**Description**: Logging level for this request
**Type**: String
**Default**: From `LOG_LEVEL` environment variable (default: `INFO`)
**Validation**: One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
**Use Cases**:
- `DEBUG`: Troubleshooting, detailed execution logs
- `INFO`: Normal operation (default)
- `WARNING`: Only warnings and errors
- `ERROR`: Only errors

```json
{
  "query": "test query",
  "log_level": "DEBUG"
}
```

## Response Format

The response now includes configuration metadata:

```json
{
  "answer": "Generated answer...",
  "sources": ["url1", "url2"],
  "source_details": [...],
  "metadata": {
    "chunks_processed": 5,
    "urls_scraped": 3,
    "total_time_ms": 2500,
    "target_domain": "westjet.com",
    "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
    "chunk_size": 1000,
    "chunk_overlap": 200
  }
}
```

## Validation Rules

| Parameter | Type | Min | Max | Special Rules |
|-----------|------|-----|-----|---------------|
| query | string | - | - | Required, non-empty |
| max_results | integer | 1 | 20 | - |
| max_chunks | integer | 1 | 50 | - |
| target_domain | string | - | - | Non-empty if provided |
| bedrock_model_id | string | - | - | Non-empty if provided |
| chunk_size | integer | 100 | 10000 | - |
| chunk_overlap | integer | 0 | 1000 | Must be < chunk_size |
| log_level | string | - | - | Must be valid log level |
| system_prompt | string | - | - | Must include {query} and {context} |

## Error Responses

### Invalid target_domain

```json
{
  "statusCode": 400,
  "body": {
    "error": "target_domain must be a non-empty string"
  }
}
```

### Invalid chunk_size

```json
{
  "statusCode": 400,
  "body": {
    "error": "chunk_size must be an integer between 100 and 10000"
  }
}
```

### Invalid chunk_overlap

```json
{
  "statusCode": 400,
  "body": {
    "error": "chunk_overlap must be less than chunk_size"
  }
}
```

### Invalid log_level

```json
{
  "statusCode": 400,
  "body": {
    "error": "log_level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
  }
}
```

## Implementation Details

### Service Caching

The handler uses intelligent caching to avoid recreating services:

- **TextProcessor**: Cached by `chunk_size` and `chunk_overlap` combination
- **BedrockService**: Cached by `model_id`
- **SearchService** and **ScraperService**: Reused across all requests

This ensures efficient resource utilization while supporting dynamic configuration.

### Log Level Handling

- Log level changes are applied for the duration of the request only
- Original log level is restored after request completion
- Uses try/finally to ensure restoration even on errors

## Use Cases

### 1. Different Domains

```json
{
  "query": "pricing",
  "target_domain": "competitor.com"
}
```

### 2. Higher Quality Responses

```json
{
  "query": "complex analysis",
  "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0"
}
```

### 3. Fine-tuned Chunking

```json
{
  "query": "detailed info",
  "chunk_size": 2000,
  "chunk_overlap": 400
}
```

### 4. Debugging

```json
{
  "query": "test",
  "log_level": "DEBUG"
}
```

### 5. Combined Configuration

```json
{
  "query": "comprehensive query",
  "target_domain": "docs.example.com",
  "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
  "chunk_size": 1500,
  "chunk_overlap": 300,
  "max_results": 10,
  "max_chunks": 15,
  "log_level": "INFO"
}
```

## Backward Compatibility

✅ Fully backward compatible - all new parameters are optional
✅ Environment variables still work as defaults
✅ Existing API calls work without modification

## Testing

All parameters are thoroughly tested with validation tests:
- Valid parameter acceptance
- Invalid type rejection
- Out-of-range value rejection
- Cross-parameter validation (chunk_overlap < chunk_size)

Run tests:
```bash
pytest src/tests/test_app.py::TestLambdaHandler -v
```

## Performance Considerations

- **Service Caching**: First request with new config may be slower due to service initialization
- **Model Selection**: Haiku (fastest) < Sonnet (balanced) < Opus (slowest but most capable)
- **Chunk Size**: Larger chunks = fewer embeddings = faster processing
- **Log Level**: DEBUG produces more output, may slightly impact performance

## Migration Guide

No migration required! Simply start using new parameters when needed.

Old code:
```json
{"query": "What are fees?"}
```

Still works! New code with custom config:
```json
{
  "query": "What are fees?",
  "target_domain": "custom.com",
  "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0"
}
```
