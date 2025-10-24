"""
Unit tests for SearchService class.
Tests all search providers: Brave, SerpAPI, and DuckDuckGo.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from search_service import SearchService


class TestSearchService:
    """Test suite for SearchService class."""

    @pytest.fixture
    def search_service(self):
        """Create SearchService instance for testing."""
        return SearchService(
            brave_api_key="test_brave_key",
            serpapi_key="test_serp_key",
            timeout=5
        )

    @pytest.fixture
    def search_service_no_keys(self):
        """Create SearchService without API keys (DuckDuckGo only)."""
        return SearchService()

    def test_init_with_keys(self, search_service):
        """Test initialization with API keys."""
        assert search_service.brave_api_key == "test_brave_key"
        assert search_service.serpapi_key == "test_serp_key"
        assert search_service.timeout == 5

    def test_init_without_keys(self, search_service_no_keys):
        """Test initialization without API keys."""
        assert search_service_no_keys.brave_api_key is None
        assert search_service_no_keys.serpapi_key is None
        assert search_service_no_keys.timeout == 5

    @patch('search_service.requests.get')
    def test_search_brave_success(self, mock_get, search_service):
        """Test successful Brave Search API call."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            'web': {
                'results': [
                    {'url': 'https://example.com/page1'},
                    {'url': 'https://example.com/page2'},
                    {'url': 'https://example.com/page3'}
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Execute
        urls = search_service._search_brave("test query", "example.com", 5)

        # Assert
        assert len(urls) == 3
        assert urls[0] == 'https://example.com/page1'
        assert urls[1] == 'https://example.com/page2'
        mock_get.assert_called_once()

        # Verify request parameters
        call_args = mock_get.call_args
        assert call_args[1]['headers']['X-Subscription-Token'] == 'test_brave_key'
        assert call_args[1]['params']['q'] == 'test query site:example.com'
        assert call_args[1]['timeout'] == 5

    @patch('search_service.requests.get')
    def test_search_brave_api_error(self, mock_get, search_service):
        """Test Brave Search API error handling."""
        # Mock exception
        mock_get.side_effect = Exception("API Error")

        # Execute
        urls = search_service._search_brave("test query", "example.com", 5)

        # Assert returns empty list on error
        assert urls == []

    @patch('search_service.requests.get')
    def test_search_brave_empty_results(self, mock_get, search_service):
        """Test Brave Search with empty results."""
        mock_response = Mock()
        mock_response.json.return_value = {'web': {'results': []}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        urls = search_service._search_brave("test query", "example.com", 5)

        assert urls == []

    @patch('search_service.requests.get')
    def test_search_brave_max_results_limit(self, mock_get, search_service):
        """Test Brave Search respects max_results limit."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'web': {
                'results': [
                    {'url': f'https://example.com/page{i}'}
                    for i in range(10)
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        urls = search_service._search_brave("test query", "example.com", 3)

        # Should only return 3 results
        assert len(urls) == 3

    @patch('search_service.requests.get')
    def test_search_serpapi_success(self, mock_get, search_service):
        """Test successful SerpAPI call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'organic_results': [
                {'link': 'https://example.com/page1'},
                {'link': 'https://example.com/page2'}
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        urls = search_service._search_serpapi("test query", "example.com", 5)

        assert len(urls) == 2
        assert urls[0] == 'https://example.com/page1'

        # Verify API key in params
        call_args = mock_get.call_args
        assert call_args[1]['params']['api_key'] == 'test_serp_key'
        assert call_args[1]['params']['q'] == 'test query site:example.com'

    @patch('search_service.requests.get')
    def test_search_serpapi_error(self, mock_get, search_service):
        """Test SerpAPI error handling."""
        mock_get.side_effect = Exception("SerpAPI Error")

        urls = search_service._search_serpapi("test query", "example.com", 5)

        assert urls == []

    @patch('duckduckgo_search.DDGS')
    def test_search_duckduckgo_success(self, mock_ddgs, search_service):
        """Test successful DuckDuckGo search."""
        # Mock DuckDuckGo results
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value.text.return_value = [
            {'href': 'https://example.com/page1', 'title': 'Page 1'},
            {'href': 'https://example.com/page2', 'title': 'Page 2'}
        ]
        mock_ddgs.return_value = mock_instance

        urls = search_service._search_duckduckgo("test query", "example.com", 5)

        assert len(urls) == 2
        assert urls[0] == 'https://example.com/page1'
        assert urls[1] == 'https://example.com/page2'

    @patch('duckduckgo_search.DDGS')
    def test_search_duckduckgo_error(self, mock_ddgs, search_service):
        """Test DuckDuckGo error handling."""
        mock_ddgs.side_effect = Exception("DuckDuckGo Error")

        urls = search_service._search_duckduckgo("test query", "example.com", 5)

        assert urls == []

    @patch('duckduckgo_search.DDGS')
    def test_search_duckduckgo_max_results(self, mock_ddgs, search_service):
        """Test DuckDuckGo respects max_results."""
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value.text.return_value = [
            {'href': f'https://example.com/page{i}'}
            for i in range(10)
        ]
        mock_ddgs.return_value = mock_instance

        urls = search_service._search_duckduckgo("test query", "example.com", 3)

        assert len(urls) == 3

    @patch.object(SearchService, '_search_brave')
    def test_search_uses_brave_first(self, mock_brave, search_service):
        """Test that search() tries Brave API first when available."""
        mock_brave.return_value = ['https://example.com/page1']

        urls = search_service.search("test query", "example.com", 5)

        mock_brave.assert_called_once_with("test query", "example.com", 5)
        assert urls == ['https://example.com/page1']

    @patch.object(SearchService, '_search_brave')
    @patch.object(SearchService, '_search_serpapi')
    def test_search_fallback_to_serpapi(self, mock_serp, mock_brave, search_service):
        """Test fallback to SerpAPI when Brave fails."""
        mock_brave.return_value = []  # Brave returns empty
        mock_serp.return_value = ['https://example.com/page1']

        urls = search_service.search("test query", "example.com", 5)

        mock_brave.assert_called_once()
        mock_serp.assert_called_once_with("test query", "example.com", 5)
        assert urls == ['https://example.com/page1']

    @patch.object(SearchService, '_search_brave')
    @patch.object(SearchService, '_search_serpapi')
    @patch.object(SearchService, '_search_duckduckgo')
    def test_search_fallback_to_duckduckgo(
        self, mock_ddg, mock_serp, mock_brave, search_service
    ):
        """Test fallback to DuckDuckGo when Brave and SerpAPI fail."""
        mock_brave.return_value = []
        mock_serp.return_value = []
        mock_ddg.return_value = ['https://example.com/page1']

        urls = search_service.search("test query", "example.com", 5)

        mock_brave.assert_called_once()
        mock_serp.assert_called_once()
        mock_ddg.assert_called_once_with("test query", "example.com", 5)
        assert urls == ['https://example.com/page1']

    @patch.object(SearchService, '_search_duckduckgo')
    def test_search_no_api_keys_uses_duckduckgo(
        self, mock_ddg, search_service_no_keys
    ):
        """Test that search uses DuckDuckGo when no API keys configured."""
        mock_ddg.return_value = ['https://example.com/page1']

        urls = search_service_no_keys.search("test query", "example.com", 5)

        mock_ddg.assert_called_once()
        assert urls == ['https://example.com/page1']

    @patch('search_service.requests.get')
    def test_search_brave_malformed_response(self, mock_get, search_service):
        """Test Brave Search with malformed JSON response."""
        mock_response = Mock()
        mock_response.json.return_value = {'unexpected': 'format'}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        urls = search_service._search_brave("test query", "example.com", 5)

        assert urls == []

    @patch('search_service.requests.get')
    def test_search_serpapi_malformed_response(self, mock_get, search_service):
        """Test SerpAPI with malformed response."""
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        urls = search_service._search_serpapi("test query", "example.com", 5)

        assert urls == []

    @patch('duckduckgo_search.DDGS')
    def test_search_duckduckgo_missing_href(self, mock_ddgs, search_service):
        """Test DuckDuckGo with results missing href field."""
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value.text.return_value = [
            {'title': 'No href'},
            {'href': 'https://example.com/page1'},
        ]
        mock_ddgs.return_value = mock_instance

        urls = search_service._search_duckduckgo("test query", "example.com", 5)

        # Should only include result with href
        assert len(urls) == 1
        assert urls[0] == 'https://example.com/page1'
