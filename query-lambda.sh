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
#
# Options:
#   --max-results NUM    Maximum search results to retrieve (default: 3)
#   --max-chunks NUM     Maximum text chunks to process (default: 5)
#   --help              Show this help message
################################################################################

# Configuration - Update these values if your deployment changes
API_ENDPOINT="${LAMBDA_API_ENDPOINT:-https://3a74ziw298.execute-api.us-east-1.amazonaws.com/prod/search}"
API_KEY="${LAMBDA_API_KEY:-}"

# Default values
MAX_RESULTS=3
MAX_CHUNKS=5
QUERY=""

################################################################################
# Functions
################################################################################

show_help() {
    cat << 'EOF'
WestJet Lambda Search Query Script

USAGE:
    ./query-lambda.sh "Your question here" [OPTIONS]

ARGUMENTS:
    query               The question or search query (required)

OPTIONS:
    --max-results NUM   Maximum search results to retrieve (default: 3)
    --max-chunks NUM    Maximum text chunks to process (default: 5)
    --help             Show this help message

ENVIRONMENT VARIABLES:
    LAMBDA_API_KEY      AWS API Gateway API key (required)
    LAMBDA_API_ENDPOINT API Gateway endpoint URL (optional, has default)

EXAMPLES:
    # Set API key and run query
    export LAMBDA_API_KEY="your-api-key-here"
    ./query-lambda.sh "What are the baggage fees?"

    # Query with custom parameters
    ./query-lambda.sh "Check-in policies" --max-results 5 --max-chunks 10

    # Pipe to jq for specific fields
    ./query-lambda.sh "Cancellation policy" | jq -r '.answer'

    # Extract just the sources
    ./query-lambda.sh "Baggage fees" | jq -r '.sources[]'

NOTES:
    - Query must be enclosed in quotes if it contains spaces
    - Output is JSON formatted with jq
    - Responses typically take 10-20 seconds depending on content size

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
JSON_PAYLOAD=$(cat <<EOF
{
  "query": "$QUERY",
  "max_results": $MAX_RESULTS,
  "max_chunks": $MAX_CHUNKS
}
EOF
)

# Execute curl request and pipe to jq for formatting
curl -s -X POST "$API_ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "X-Api-Key: $API_KEY" \
    -d "$JSON_PAYLOAD" | jq '.'
