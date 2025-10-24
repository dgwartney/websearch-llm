"""
SearchService class for web search using various APIs.
Supports Brave Search, SerpAPI, and DuckDuckGo (fallback).
"""
import logging
from typing import List, Optional
import requests

logger = logging.getLogger(__name__)


class SearchService:
    """Handles web search operations with multiple provider support."""

    def __init__(
        self,
        brave_api_key: Optional[str] = None,
        serpapi_key: Optional[str] = None,
        timeout: int = 5
    ):
        """
        Initialize SearchService.

        Args:
            brave_api_key: Brave Search API key (optional)
            serpapi_key: SerpAPI key (optional)
            timeout: Request timeout in seconds
        """
        self.brave_api_key = brave_api_key
        self.serpapi_key = serpapi_key
        self.timeout = timeout

    def search(
        self,
        query: str,
        target_domain: str,
        max_results: int = 5
    ) -> List[str]:
        """
        Search for relevant URLs using available search API.

        Args:
            query: Search query
            target_domain: Domain to restrict search to
            max_results: Maximum number of URLs to return

        Returns:
            List of URLs
        """
        # Try Brave Search first (if configured)
        if self.brave_api_key:
            urls = self._search_brave(query, target_domain, max_results)
            if urls:
                return urls

        # Try SerpAPI (if configured)
        if self.serpapi_key:
            urls = self._search_serpapi(query, target_domain, max_results)
            if urls:
                return urls

        # Fallback to DuckDuckGo (free)
        logger.info("Using DuckDuckGo fallback search")
        return self._search_duckduckgo(query, target_domain, max_results)

    def _search_brave(
        self,
        query: str,
        domain: str,
        max_results: int
    ) -> List[str]:
        """Search using Brave Search API."""
        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.brave_api_key
            }
            params = {
                "q": f"{query} site:{domain}",
                "count": max_results
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            results = response.json()
            urls = [
                result['url']
                for result in results.get('web', {}).get('results', [])
            ]

            logger.info(f"Brave Search returned {len(urls)} URLs")
            return urls[:max_results]

        except Exception as e:
            logger.warning(f"Brave Search failed: {e}")
            return []

    def _search_serpapi(
        self,
        query: str,
        domain: str,
        max_results: int
    ) -> List[str]:
        """Search using SerpAPI."""
        try:
            url = "https://serpapi.com/search"
            params = {
                "q": f"{query} site:{domain}",
                "api_key": self.serpapi_key,
                "num": max_results
            }

            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            results = response.json()
            urls = [
                result['link']
                for result in results.get('organic_results', [])
            ]

            logger.info(f"SerpAPI returned {len(urls)} URLs")
            return urls[:max_results]

        except Exception as e:
            logger.warning(f"SerpAPI failed: {e}")
            return []

    def _search_duckduckgo(
        self,
        query: str,
        domain: str,
        max_results: int
    ) -> List[str]:
        """Search using DuckDuckGo (free, no API key required)."""
        try:
            from duckduckgo_search import DDGS

            search_query = f"{query} site:{domain}"

            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=max_results))
                urls = [result['href'] for result in results if 'href' in result]

                logger.info(f"DuckDuckGo returned {len(urls)} URLs")
                return urls[:max_results]

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []
