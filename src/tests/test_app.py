"""
Unit tests for Lambda handler and WebSearchLLMHandler class.
Tests end-to-end orchestration and integration.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from langchain.schema import Document
import app
from app import WebSearchLLMHandler, lambda_handler


class TestWebSearchLLMHandler:
    """Test suite for WebSearchLLMHandler class."""

    @pytest.fixture
    def handler(self):
        """Create WebSearchLLMHandler instance for testing."""
        with patch('app.SearchService'), \
             patch('app.ScraperService'), \
             patch('app.TextProcessor'), \
             patch('app.BedrockService'):

            handler = WebSearchLLMHandler()

            # Mock services
            handler.search_service = Mock()
            handler.scraper_service = Mock()
            handler.text_processor = Mock()
            handler.bedrock_service = Mock()

            return handler

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        return [
            Document(
                page_content="Content from page 1",
                metadata={'source': 'https://example.com/page1'}
            ),
            Document(
                page_content="Content from page 2",
                metadata={'source': 'https://example.com/page2'}
            )
        ]

    def test_init(self, handler):
        """Test WebSearchLLMHandler initialization."""
        assert handler.search_service is not None
        assert handler.scraper_service is not None
        assert handler.text_processor is not None
        assert handler.bedrock_service is not None

    def test_process_query_success(self, handler, sample_documents):
        """Test successful query processing."""
        # Mock service responses
        handler.search_service.search.return_value = [
            'https://example.com/page1',
            'https://example.com/page2'
        ]
        handler.scraper_service.scrape_urls.return_value = sample_documents
        handler.text_processor.chunk_documents.return_value = [
            Document(page_content="Chunk 1", metadata={'source': 'url1'}),
            Document(page_content="Chunk 2", metadata={'source': 'url2'})
        ]
        handler.text_processor.rank_chunks.return_value = (
            [Document(page_content="Chunk 1", metadata={'source': 'url1'})],
            [0.85]
        )
        handler.text_processor.format_chunks_for_context.return_value = "Formatted context"
        handler.bedrock_service.generate_answer.return_value = "Generated answer"

        # Execute
        result = handler.process_query("test query", max_results=5, max_chunks=10)

        # Assert
        assert result['answer'] == "Generated answer"
        assert len(result['sources']) > 0
        assert 'metadata' in result
        assert result['metadata']['chunks_processed'] == 1
        assert result['metadata']['urls_scraped'] == 2
        # Check for source_details
        assert 'source_details' in result
        assert len(result['source_details']) == 1
        assert result['source_details'][0]['rank'] == 1
        assert result['source_details'][0]['similarity_score'] == 0.85
        assert 'url' in result['source_details'][0]
        assert 'content_preview' in result['source_details'][0]

        # Verify service calls
        handler.search_service.search.assert_called_once_with(
            query="test query",
            target_domain=handler.target_domain,
            max_results=5
        )
        handler.scraper_service.scrape_urls.assert_called_once()
        handler.text_processor.chunk_documents.assert_called_once()
        handler.text_processor.rank_chunks.assert_called_once()
        handler.bedrock_service.generate_answer.assert_called_once()

    def test_process_query_no_search_results(self, handler):
        """Test query processing when search returns no results."""
        handler.search_service.search.return_value = []

        result = handler.process_query("test query")

        assert "No relevant search results" in result['answer']
        assert result['sources'] == []
        assert result['metadata']['urls_scraped'] == 0
        assert result['metadata']['chunks_processed'] == 0

    def test_process_query_scraping_fails(self, handler):
        """Test query processing when scraping fails."""
        handler.search_service.search.return_value = ['url1', 'url2']
        handler.scraper_service.scrape_urls.return_value = []

        result = handler.process_query("test query")

        assert "Unable to retrieve content" in result['answer']
        assert len(result['sources']) == 2  # URLs are still returned
        assert result['metadata']['urls_scraped'] == 0

    def test_process_query_custom_params(self, handler, sample_documents):
        """Test query processing with custom parameters."""
        handler.search_service.search.return_value = ['url1']
        handler.scraper_service.scrape_urls.return_value = sample_documents
        handler.text_processor.chunk_documents.return_value = [
            Document(page_content=f"Chunk {i}", metadata={'source': f'url{i}'})
            for i in range(20)
        ]
        handler.text_processor.rank_chunks.return_value = (
            [Document(page_content="Chunk", metadata={'source': 'url1'})],
            [0.75]
        )
        handler.text_processor.format_chunks_for_context.return_value = "Context"
        handler.bedrock_service.generate_answer.return_value = "Answer"

        result = handler.process_query("query", max_results=3, max_chunks=15)

        # Verify custom params were passed
        handler.search_service.search.assert_called_with(
            query="query",
            target_domain=handler.target_domain,
            max_results=3
        )
        handler.text_processor.rank_chunks.assert_called_with(
            chunks=handler.text_processor.chunk_documents.return_value,
            query="query",
            max_chunks=15
        )
        # Verify source_details exist
        assert 'source_details' in result
        assert len(result['source_details']) == 1

    def test_process_query_timing_metadata(self, handler, sample_documents):
        """Test that timing metadata is included in response."""
        handler.search_service.search.return_value = ['url1']
        handler.scraper_service.scrape_urls.return_value = sample_documents
        handler.text_processor.chunk_documents.return_value = [
            Document(page_content="Chunk", metadata={'source': 'url1'})
        ]
        handler.text_processor.rank_chunks.return_value = (
            [Document(page_content="Chunk", metadata={'source': 'url1'})],
            [0.90]
        )
        handler.text_processor.format_chunks_for_context.return_value = "Context"
        handler.bedrock_service.generate_answer.return_value = "Answer"

        result = handler.process_query("query")

        assert 'total_time_ms' in result['metadata']
        assert isinstance(result['metadata']['total_time_ms'], int)
        assert result['metadata']['total_time_ms'] >= 0
        # Verify source_details exist
        assert 'source_details' in result
        assert len(result['source_details']) == 1

    def test_process_query_unique_sources(self, handler):
        """Test that sources are deduplicated."""
        handler.search_service.search.return_value = ['url1']
        handler.scraper_service.scrape_urls.return_value = [
            Document(page_content="Content", metadata={'source': 'url1'})
        ]
        handler.text_processor.chunk_documents.return_value = [
            Document(page_content="Chunk 1", metadata={'source': 'url1'}),
            Document(page_content="Chunk 2", metadata={'source': 'url1'}),
            Document(page_content="Chunk 3", metadata={'source': 'url2'})
        ]
        handler.text_processor.rank_chunks.return_value = (
            [
                Document(page_content="Chunk 1", metadata={'source': 'url1'}),
                Document(page_content="Chunk 2", metadata={'source': 'url1'}),
                Document(page_content="Chunk 3", metadata={'source': 'url2'})
            ],
            [0.95, 0.92, 0.88]
        )
        handler.text_processor.format_chunks_for_context.return_value = "Context"
        handler.bedrock_service.generate_answer.return_value = "Answer"

        result = handler.process_query("query")

        # Should have unique sources
        assert len(result['sources']) == 2
        assert 'url1' in result['sources']
        assert 'url2' in result['sources']
        # Verify source_details exist and include all chunks
        assert 'source_details' in result
        assert len(result['source_details']) == 3
        assert result['source_details'][0]['similarity_score'] == 0.95


class TestLambdaHandler:
    """Test suite for lambda_handler function."""

    def setUp(self):
        """Reset global handler before each test."""
        app.handler = None

    @pytest.fixture(autouse=True)
    def reset_handler(self):
        """Reset global handler before each test."""
        app.handler = None
        yield
        app.handler = None

    @pytest.fixture
    def lambda_event(self):
        """Create sample Lambda event."""
        return {
            'body': json.dumps({
                'query': 'test query',
                'max_results': 5,
                'max_chunks': 10
            })
        }

    @pytest.fixture
    def lambda_context(self):
        """Create mock Lambda context."""
        context = Mock()
        context.aws_request_id = 'test-request-id'
        return context

    def test_lambda_handler_success(self, lambda_event, lambda_context):
        """Test successful Lambda invocation."""
        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Test answer',
                'sources': ['url1', 'url2'],
                'metadata': {
                    'chunks_processed': 5,
                    'urls_scraped': 2,
                    'total_time_ms': 1000
                }
            }
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(lambda_event, lambda_context)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['answer'] == 'Test answer'
            assert len(body['sources']) == 2
            assert body['metadata']['chunks_processed'] == 5

    def test_lambda_handler_missing_query(self, lambda_context):
        """Test Lambda handler with missing query parameter."""
        event = {'body': json.dumps({})}

        response = lambda_handler(event, lambda_context)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Missing required parameter' in body['error']

    def test_lambda_handler_invalid_json(self, lambda_context):
        """Test Lambda handler with invalid JSON body."""
        event = {'body': 'invalid json'}

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 500

    def test_lambda_handler_missing_body(self, lambda_context):
        """Test Lambda handler with missing body."""
        event = {}

        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400

    def test_lambda_handler_invalid_max_results(self, lambda_context):
        """Test Lambda handler with invalid max_results parameter."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'max_results': 100  # Too high
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'max_results' in body['error']

    def test_lambda_handler_invalid_max_results_negative(self, lambda_context):
        """Test Lambda handler with negative max_results."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'max_results': -1
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400

    def test_lambda_handler_invalid_max_chunks(self, lambda_context):
        """Test Lambda handler with invalid max_chunks parameter."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'max_chunks': 100  # Too high
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'max_chunks' in body['error']

    def test_lambda_handler_invalid_max_chunks_type(self, lambda_context):
        """Test Lambda handler with wrong type for max_chunks."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'max_chunks': "not a number"
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400

    def test_lambda_handler_default_params(self, lambda_context):
        """Test Lambda handler with default parameters."""
        event = {
            'body': json.dumps({'query': 'test query'})
        }

        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Answer',
                'sources': [],
                'metadata': {}
            }
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(event, lambda_context)

            # Verify default params were used (system_prompt is None by default)
            mock_handler.process_query.assert_called_once_with('test query', 5, 10, None)

    def test_lambda_handler_reuses_handler_instance(self, lambda_event, lambda_context):
        """Test that Lambda handler reuses the global handler instance."""
        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Answer',
                'sources': [],
                'metadata': {}
            }
            mock_handler_class.return_value = mock_handler

            # First invocation
            lambda_handler(lambda_event, lambda_context)
            # Second invocation
            lambda_handler(lambda_event, lambda_context)

            # Handler should only be initialized once
            assert mock_handler_class.call_count == 1

    def test_lambda_handler_exception_handling(self, lambda_event, lambda_context):
        """Test Lambda handler exception handling."""
        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.side_effect = Exception("Processing error")
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(lambda_event, lambda_context)

            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert 'error' in body
            assert 'Internal server error' in body['error']

    def test_lambda_handler_content_type_header(self, lambda_event, lambda_context):
        """Test that response includes correct Content-Type header."""
        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Answer',
                'sources': [],
                'metadata': {}
            }
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(lambda_event, lambda_context)

            assert 'headers' in response
            assert response['headers']['Content-Type'] == 'application/json'

    def test_lambda_handler_valid_json_response(self, lambda_event, lambda_context):
        """Test that response body is valid JSON."""
        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Answer',
                'sources': ['url1'],
                'metadata': {'key': 'value'}
            }
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(lambda_event, lambda_context)

            # Should be able to parse response body
            body = json.loads(response['body'])
            assert isinstance(body, dict)

    def test_lambda_handler_with_system_prompt(self, lambda_context):
        """Test Lambda handler with custom system prompt."""
        custom_prompt = "You are helpful.\n\nContext: {context}\n\nQuestion: {query}\n\nAnswer:"
        event = {
            'body': json.dumps({
                'query': 'test query',
                'system_prompt': custom_prompt
            })
        }

        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Custom answer',
                'sources': [],
                'metadata': {}
            }
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 200
            # Verify system_prompt was passed to process_query
            mock_handler.process_query.assert_called_once_with(
                'test query', 5, 10, custom_prompt
            )

    def test_lambda_handler_system_prompt_missing_query_placeholder(self, lambda_context):
        """Test Lambda handler with system prompt missing query placeholder."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'system_prompt': 'Context: {context}\n\nAnswer:'
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'must include {query} and {context} placeholders' in body['error']

    def test_lambda_handler_system_prompt_missing_context_placeholder(self, lambda_context):
        """Test Lambda handler with system prompt missing context placeholder."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'system_prompt': 'Question: {query}\n\nAnswer:'
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'must include {query} and {context} placeholders' in body['error']

    def test_lambda_handler_system_prompt_invalid_type(self, lambda_context):
        """Test Lambda handler with system prompt of wrong type."""
        event = {
            'body': json.dumps({
                'query': 'test',
                'system_prompt': 123  # Should be string
            })
        }

        with patch('app.WebSearchLLMHandler'):
            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'system_prompt must be a string' in body['error']

    def test_lambda_handler_without_system_prompt_uses_default(self, lambda_context):
        """Test Lambda handler without system prompt uses default."""
        event = {
            'body': json.dumps({
                'query': 'test query'
            })
        }

        with patch('app.WebSearchLLMHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.process_query.return_value = {
                'answer': 'Default answer',
                'sources': [],
                'metadata': {}
            }
            mock_handler_class.return_value = mock_handler

            response = lambda_handler(event, lambda_context)

            assert response['statusCode'] == 200
            # Verify system_prompt parameter was None (uses default)
            mock_handler.process_query.assert_called_once_with(
                'test query', 5, 10, None
            )
