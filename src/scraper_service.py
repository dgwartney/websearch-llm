"""
ScraperService class for web scraping using LangChain.
Handles HTML loading, transformation, and rate limiting.
"""
import logging
from typing import List
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer
from langchain.schema import Document

logger = logging.getLogger(__name__)


class ScraperService:
    """Handles web scraping with rate limiting and HTML transformation."""

    def __init__(
        self,
        max_concurrent: int = 3,
        verify_ssl: bool = True,
        min_content_length: int = 100
    ):
        """
        Initialize ScraperService.

        Args:
            max_concurrent: Maximum concurrent scraping requests (rate limiting)
            verify_ssl: Whether to verify SSL certificates
            min_content_length: Minimum content length to consider valid
        """
        self.max_concurrent = max_concurrent
        self.verify_ssl = verify_ssl
        self.min_content_length = min_content_length
        self.html_transformer = Html2TextTransformer()

    def scrape_urls(self, urls: List[str]) -> List[Document]:
        """
        Scrape content from URLs and return as LangChain Documents.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of LangChain Documents with scraped content
        """
        if not urls:
            logger.warning("No URLs provided to scrape")
            return []

        try:
            # Load HTML from URLs with rate limiting
            logger.info(f"Scraping {len(urls)} URLs with max_concurrent={self.max_concurrent}")

            loader = AsyncHtmlLoader(
                urls,
                verify_ssl=self.verify_ssl,
                requests_per_second=self.max_concurrent
            )
            html_docs = loader.load()

            # Transform HTML to clean text
            text_docs = self.html_transformer.transform_documents(html_docs)

            # Filter out invalid documents
            valid_docs = self._filter_valid_documents(text_docs)

            logger.info(
                f"Successfully scraped {len(valid_docs)} out of {len(urls)} URLs"
            )

            return valid_docs

        except Exception as e:
            logger.error(f"Error scraping URLs: {e}", exc_info=True)
            return []

    def _filter_valid_documents(self, documents: List[Document]) -> List[Document]:
        """
        Filter out invalid or empty documents.

        Args:
            documents: List of documents to filter

        Returns:
            List of valid documents
        """
        valid_docs = []

        for doc in documents:
            # Check if content is long enough
            content = doc.page_content.strip()
            if len(content) < self.min_content_length:
                source = doc.metadata.get('source', 'unknown')
                logger.debug(
                    f"Skipping document from {source}: "
                    f"content too short ({len(content)} chars)"
                )
                continue

            # Check if content is not just error messages
            error_indicators = [
                '404 not found',
                'page not found',
                'access denied',
                'forbidden'
            ]

            content_lower = content.lower()
            if any(indicator in content_lower for indicator in error_indicators):
                source = doc.metadata.get('source', 'unknown')
                logger.debug(f"Skipping document from {source}: appears to be error page")
                continue

            valid_docs.append(doc)

        return valid_docs
