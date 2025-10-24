"""
Unit tests for ScraperService class.
Tests web scraping functionality with LangChain.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain.schema import Document
from scraper_service import ScraperService


class TestScraperService:
    """Test suite for ScraperService class."""

    @pytest.fixture
    def scraper_service(self):
        """Create ScraperService instance for testing."""
        return ScraperService(
            max_concurrent=3,
            verify_ssl=True,
            min_content_length=100
        )

    @pytest.fixture
    def sample_documents(self):
        """Create sample LangChain documents for testing."""
        return [
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement. It has more than 100 characters.",
                metadata={'source': 'https://example.com/page1'}
            ),
            Document(
                page_content="Another valid document with enough content to pass the minimum length requirement and testing purposes here.",
                metadata={'source': 'https://example.com/page2'}
            )
        ]

    def test_init(self, scraper_service):
        """Test initialization with default parameters."""
        assert scraper_service.max_concurrent == 3
        assert scraper_service.verify_ssl is True
        assert scraper_service.min_content_length == 100
        assert scraper_service.html_transformer is not None

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        service = ScraperService(
            max_concurrent=5,
            verify_ssl=False,
            min_content_length=200
        )
        assert service.max_concurrent == 5
        assert service.verify_ssl is False
        assert service.min_content_length == 200

    @patch('scraper_service.AsyncHtmlLoader')
    def test_scrape_urls_success(self, mock_loader_class, scraper_service, sample_documents):
        """Test successful URL scraping."""
        # Mock loader
        mock_loader = Mock()
        mock_loader.load.return_value = sample_documents
        mock_loader_class.return_value = mock_loader

        # Mock transformer
        with patch.object(scraper_service.html_transformer, 'transform_documents') as mock_transform:
            mock_transform.return_value = sample_documents

            # Execute
            urls = ['https://example.com/page1', 'https://example.com/page2']
            result = scraper_service.scrape_urls(urls)

            # Assert
            assert len(result) == 2
            assert result[0].page_content == sample_documents[0].page_content
            mock_loader_class.assert_called_once_with(
                urls,
                verify_ssl=True,
                requests_per_second=3
            )
            mock_loader.load.assert_called_once()
            mock_transform.assert_called_once()

    def test_scrape_urls_empty_list(self, scraper_service):
        """Test scraping with empty URL list."""
        result = scraper_service.scrape_urls([])
        assert result == []

    @patch('scraper_service.AsyncHtmlLoader')
    def test_scrape_urls_loader_exception(self, mock_loader_class, scraper_service):
        """Test handling of loader exceptions."""
        mock_loader = Mock()
        mock_loader.load.side_effect = Exception("Network error")
        mock_loader_class.return_value = mock_loader

        urls = ['https://example.com/page1']
        result = scraper_service.scrape_urls(urls)

        assert result == []

    @patch('scraper_service.AsyncHtmlLoader')
    def test_scrape_urls_transformer_exception(self, mock_loader_class, scraper_service, sample_documents):
        """Test handling of transformer exceptions."""
        mock_loader = Mock()
        mock_loader.load.return_value = sample_documents
        mock_loader_class.return_value = mock_loader

        with patch.object(scraper_service.html_transformer, 'transform_documents') as mock_transform:
            mock_transform.side_effect = Exception("Transform error")

            urls = ['https://example.com/page1']
            result = scraper_service.scrape_urls(urls)

            assert result == []

    def test_filter_valid_documents_all_valid(self, scraper_service, sample_documents):
        """Test filtering with all valid documents."""
        result = scraper_service._filter_valid_documents(sample_documents)
        assert len(result) == 2

    def test_filter_valid_documents_short_content(self, scraper_service):
        """Test filtering out documents with short content."""
        docs = [
            Document(
                page_content="Too short",
                metadata={'source': 'https://example.com/page1'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and provides useful information for testing.",
                metadata={'source': 'https://example.com/page2'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        # Only the second document should pass
        assert len(result) == 1
        assert result[0].metadata['source'] == 'https://example.com/page2'

    def test_filter_valid_documents_error_page_404(self, scraper_service):
        """Test filtering out 404 error pages."""
        docs = [
            Document(
                page_content="404 Not Found - The page you are looking for does not exist on this server. This is a long enough error message to pass length check.",
                metadata={'source': 'https://example.com/missing'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and has useful information.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        # 404 page should be filtered out
        assert len(result) == 1
        assert result[0].metadata['source'] == 'https://example.com/page1'

    def test_filter_valid_documents_error_page_not_found(self, scraper_service):
        """Test filtering out 'page not found' error pages."""
        docs = [
            Document(
                page_content="Page not found. Please check the URL and try again. This error message is long enough to pass the minimum content length requirement.",
                metadata={'source': 'https://example.com/missing'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and provides useful content.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        assert len(result) == 1
        assert result[0].metadata['source'] == 'https://example.com/page1'

    def test_filter_valid_documents_access_denied(self, scraper_service):
        """Test filtering out 'access denied' pages."""
        docs = [
            Document(
                page_content="Access Denied. You do not have permission to view this page. This error message needs to be longer to pass validation.",
                metadata={'source': 'https://example.com/protected'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and contains useful information.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        assert len(result) == 1

    def test_filter_valid_documents_forbidden(self, scraper_service):
        """Test filtering out 'forbidden' pages."""
        docs = [
            Document(
                page_content="Forbidden - You don't have permission to access this resource. This error message must be sufficiently long to pass validation.",
                metadata={'source': 'https://example.com/forbidden'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and useful content for testing.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        assert len(result) == 1

    def test_filter_valid_documents_all_invalid(self, scraper_service):
        """Test filtering when all documents are invalid."""
        docs = [
            Document(page_content="Short", metadata={'source': 'url1'}),
            Document(page_content="404 not found", metadata={'source': 'url2'}),
        ]

        result = scraper_service._filter_valid_documents(docs)

        assert len(result) == 0

    def test_filter_valid_documents_empty_list(self, scraper_service):
        """Test filtering empty document list."""
        result = scraper_service._filter_valid_documents([])
        assert result == []

    def test_filter_valid_documents_whitespace_only(self, scraper_service):
        """Test filtering documents with only whitespace."""
        docs = [
            Document(
                page_content="   \n\n\t   ",
                metadata={'source': 'https://example.com/empty'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and contains real information.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        # Whitespace-only document should be filtered
        assert len(result) == 1

    def test_filter_valid_documents_case_insensitive_error_detection(self, scraper_service):
        """Test that error detection is case-insensitive."""
        docs = [
            Document(
                page_content="404 NOT FOUND - ERROR - This error message needs to be long enough to pass the minimum content length requirement for testing.",
                metadata={'source': 'https://example.com/error'}
            ),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and provides useful information.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        assert len(result) == 1

    def test_filter_valid_documents_missing_source_metadata(self, scraper_service):
        """Test filtering documents without source metadata."""
        docs = [
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and has useful information for testing purposes.",
                metadata={}
            )
        ]

        result = scraper_service._filter_valid_documents(docs)

        # Should still be valid even without source
        assert len(result) == 1

    @patch('scraper_service.AsyncHtmlLoader')
    def test_scrape_urls_filters_invalid_documents(self, mock_loader_class, scraper_service):
        """Test that scrape_urls filters out invalid documents."""
        invalid_docs = [
            Document(page_content="404 not found - this error message needs to be long enough to pass the minimum content length requirement", metadata={'source': 'url1'}),
            Document(
                page_content="This is a valid document with enough content to pass the minimum length requirement and provides useful information for testing.",
                metadata={'source': 'url2'}
            ),
            Document(page_content="short", metadata={'source': 'url3'}),
        ]

        mock_loader = Mock()
        mock_loader.load.return_value = invalid_docs
        mock_loader_class.return_value = mock_loader

        with patch.object(scraper_service.html_transformer, 'transform_documents') as mock_transform:
            mock_transform.return_value = invalid_docs

            urls = ['url1', 'url2', 'url3']
            result = scraper_service.scrape_urls(urls)

            # Only one valid document should remain
            assert len(result) == 1
            assert result[0].metadata['source'] == 'url2'

    @patch('scraper_service.AsyncHtmlLoader')
    def test_scrape_urls_all_filtered_out(self, mock_loader_class, scraper_service):
        """Test when all documents are filtered out."""
        invalid_docs = [
            Document(page_content="404 not found", metadata={'source': 'url1'}),
            Document(page_content="short", metadata={'source': 'url2'}),
        ]

        mock_loader = Mock()
        mock_loader.load.return_value = invalid_docs
        mock_loader_class.return_value = mock_loader

        with patch.object(scraper_service.html_transformer, 'transform_documents') as mock_transform:
            mock_transform.return_value = invalid_docs

            urls = ['url1', 'url2']
            result = scraper_service.scrape_urls(urls)

            assert len(result) == 0
