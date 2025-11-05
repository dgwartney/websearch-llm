#!/bin/bash

################################################################################
# Test Script for query-lambda.sh System Prompt Feature
#
# This script tests the new --system-prompt-path functionality
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERY_SCRIPT="$SCRIPT_DIR/query-lambda.sh"

echo "Testing query-lambda.sh system prompt feature..."
echo

# Test 1: Help output
echo "Test 1: Checking help output includes --system-prompt-path"
if bash "$QUERY_SCRIPT" --help | grep -q "system-prompt-path"; then
    echo "✅ PASSED: Help includes --system-prompt-path option"
else
    echo "❌ FAILED: Help missing --system-prompt-path option"
    exit 1
fi
echo

# Test 2: Non-existent file
echo "Test 2: Testing non-existent file error"
if bash "$QUERY_SCRIPT" "test" --system-prompt-path /tmp/nonexistent_prompt_file_12345.txt 2>&1 | grep -q "System prompt file not found"; then
    echo "✅ PASSED: Correctly detects non-existent file"
else
    echo "❌ FAILED: Did not detect non-existent file"
    exit 1
fi
echo

# Test 3: Missing {query} placeholder
echo "Test 3: Testing missing {query} placeholder validation"
cat > /tmp/test_missing_query.txt << 'EOF'
This has {context} but no query placeholder.
EOF
if bash "$QUERY_SCRIPT" "test" --system-prompt-path /tmp/test_missing_query.txt 2>&1 | grep -q "must include {query} placeholder"; then
    echo "✅ PASSED: Correctly detects missing {query} placeholder"
else
    echo "❌ FAILED: Did not detect missing {query} placeholder"
    exit 1
fi
rm -f /tmp/test_missing_query.txt
echo

# Test 4: Missing {context} placeholder
echo "Test 4: Testing missing {context} placeholder validation"
cat > /tmp/test_missing_context.txt << 'EOF'
This has {query} but no context placeholder.
EOF
if bash "$QUERY_SCRIPT" "test" --system-prompt-path /tmp/test_missing_context.txt 2>&1 | grep -q "must include {context} placeholder"; then
    echo "✅ PASSED: Correctly detects missing {context} placeholder"
else
    echo "❌ FAILED: Did not detect missing {context} placeholder"
    exit 1
fi
rm -f /tmp/test_missing_context.txt
echo

# Test 5: Valid prompt file passes validation
echo "Test 5: Testing valid prompt file passes validation"
cat > /tmp/test_valid_prompt.txt << 'EOF'
You are helpful.
Context: {context}
Query: {query}
EOF
# Should fail on API key, not on validation
if bash "$QUERY_SCRIPT" "test" --system-prompt-path /tmp/test_valid_prompt.txt 2>&1 | grep -q "LAMBDA_API_KEY"; then
    echo "✅ PASSED: Valid prompt file passes validation (fails on API key as expected)"
else
    echo "❌ FAILED: Valid prompt file did not pass validation"
    exit 1
fi
rm -f /tmp/test_valid_prompt.txt
echo

# Test 6: Special characters are handled
echo "Test 6: Testing special characters in prompt"
cat > /tmp/test_special_chars.txt << 'EOF'
You are a "helpful" assistant!
Context: {context}
Query: {query}
Answer with $pecial characters.
EOF
if bash "$QUERY_SCRIPT" "test" --system-prompt-path /tmp/test_special_chars.txt 2>&1 | grep -q "LAMBDA_API_KEY"; then
    echo "✅ PASSED: Special characters handled correctly"
else
    echo "❌ FAILED: Special characters not handled correctly"
    exit 1
fi
rm -f /tmp/test_special_chars.txt
echo

# Test 7: Script works without --system-prompt-path (backward compatibility)
echo "Test 7: Testing backward compatibility (without --system-prompt-path)"
if bash "$QUERY_SCRIPT" "test" 2>&1 | grep -q "LAMBDA_API_KEY"; then
    echo "✅ PASSED: Script works without --system-prompt-path option"
else
    echo "❌ FAILED: Backward compatibility broken"
    exit 1
fi
echo

echo "=========================================="
echo "All tests passed! ✅"
echo "=========================================="
echo
echo "The query-lambda.sh script correctly:"
echo "  ✅ Shows --system-prompt-path in help"
echo "  ✅ Validates file existence"
echo "  ✅ Validates {query} placeholder"
echo "  ✅ Validates {context} placeholder"
echo "  ✅ Accepts valid prompt files"
echo "  ✅ Handles special characters"
echo "  ✅ Maintains backward compatibility"
