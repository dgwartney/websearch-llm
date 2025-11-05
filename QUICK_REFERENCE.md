# Quick Reference - Dynamic Configuration Parameters

## REST API Parameters

| Parameter | Type | Required | Default | Range/Values | Description |
|-----------|------|----------|---------|--------------|-------------|
| **query** | string | ✅ Yes | - | Non-empty | Search query |
| **max_results** | integer | No | 5 | 1-20 | Max URLs to search |
| **max_chunks** | integer | No | 10 | 1-50 | Max text chunks for context |
| **system_prompt** | string | No | WestJet prompt | Must include {query} and {context} | Custom LLM prompt |
| **target_domain** | string | No | From env | Non-empty | Domain to search |
| **bedrock_model_id** | string | No | From env | Valid model ID | Bedrock model to use |
| **chunk_size** | integer | No | 1000 | 100-10000 | Text chunk size (chars) |
| **chunk_overlap** | integer | No | 200 | 0-1000, < chunk_size | Chunk overlap (chars) |
| **log_level** | string | No | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL | Request log level |

## Script Options

```bash
./query-lambda.sh "query" [OPTIONS]

Options:
  --max-results NUM              Max search results (1-20)
  --max-chunks NUM               Max text chunks (1-50)
  --system-prompt-path FILE      Custom system prompt file
  --target-domain DOMAIN         Domain to search
  --bedrock-model-id MODEL       Bedrock model ID
  --chunk-size NUM               Text chunk size (100-10000)
  --chunk-overlap NUM            Chunk overlap (0-1000)
  --log-level LEVEL              Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --help                         Show help
```

## Common Use Cases

### 1. Search Different Domain
```bash
# API
{"query": "pricing", "target_domain": "competitor.com"}

# Script
./query-lambda.sh "pricing" --target-domain competitor.com
```

### 2. Use Better Model
```bash
# API
{"query": "complex analysis", "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0"}

# Script
./query-lambda.sh "complex analysis" --bedrock-model-id anthropic.claude-3-sonnet-20240229-v1:0
```

### 3. Fine-tune Chunking
```bash
# API
{"query": "detailed info", "chunk_size": 2000, "chunk_overlap": 400}

# Script
./query-lambda.sh "detailed info" --chunk-size 2000 --chunk-overlap 400
```

### 4. Debug Mode
```bash
# API
{"query": "test", "log_level": "DEBUG"}

# Script
./query-lambda.sh "test" --log-level DEBUG
```

## Model Options

| Model | Speed | Cost | Quality | Use Case |
|-------|-------|------|---------|----------|
| claude-3-haiku-20240307-v1:0 | ⚡⚡⚡ | 💰 | ⭐⭐⭐ | Fast queries, simple answers |
| claude-3-sonnet-20240229-v1:0 | ⚡⚡ | 💰💰 | ⭐⭐⭐⭐ | Balanced, recommended |
| claude-3-opus-20240229-v1:0 | ⚡ | 💰💰💰 | ⭐⭐⭐⭐⭐ | Complex analysis, best quality |

## Chunk Size Guidelines

| Size | Chunks | Speed | Precision | Use Case |
|------|--------|-------|-----------|----------|
| 500-800 | Many | Slower | High | Precise matching |
| 1000-1500 | Medium | Medium | Medium | Balanced (default) |
| 2000-3000 | Few | Faster | Lower | Broad context |

## Error Codes

| Code | Error | Fix |
|------|-------|-----|
| 400 | Missing query | Include "query" in body |
| 400 | Invalid max_results | Use 1-20 |
| 400 | Invalid max_chunks | Use 1-50 |
| 400 | Invalid chunk_size | Use 100-10000 |
| 400 | Invalid chunk_overlap | Use 0-1000, < chunk_size |
| 400 | Invalid log_level | Use DEBUG, INFO, WARNING, ERROR, CRITICAL |
| 400 | Empty target_domain | Provide non-empty string or omit |
| 400 | Empty bedrock_model_id | Provide valid model ID or omit |
| 400 | Invalid system_prompt | Must include {query} and {context} |
| 500 | Internal error | Check Lambda logs |

## Examples

### Minimal Request
```json
{"query": "What are fees?"}
```

### Full Configuration
```json
{
  "query": "Comprehensive query",
  "max_results": 10,
  "max_chunks": 15,
  "target_domain": "docs.example.com",
  "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
  "chunk_size": 1500,
  "chunk_overlap": 300,
  "log_level": "INFO"
}
```

### Script - Basic
```bash
./query-lambda.sh "What are fees?"
```

### Script - Full Configuration
```bash
./query-lambda.sh "Comprehensive query" \
  --max-results 10 \
  --max-chunks 15 \
  --target-domain docs.example.com \
  --bedrock-model-id anthropic.claude-3-sonnet-20240229-v1:0 \
  --chunk-size 1500 \
  --chunk-overlap 300 \
  --log-level INFO
```

## Response Metadata

All responses include configuration used:

```json
{
  "metadata": {
    "chunks_processed": 8,
    "urls_scraped": 5,
    "total_time_ms": 2500,
    "target_domain": "example.com",
    "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
    "chunk_size": 1500,
    "chunk_overlap": 300
  }
}
```

## Tips

1. **Start with defaults** - They work well for most cases
2. **Use Sonnet for quality** - Best balance of speed and quality
3. **Larger chunks for speed** - When you need fast responses
4. **Smaller chunks for precision** - When you need exact matches
5. **Use DEBUG logging** - Only when troubleshooting
6. **Keep chunk_overlap** at 10-20% of chunk_size
7. **Test different domains** - Compare results across sites
8. **Monitor response time** - Adjust parameters based on performance needs

## Support

- Documentation: `DYNAMIC_CONFIG_UPDATE.md`
- Summary: `DYNAMIC_CONFIG_SUMMARY.md`
- System Prompt Guide: `SYSTEM_PROMPT_USAGE.md`
- Script Help: `./query-lambda.sh --help`
