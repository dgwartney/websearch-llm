"""
Integration tests for the complete Lambda handler workflow.
Tests end-to-end functionality with realistic scenarios.
"""
import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from langchain.schema import Document

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import lambda_handler, WebSearchLLMHandler


class TestIntegration:
    """Integration tests for complete Lambda workflow."""

    @pytest.fixture(autouse=True)
    def reset_global_handler(self):
        """Reset global handler before each test."""
        import app
        app.handler = None
        yield
        app.handler = None

    @pytest.fixture
    def lambda_context(self):
        """Create mock Lambda context."""
        context = Mock()
        context.aws_request_id = 'test-request-id-123'
        context.function_name = 'websearch-llm-test'
        context.memory_limit_in_mb = 1536
        context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789:function:test'
        return context

    @pytest.fixture
    def sample_search_query_event(self):
        """Create sample API Gateway event."""
        return {
            'body': json.dumps({
                'query': 'What are the benefits of AWS Lambda?',
                'max_results': 3,
                'max_chunks': 5
            }),
            'headers': {
                'Content-Type': 'application/json',
                'x-api-key': 'test-api-key'
            },
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            }
        }

    def test_full_workflow_success(self, sample_search_query_event, lambda_context):
        """Test complete successful workflow from search to answer."""
        with patch('app.SearchService') as MockSearchService, \
             patch('app.ScraperService') as MockScraperService, \
             patch('app.TextProcessor') as MockTextProcessor, \
             patch('app.BedrockService') as MockBedrockService:

            # Setup mocks for full workflow
            mock_search = MockSearchService.return_value
            mock_search.search.return_value = [
                'https://aws.amazon.com/lambda/features/',
                'https://docs.aws.amazon.com/lambda/latest/dg/welcome.html'
            ]

            mock_scraper = MockScraperService.return_value
            mock_scraper.scrape_urls.return_value = [
                Document(
                    page_content="AWS Lambda is a serverless compute service that lets you run code without provisioning or managing servers. It automatically scales and only charges for compute time used.",
                    metadata={'source': 'https://aws.amazon.com/lambda/features/'}
                ),
                Document(
                    page_content="Lambda executes your code only when needed and scales automatically, from a few requests per day to thousands per second.",
                    metadata={'source': 'https://docs.aws.amazon.com/lambda/latest/dg/welcome.html'}
                )
            ]

            mock_text_processor = MockTextProcessor.return_value
            mock_text_processor.chunk_documents.return_value = [
                Document(
                    page_content="AWS Lambda is a serverless compute service.",
                    metadata={'source': 'https://aws.amazon.com/lambda/features/'}
                ),
                Document(
                    page_content="It automatically scales and only charges for compute time used.",
                    metadata={'source': 'https://aws.amazon.com/lambda/features/'}
                )
            ]
            mock_text_processor.rank_chunks.return_value = [
                Document(
                    page_content="AWS Lambda is a serverless compute service.",
                    metadata={'source': 'https://aws.amazon.com/lambda/features/'}
                )
            ]
            mock_text_processor.format_chunks_for_context.return_value = (
                "[Source 1: https://aws.amazon.com/lambda/features/]\n"
                "AWS Lambda is a serverless compute service."
            )

            mock_bedrock = MockBedrockService.return_value
            mock_bedrock.generate_answer.return_value = (
                "AWS Lambda offers several key benefits:\n\n"
                "1. Serverless architecture - No server management required\n"
                "2. Automatic scaling - Scales from zero to thousands of requests\n"
                "3. Pay-per-use pricing - Only pay for compute time consumed\n"
                "4. High availability - Built-in fault tolerance\n\n"
                "According to Source 1, Lambda is a serverless compute service that "
                "automatically scales and charges only for actual compute time used."
            )

            # Execute Lambda handler
            response = lambda_handler(sample_search_query_event, lambda_context)

            # Verify response
            assert response['statusCode'] == 200
            assert 'body' in response

            body = json.loads(response['body'])
            assert 'answer' in body
            assert 'sources' in body
            assert 'metadata' in body

            # Verify answer content
            assert 'serverless' in body['answer'].lower()
            assert 'Lambda' in body['answer']

            # Verify sources
            assert len(body['sources']) > 0
            assert 'aws.amazon.com' in body['sources'][0]

            # Verify metadata
            assert body['metadata']['chunks_processed'] == 1
            assert body['metadata']['urls_scraped'] == 2
            assert 'total_time_ms' in body['metadata']

            # Verify service calls
            mock_search.search.assert_called_once()
            mock_scraper.scrape_urls.assert_called_once()
            mock_text_processor.chunk_documents.assert_called_once()
            mock_text_processor.rank_chunks.assert_called_once()
            mock_bedrock.generate_answer.assert_called_once()

    def test_workflow_with_search_failure(self, sample_search_query_event, lambda_context):
        """Test workflow when search returns no results."""
        with patch('app.SearchService') as MockSearchService, \
             patch('app.ScraperService'), \
             patch('app.TextProcessor'), \
             patch('app.BedrockService'):

            mock_search = MockSearchService.return_value
            mock_search.search.return_value = []  # No search results

            response = lambda_handler(sample_search_query_event, lambda_context)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'No relevant search results' in body['answer']
            assert body['sources'] == []

    def test_workflow_with_scraping_failure(self, sample_search_query_event, lambda_context):
        """Test workflow when scraping fails."""
        with patch('app.SearchService') as MockSearchService, \
             patch('app.ScraperService') as MockScraperService, \
             patch('app.TextProcessor'), \
             patch('app.BedrockService'):

            mock_search = MockSearchService.return_value
            mock_search.search.return_value = ['https://example.com/page1']

            mock_scraper = MockScraperService.return_value
            mock_scraper.scrape_urls.return_value = []  # Scraping failed

            response = lambda_handler(sample_search_query_event, lambda_context)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'Unable to retrieve content' in body['answer']

    def test_workflow_with_different_query_types(self, lambda_context):
        """Test workflow with various query types."""
        test_queries = [
            'How does Lambda pricing work?',
            'What is the maximum timeout for Lambda functions?',
            'Can Lambda functions access VPC resources?'
        ]

        with patch('app.SearchService') as MockSearchService, \
             patch('app.ScraperService') as MockScraperService, \
             patch('app.TextProcessor') as MockTextProcessor, \
             patch('app.BedrockService') as MockBedrockService:

            # Setup basic mocks
            MockSearchService.return_value.search.return_value = ['https://example.com']
            MockScraperService.return_value.scrape_urls.return_value = [
                Document(page_content="Test content " * 20, metadata={'source': 'https://example.com'})
            ]
            MockTextProcessor.return_value.chunk_documents.return_value = [
                Document(page_content="Test chunk", metadata={'source': 'https://example.com'})
            ]
            MockTextProcessor.return_value.rank_chunks.return_value = [
                Document(page_content="Test chunk", metadata={'source': 'https://example.com'})
            ]
            MockTextProcessor.return_value.format_chunks_for_context.return_value = "Context"
            MockBedrockService.return_value.generate_answer.return_value = "Test answer"

            for query in test_queries:
                event = {
                    'body': json.dumps({'query': query})
                }
                response = lambda_handler(event, lambda_context)

                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert 'answer' in body

    def test_performance_metadata(self, sample_search_query_event, lambda_context):
        """Test that performance metadata is tracked correctly."""
        with patch('app.SearchService') as MockSearchService, \
             patch('app.ScraperService') as MockScraperService, \
             patch('app.TextProcessor') as MockTextProcessor, \
             patch('app.BedrockService') as MockBedrockService:

            # Setup mocks
            MockSearchService.return_value.search.return_value = ['url1']
            MockScraperService.return_value.scrape_urls.return_value = [
                Document(page_content="Content " * 20, metadata={'source': 'url1'})
            ]
            MockTextProcessor.return_value.chunk_documents.return_value = [
                Document(page_content="Chunk", metadata={'source': 'url1'})
            ]
            MockTextProcessor.return_value.rank_chunks.return_value = [
                Document(page_content="Chunk", metadata={'source': 'url1'})
            ]
            MockTextProcessor.return_value.format_chunks_for_context.return_value = "Context"
            MockBedrockService.return_value.generate_answer.return_value = "Answer"

            response = lambda_handler(sample_search_query_event, lambda_context)

            body = json.loads(response['body'])
            metadata = body['metadata']

            assert 'total_time_ms' in metadata
            assert isinstance(metadata['total_time_ms'], int)
            assert metadata['total_time_ms'] >= 0
            assert metadata['urls_scraped'] >= 1
            assert metadata['chunks_processed'] >= 1

    def test_handler_instance_reuse(self, sample_search_query_event, lambda_context):
        """Test that handler instance is reused across invocations."""
        import app

        # Reset global handler
        app.handler = None

        with patch('app.SearchService'), \
             patch('app.ScraperService'), \
             patch('app.TextProcessor'), \
             patch('app.BedrockService'), \
             patch('app.WebSearchLLMHandler') as MockHandler:

            mock_instance = Mock()
            mock_instance.process_query.return_value = {
                'answer': 'Test',
                'sources': [],
                'metadata': {}
            }
            MockHandler.return_value = mock_instance

            # First invocation
            lambda_handler(sample_search_query_event, lambda_context)

            # Second invocation
            lambda_handler(sample_search_query_event, lambda_context)

            # Handler should only be created once
            assert MockHandler.call_count == 1

        # Cleanup
        app.handler = None

    def test_error_handling_in_workflow(self, sample_search_query_event, lambda_context):
        """Test error handling throughout the workflow."""
        with patch('app.SearchService') as MockSearchService:
            mock_search = MockSearchService.return_value
            mock_search.search.side_effect = Exception("Search service error")

            response = lambda_handler(sample_search_query_event, lambda_context)

            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert 'error' in body
            assert 'Internal server error' in body['error']

    def test_invalid_request_handling(self, lambda_context):
        """Test handling of invalid requests."""
        invalid_events = [
            {'body': json.dumps({})},  # Missing query
            {'body': 'invalid json'},  # Invalid JSON
            {},  # Missing body
            {'body': json.dumps({'query': 'test', 'max_results': 100})},  # Invalid max_results
        ]

        for event in invalid_events:
            with patch('app.WebSearchLLMHandler'):
                response = lambda_handler(event, lambda_context)
                assert response['statusCode'] in [400, 500]
                body = json.loads(response['body'])
                assert 'error' in body

    def test_source_deduplication(self, sample_search_query_event, lambda_context):
        """Test that duplicate sources are removed."""
        with patch('app.SearchService') as MockSearchService, \
             patch('app.ScraperService') as MockScraperService, \
             patch('app.TextProcessor') as MockTextProcessor, \
             patch('app.BedrockService') as MockBedrockService:

            MockSearchService.return_value.search.return_value = ['url1']
            MockScraperService.return_value.scrape_urls.return_value = [
                Document(page_content="Content " * 20, metadata={'source': 'url1'})
            ]

            # Multiple chunks from same source
            MockTextProcessor.return_value.chunk_documents.return_value = [
                Document(page_content="Chunk 1", metadata={'source': 'url1'}),
                Document(page_content="Chunk 2", metadata={'source': 'url1'}),
                Document(page_content="Chunk 3", metadata={'source': 'url1'})
            ]
            MockTextProcessor.return_value.rank_chunks.return_value = [
                Document(page_content="Chunk 1", metadata={'source': 'url1'}),
                Document(page_content="Chunk 2", metadata={'source': 'url1'})
            ]
            MockTextProcessor.return_value.format_chunks_for_context.return_value = "Context"
            MockBedrockService.return_value.generate_answer.return_value = "Answer"

            response = lambda_handler(sample_search_query_event, lambda_context)
            body = json.loads(response['body'])

            # Should only have one unique source
            assert len(body['sources']) == 1
            assert body['sources'][0] == 'url1'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
