# Web Search LLM - AWS Lambda

A serverless application that performs intelligent web search and generates answers using AWS Bedrock LLMs. Built with AWS SAM, Python, and LangChain.

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌──────────────┐
│ API Gateway │─────▶│   Lambda    │─────▶│ AWS Bedrock  │
│ (x-api-key) │      │   Handler   │      │   (Claude)   │
└─────────────┘      └─────────────┘      └──────────────┘
                            │
                            ├─────▶ Search APIs (Brave/SerpAPI/DuckDuckGo)
                            ├─────▶ Web Scraper (AsyncHtmlLoader)
                            ├─────▶ Text Chunker & Ranker
                            └─────▶ Bedrock Embeddings (Titan)
```

## Features

- **Multiple Search Providers**: Brave Search, SerpAPI, or free DuckDuckGo fallback
- **Intelligent Scraping**: Rate-limited concurrent scraping with error handling
- **Semantic Ranking**: AWS Bedrock Titan embeddings for relevance ranking
- **LLM Answer Generation**: Claude 3 Haiku for fast, accurate responses
- **API Key Protection**: API Gateway with x-api-key requirement
- **Modular Design**: Clean class-based architecture with separation of concerns

## Project Structure

```
websearch-llm/
├── template.yaml              # SAM template
├── README.md                  # This file
├── samconfig.toml            # SAM configuration (generated)
└── src/
    ├── app.py                # Main Lambda handler
    ├── search_service.py     # Search API integration
    ├── scraper_service.py    # Web scraping
    ├── text_processor.py     # Chunking and ranking
    ├── bedrock_service.py    # AWS Bedrock LLM
    └── requirements.txt      # Python dependencies
```

## Prerequisites

1. **AWS CLI** configured with credentials
2. **AWS SAM CLI** installed ([installation guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
3. **Python 3.12** or later
4. **Docker** (for local testing)
5. **AWS Bedrock Access**: Enable Claude 3 models in your AWS account

### Enable AWS Bedrock Models

```bash
# Navigate to AWS Console → Bedrock → Model Access
# Request access to:
# - Anthropic Claude 3 Haiku
# - Amazon Titan Embeddings
```

## Installation & Deployment

### 1. Clone and Setup

```bash
cd websearch-llm
```

### 2. Configure Parameters

Edit `template.yaml` or use SAM CLI parameters:

- `TargetDomain`: Domain to search (e.g., `docs.aws.amazon.com`)
- `GoogleApiKey`: (Optional) Google Custom Search API key
- `GoogleSearchEngineId`: (Optional) Google Search Engine ID
- `BedrockModelId`: Bedrock model (default: Claude 3 Haiku)
- `MaxConcurrentRequests`: Scraping rate limit (default: 3)

### 3. Build

```bash
sam build
```

### 4. Deploy

```bash
sam deploy --guided
```

Follow the prompts:
- **Stack Name**: `websearch-llm`
- **AWS Region**: Your preferred region (e.g., `us-east-1`)
- **Parameter TargetDomain**: Your target domain
- **Confirm changes before deploy**: Y
- **Allow SAM CLI IAM role creation**: Y
- **Save arguments to configuration file**: Y

### 5. Get API Key

After deployment, retrieve your API key:

```bash
# Get API Key ID from stack outputs
aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`WebSearchApiKey`].OutputValue' \
  --output text

# Get actual API key value
aws apigateway get-api-key \
  --api-key <API_KEY_ID> \
  --include-value \
  --query 'value' \
  --output text
```

## Usage

### API Endpoint

```
POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/search
```

### Request Format

**Headers:**
```
Content-Type: application/json
x-api-key: <your-api-key>
```

**Body:**
```json
{
  "query": "What are the AWS Lambda pricing details?",
  "max_results": 5,
  "max_chunks": 10
}
```

### Response Format

```json
{
  "answer": "AWS Lambda pricing is based on...",
  "sources": [
    "https://aws.amazon.com/lambda/pricing/",
    "https://docs.aws.amazon.com/lambda/..."
  ],
  "metadata": {
    "chunks_processed": 8,
    "urls_scraped": 3,
    "total_time_ms": 2847
  }
}
```

### Example with cURL

```bash
curl -X POST \
  https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/search \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key-here" \
  -d '{
    "query": "What are the best practices for Lambda performance?",
    "max_results": 5,
    "max_chunks": 10
  }'
```

### Example with Python

```python
import requests
import json

url = "https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/search"
headers = {
    "Content-Type": "application/json",
    "x-api-key": "your-api-key-here"
}
payload = {
    "query": "How do I optimize Lambda cold starts?",
    "max_results": 5,
    "max_chunks": 10
}

response = requests.post(url, headers=headers, json=payload)
result = response.json()

print(f"Answer: {result['answer']}")
print(f"Sources: {', '.join(result['sources'])}")
```

## Configuration

### Search API Keys (Optional)

Set these in `template.yaml` parameters or as Lambda environment variables:

- **BRAVE_API_KEY**: [Get key here](https://brave.com/search/api/)
- **SERPAPI_KEY**: [Get key here](https://serpapi.com/)

If none are set, the function falls back to free DuckDuckGo search.

### AWS Region

Default is `us-east-1`. Change in `template.yaml` Globals or set `AWS_REGION` environment variable.

### Model Configuration

Change Bedrock model in `template.yaml`:

```yaml
BedrockModelId:
  Type: String
  Default: anthropic.claude-3-haiku-20240307-v1:0  # Fast, cheap
  # Alternative: anthropic.claude-3-sonnet-20240229-v1:0  # More capable
  # Alternative: anthropic.claude-3-5-sonnet-20240620-v1:0  # Most capable
```

## Local Testing

### Test Locally with SAM

```bash
# Start local API
sam local start-api

# Test with curl
curl -X POST http://127.0.0.1:3000/search \
  -H "Content-Type: application/json" \
  -H "x-api-key: test-key" \
  -d '{"query": "test query"}'
```

### Unit Tests

```bash
cd src
python -m pytest tests/
```

## Cost Estimation

For 1000 requests/month with average configuration:

- **Lambda**: ~$2.50 (1536MB, 5s avg duration)
- **Bedrock Claude Haiku**: ~$1.50 (input + output tokens)
- **Bedrock Titan Embeddings**: ~$0.50
- **API Gateway**: ~$3.50
- **Search API** (if using paid):
  - Brave: $5-10
  - SerpAPI: $50-100
- **Total**: ~$8/month (with free DuckDuckGo) or $13-113/month (with paid search)

## Performance

- **Cold Start**: ~2-3s (first invocation)
- **Warm Start**: ~1-3s (subsequent invocations)
- **Typical Response Time**: 2-5s total

### Optimization Tips

1. **Increase Lambda memory**: Higher memory = faster CPU
2. **Use Claude Haiku**: Faster than Sonnet/Opus
3. **Reduce max_chunks**: Fewer chunks = faster processing
4. **Enable CloudWatch Logs filtering**: Reduce log volume

## Monitoring

### CloudWatch Logs

```bash
sam logs -n WebSearchLLMFunction --stack-name websearch-llm --tail
```

### CloudWatch Metrics

- Lambda Duration
- Lambda Errors
- API Gateway 4XX/5XX
- Bedrock Invocations

## Troubleshooting

### "No module named 'langchain'"

Rebuild with dependencies:
```bash
sam build --use-container
```

### "Access Denied" from Bedrock

Enable model access in Bedrock console:
```
AWS Console → Bedrock → Model Access → Request Access
```

### "Rate limit exceeded"

Adjust `MaxConcurrentRequests` parameter or implement exponential backoff in `search_service.py`.

### API Gateway 403 Forbidden

Check API key is correct and included in `x-api-key` header.

## Cleanup

```bash
sam delete --stack-name websearch-llm
```

## Advanced Configuration

### Custom Prompt Template

Modify `bedrock_service.py:40-60` to customize the LLM prompt.

### Custom Chunking Strategy

Modify `text_processor.py:26-32` to adjust chunk size and overlap.

### Add Caching

Implement caching layer using ElastiCache or DynamoDB for frequently searched queries.

## Security Considerations

- API keys stored as NoEcho parameters
- IAM role with least privilege (Bedrock invoke only)
- API Gateway rate limiting (5 req/s burst, 1000/day quota)
- SSL/TLS encryption in transit
- Consider adding WAF for production use

## License

MIT

## Support

For issues or questions:
1. Check CloudWatch Logs
2. Review this README
3. Open GitHub issue
