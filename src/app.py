"""
Main Lambda handler for web search and LLM-based answer generation.
Orchestrates SearchService, ScraperService, TextProcessor, and BedrockService.
"""
import json
import os
import logging
import time
from typing import Dict, Any

from search_service import SearchService
from scraper_service import ScraperService
from text_processor import TextProcessor
from bedrock_service import BedrockService

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))


class WebSearchLLMHandler:
    """Main orchestrator for web search and LLM answer generation."""

    def __init__(self):
        """Initialize all service components."""
        # Get configuration from environment
        self.target_domain = os.getenv('TARGET_DOMAIN', 'example.com')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')

        # Initialize services
        self.search_service = SearchService(
            brave_api_key=os.getenv('BRAVE_API_KEY'),
            serpapi_key=os.getenv('SERPAPI_KEY'),
            timeout=5
        )

        self.scraper_service = ScraperService(
            max_concurrent=int(os.getenv('MAX_CONCURRENT_REQUESTS', 3)),
            verify_ssl=True,
            min_content_length=100
        )

        self.text_processor = TextProcessor(
            chunk_size=1000,
            chunk_overlap=200,
            embedding_model_id="amazon.titan-embed-text-v1",
            aws_region=self.aws_region
        )

        self.bedrock_service = BedrockService(
            model_id=os.getenv(
                'BEDROCK_MODEL_ID',
                'anthropic.claude-3-haiku-20240307-v1:0'
            ),
            aws_region=self.aws_region,
            temperature=0.1,
            max_tokens=2000
        )

        logger.info("WebSearchLLMHandler initialized successfully")

    def process_query(
        self,
        query: str,
        max_results: int = 5,
        max_chunks: int = 10
    ) -> Dict[str, Any]:
        """
        Process a search query and generate an answer.

        Args:
            query: User's search query
            max_results: Maximum number of URLs to search
            max_chunks: Maximum number of text chunks to use for context

        Returns:
            Dict containing answer, sources, and metadata
        """
        start_time = time.time()

        # Step 1: Search for relevant URLs
        logger.info(f"Searching for: {query}")
        urls = self.search_service.search(
            query=query,
            target_domain=self.target_domain,
            max_results=max_results
        )

        if not urls:
            return {
                'answer': 'No relevant search results found for your query.',
                'sources': [],
                'metadata': {
                    'urls_scraped': 0,
                    'chunks_processed': 0,
                    'total_time_ms': int((time.time() - start_time) * 1000)
                }
            }

        logger.info(f"Found {len(urls)} URLs to scrape")

        # Step 2: Scrape content from URLs
        documents = self.scraper_service.scrape_urls(urls)

        if not documents:
            return {
                'answer': 'Unable to retrieve content from search results.',
                'sources': urls,
                'metadata': {
                    'urls_scraped': 0,
                    'chunks_processed': 0,
                    'total_time_ms': int((time.time() - start_time) * 1000)
                }
            }

        logger.info(f"Successfully scraped {len(documents)} documents")

        # Step 3: Chunk documents
        chunks = self.text_processor.chunk_documents(documents)

        # Step 4: Rank chunks by relevance
        top_chunks, similarity_scores = self.text_processor.rank_chunks(
            chunks=chunks,
            query=query,
            max_chunks=max_chunks
        )

        # Step 5: Format context for LLM
        context = self.text_processor.format_chunks_for_context(top_chunks)

        # Step 6: Generate answer using LLM
        logger.info("Generating answer with Bedrock")
        answer = self.bedrock_service.generate_answer(query, context)

        # Extract unique source URLs
        source_urls = list(set([
            chunk.metadata.get('source', '')
            for chunk in top_chunks
        ]))

        # Build detailed source information with similarity scores
        source_details = []
        for i, (chunk, score) in enumerate(zip(top_chunks, similarity_scores), 1):
            source_url = chunk.metadata.get('source', 'Unknown')
            source_details.append({
                'rank': i,
                'similarity_score': round(score, 4),
                'url': source_url,
                'content_preview': chunk.page_content[:200] + '...' if len(chunk.page_content) > 200 else chunk.page_content
            })

        total_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Successfully processed query in {total_time_ms}ms")

        return {
            'answer': answer,
            'sources': source_urls,
            'source_details': source_details,
            'metadata': {
                'chunks_processed': len(top_chunks),
                'urls_scraped': len(documents),
                'total_time_ms': total_time_ms
            }
        }


# Global handler instance (reused across Lambda invocations)
handler = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function.

    Expected request body:
    {
        "query": "What is the pricing for product X?",
        "max_results": 5,
        "max_chunks": 10
    }

    Returns:
    {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": {
            "answer": "...",
            "sources": ["url1", "url2"],
            "metadata": {...}
        }
    }
    """
    global handler

    try:
        # Initialize handler (reuse across invocations)
        if handler is None:
            logger.info("Initializing WebSearchLLMHandler")
            handler = WebSearchLLMHandler()

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        query = body.get('query')

        if not query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Missing required parameter: query'
                })
            }

        max_results = body.get('max_results', 5)
        max_chunks = body.get('max_chunks', 10)

        # Validate parameters
        if not isinstance(max_results, int) or max_results < 1 or max_results > 20:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'max_results must be an integer between 1 and 20'
                })
            }

        if not isinstance(max_chunks, int) or max_chunks < 1 or max_chunks > 50:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'max_chunks must be an integer between 1 and 50'
                })
            }

        # Process query
        result = handler.process_query(query, max_results, max_chunks)

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': f'Internal server error: {str(e)}'
            })
        }
