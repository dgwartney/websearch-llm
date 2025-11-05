#!/bin/bash

################################################################################
# WestJet Lambda Search Query Script
#
# This script queries the deployed AWS Lambda function for WestJet information
# using natural language questions.
#
# Usage:
#   ./query-lambda.sh "Your question here"
#   ./query-lambda.sh "What are baggage fees?" --max-results 5
#   ./query-lambda.sh "Check-in policies" --max-chunks 10
#   ./query-lambda.sh "Your question" --system-prompt-path prompt.txt
#
# Options:
#   --max-results NUM         Maximum search results to retrieve (default: 3)
#   --max-chunks NUM          Maximum text chunks to process (default: 5)
#   --system-prompt-path FILE Path to file containing custom system prompt
#   --target-domain DOMAIN    Domain to search (default: from Lambda env)
#   --bedrock-model-id MODEL  Bedrock model ID (default: from Lambda env)
#   --chunk-size NUM          Text chunk size in characters (default: from Lambda env)
#   --chunk-overlap NUM       Chunk overlap in characters (default: from Lambda env)
#   --log-level LEVEL         Log level: DEBUG, INFO, WARNING, ERROR (default: from Lambda env)
#   --help                    Show this help message
################################################################################

# Configuration - Update these values if your deployment changes
API_ENDPOINT="${LAMBDA_API_ENDPOINT:-https://ptk188i3l3.execute-api.us-east-1.amazonaws.com/prod/search}"
API_KEY="${LAMBDA_API_KEY:-}"

# Default values
MAX_RESULTS=3
MAX_CHUNKS=5
QUERY=""
SYSTEM_PROMPT_PATH=""
TARGET_DOMAIN=""
BEDROCK_MODEL_ID=""
CHUNK_SIZE=""
CHUNK_OVERLAP=""
LOG_LEVEL=""

################################################################################
# Functions
################################################################################

show_help() {
    cat << 'EOF'
WestJet Lambda Search Query Script

USAGE:
    ./query-lambda.sh "Your question here" [OPTIONS]

ARGUMENTS:
    query                       The question or search query (required)

OPTIONS:
    --max-results NUM           Maximum search results to retrieve (default: 3)
    --max-chunks NUM            Maximum text chunks to process (default: 5)
    --system-prompt-path FILE   Path to file containing custom system prompt
    --target-domain DOMAIN      Domain to search (e.g., westjet.com)
    --bedrock-model-id MODEL    Bedrock model ID to use
    --chunk-size NUM            Text chunk size in characters (100-10000)
    --chunk-overlap NUM         Chunk overlap in characters (0-1000)
    --log-level LEVEL           Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    --help                      Show this help message

ENVIRONMENT VARIABLES:
    LAMBDA_API_KEY      AWS API Gateway API key (required)
    LAMBDA_API_ENDPOINT API Gateway endpoint URL (optional, has default)

EXAMPLES:
    # Set API key and run query
    export LAMBDA_API_KEY="your-api-key-here"
    ./query-lambda.sh "What are the baggage fees?"

    # Query with custom parameters
    ./query-lambda.sh "Check-in policies" --max-results 5 --max-chunks 10

    # Query with custom system prompt
    ./query-lambda.sh "What are baggage fees?" --system-prompt-path custom_prompt.txt

    # Query with custom domain and model
    ./query-lambda.sh "Pricing info" --target-domain example.com --bedrock-model-id anthropic.claude-3-sonnet-20240229-v1:0

    # Query with custom chunking parameters
    ./query-lambda.sh "Detailed info" --chunk-size 2000 --chunk-overlap 400

    # Pipe to jq for specific fields
    ./query-lambda.sh "Cancellation policy" | jq -r '.answer'

    # Extract just the sources
    ./query-lambda.sh "Baggage fees" | jq -r '.sources[]'

NOTES:
    - Query must be enclosed in quotes if it contains spaces
    - Output is JSON formatted with jq
    - Responses typically take 10-20 seconds depending on content size
    - System prompt file must include {query} and {context} placeholders

EOF
}

################################################################################
# Parse Arguments
################################################################################

if [ $# -eq 0 ]; then
    echo "ERROR: No query provided" >&2
    echo ""
    show_help
    exit 1
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --max-results)
            MAX_RESULTS="$2"
            shift 2
            ;;
        --max-chunks)
            MAX_CHUNKS="$2"
            shift 2
            ;;
        --system-prompt-path)
            SYSTEM_PROMPT_PATH="$2"
            shift 2
            ;;
        --target-domain)
            TARGET_DOMAIN="$2"
            shift 2
            ;;
        --bedrock-model-id)
            BEDROCK_MODEL_ID="$2"
            shift 2
            ;;
        --chunk-size)
            CHUNK_SIZE="$2"
            shift 2
            ;;
        --chunk-overlap)
            CHUNK_OVERLAP="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            show_help
            exit 1
            ;;
        *)
            if [ -z "$QUERY" ]; then
                QUERY="$1"
            else
                echo "ERROR: Multiple queries provided. Please enclose your query in quotes." >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate query
if [ -z "$QUERY" ]; then
    echo "ERROR: Query cannot be empty" >&2
    show_help
    exit 1
fi

# Validate numeric parameters
if ! [[ "$MAX_RESULTS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: max-results must be a number" >&2
    exit 1
fi

if ! [[ "$MAX_CHUNKS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: max-chunks must be a number" >&2
    exit 1
fi

# Validate chunk-size if provided
if [ -n "$CHUNK_SIZE" ]; then
    if ! [[ "$CHUNK_SIZE" =~ ^[0-9]+$ ]]; then
        echo "ERROR: chunk-size must be a number" >&2
        exit 1
    fi
    if [ "$CHUNK_SIZE" -lt 100 ] || [ "$CHUNK_SIZE" -gt 10000 ]; then
        echo "ERROR: chunk-size must be between 100 and 10000" >&2
        exit 1
    fi
fi

# Validate chunk-overlap if provided
if [ -n "$CHUNK_OVERLAP" ]; then
    if ! [[ "$CHUNK_OVERLAP" =~ ^[0-9]+$ ]]; then
        echo "ERROR: chunk-overlap must be a number" >&2
        exit 1
    fi
    if [ "$CHUNK_OVERLAP" -lt 0 ] || [ "$CHUNK_OVERLAP" -gt 1000 ]; then
        echo "ERROR: chunk-overlap must be between 0 and 1000" >&2
        exit 1
    fi
    # Check if both chunk_size and chunk_overlap are provided
    if [ -n "$CHUNK_SIZE" ] && [ "$CHUNK_OVERLAP" -ge "$CHUNK_SIZE" ]; then
        echo "ERROR: chunk-overlap must be less than chunk-size" >&2
        exit 1
    fi
fi

# Validate log-level if provided
if [ -n "$LOG_LEVEL" ]; then
    LOG_LEVEL_UPPER=$(echo "$LOG_LEVEL" | tr '[:lower:]' '[:upper:]')
    case "$LOG_LEVEL_UPPER" in
        DEBUG|INFO|WARNING|ERROR|CRITICAL)
            LOG_LEVEL="$LOG_LEVEL_UPPER"
            ;;
        *)
            echo "ERROR: log-level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL" >&2
            exit 1
            ;;
    esac
fi

# Validate system prompt file if provided
if [ -n "$SYSTEM_PROMPT_PATH" ]; then
    if [ ! -f "$SYSTEM_PROMPT_PATH" ]; then
        echo "ERROR: System prompt file not found: $SYSTEM_PROMPT_PATH" >&2
        exit 1
    fi
    if [ ! -r "$SYSTEM_PROMPT_PATH" ]; then
        echo "ERROR: System prompt file is not readable: $SYSTEM_PROMPT_PATH" >&2
        exit 1
    fi
    # Read and validate system prompt contains required placeholders
    SYSTEM_PROMPT_CONTENT=$(cat "$SYSTEM_PROMPT_PATH")
    if [[ ! "$SYSTEM_PROMPT_CONTENT" =~ \{query\} ]]; then
        echo "ERROR: System prompt must include {query} placeholder" >&2
        exit 1
    fi
    if [[ ! "$SYSTEM_PROMPT_CONTENT" =~ \{context\} ]]; then
        echo "ERROR: System prompt must include {context} placeholder" >&2
        exit 1
    fi
fi

################################################################################
# Execute Query
################################################################################

# Validate API key is set
if [ -z "$API_KEY" ]; then
    echo "ERROR: LAMBDA_API_KEY environment variable is not set" >&2
    echo "" >&2
    echo "Please set the API key:" >&2
    echo "  export LAMBDA_API_KEY=\"your-api-key-here\"" >&2
    echo "" >&2
    echo "Run './query-lambda.sh --help' for more information" >&2
    exit 1
fi

# Build JSON payload
# Start with base payload
JSON_PAYLOAD=$(cat <<EOF
{
  "query": "$QUERY",
  "max_results": $MAX_RESULTS,
  "max_chunks": $MAX_CHUNKS
}
EOF
)

# Add optional parameters if provided
if [ -n "$SYSTEM_PROMPT_PATH" ]; then
    SYSTEM_PROMPT_JSON=$(jq -Rs . < "$SYSTEM_PROMPT_PATH")
    JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --argjson sp "$SYSTEM_PROMPT_JSON" '. + {system_prompt: $sp}')
fi

if [ -n "$TARGET_DOMAIN" ]; then
    JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --arg td "$TARGET_DOMAIN" '. + {target_domain: $td}')
fi

if [ -n "$BEDROCK_MODEL_ID" ]; then
    JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --arg bm "$BEDROCK_MODEL_ID" '. + {bedrock_model_id: $bm}')
fi

if [ -n "$CHUNK_SIZE" ]; then
    JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --argjson cs "$CHUNK_SIZE" '. + {chunk_size: $cs}')
fi

if [ -n "$CHUNK_OVERLAP" ]; then
    JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --argjson co "$CHUNK_OVERLAP" '. + {chunk_overlap: $co}')
fi

if [ -n "$LOG_LEVEL" ]; then
    JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --arg ll "$LOG_LEVEL" '. + {log_level: $ll}')
fi

# Execute curl request and pipe to jq for formatting
curl -s -X POST "$API_ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "X-Api-Key: $API_KEY" \
    -d "$JSON_PAYLOAD" | jq '.answer' | sed 's/^"\(.*\)"$/\1/'
