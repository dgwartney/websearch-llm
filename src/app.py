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
        """Initialize all service components with defaults from environment."""
        # Get default configuration from environment
        self.default_target_domain = os.getenv('TARGET_DOMAIN', 'example.com')
        self.default_aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.default_bedrock_model_id = os.getenv(
            'BEDROCK_MODEL_ID',
            'anthropic.claude-3-haiku-20240307-v1:0'
        )
        self.default_chunk_size = int(os.getenv('CHUNK_SIZE', 1000))
        self.default_chunk_overlap = int(os.getenv('CHUNK_OVERLAP', 200))
        self.default_log_level = os.getenv('LOG_LEVEL', 'INFO')

        # Initialize search and scraper services (these don't need per-request config)
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

        # Cache for services that can be reused with same config
        self._text_processor_cache = {}
        self._bedrock_service_cache = {}

        logger.info("WebSearchLLMHandler initialized successfully")

    def _get_text_processor(
        self,
        chunk_size: int,
        chunk_overlap: int
    ) -> TextProcessor:
        """
        Get or create a TextProcessor with the specified configuration.
        Uses caching to reuse processors with same config.

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks

        Returns:
            TextProcessor instance
        """
        cache_key = f"{chunk_size}_{chunk_overlap}"
        if cache_key not in self._text_processor_cache:
            self._text_processor_cache[cache_key] = TextProcessor(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                embedding_model_id="amazon.titan-embed-text-v1",
                aws_region=self.default_aws_region
            )
            logger.info(f"Created TextProcessor with chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")
        return self._text_processor_cache[cache_key]

    def _get_bedrock_service(self, model_id: str) -> BedrockService:
        """
        Get or create a BedrockService with the specified model.
        Uses caching to reuse services with same model.

        Args:
            model_id: Bedrock model ID

        Returns:
            BedrockService instance
        """
        if model_id not in self._bedrock_service_cache:
            self._bedrock_service_cache[model_id] = BedrockService(
                model_id=model_id,
                aws_region=self.default_aws_region,
                temperature=0.1,
                max_tokens=2000
            )
            logger.info(f"Created BedrockService with model_id={model_id}")
        return self._bedrock_service_cache[model_id]

    def process_query(
        self,
        query: str,
        max_results: int = 5,
        max_chunks: int = 10,
        system_prompt: str = None,
        target_domain: str = None,
        bedrock_model_id: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
        log_level: str = None
    ) -> Dict[str, Any]:
        """
        Process a search query and generate an answer.

        Args:
            query: User's search query
            max_results: Maximum number of URLs to search
            max_chunks: Maximum number of text chunks to use for context
            system_prompt: Optional custom system prompt template with {query} and {context} placeholders
            target_domain: Domain to search (defaults to environment config)
            bedrock_model_id: Bedrock model ID to use (defaults to environment config)
            chunk_size: Text chunk size in characters (defaults to environment config)
            chunk_overlap: Chunk overlap in characters (defaults to environment config)
            log_level: Log level for this request (DEBUG, INFO, WARNING, ERROR)

        Returns:
            Dict containing answer, sources, and metadata
        """
        start_time = time.time()

        # Apply per-request configuration with defaults
        target_domain = target_domain or self.default_target_domain
        bedrock_model_id = bedrock_model_id or self.default_bedrock_model_id
        chunk_size = chunk_size or self.default_chunk_size
        chunk_overlap = chunk_overlap or self.default_chunk_overlap

        # Set log level for this request if specified
        original_log_level = logger.level
        if log_level:
            try:
                logger.setLevel(getattr(logging, log_level.upper()))
                logger.info(f"Log level set to {log_level.upper()} for this request")
            except (AttributeError, ValueError):
                logger.warning(f"Invalid log level '{log_level}', keeping current level")

        try:
            # Get appropriate services for this request
            text_processor = self._get_text_processor(chunk_size, chunk_overlap)
            bedrock_service = self._get_bedrock_service(bedrock_model_id)

            # Step 1: Search for relevant URLs
            logger.info(f"Searching for: {query} on domain: {target_domain}")
            urls = self.search_service.search(
                query=query,
                target_domain=target_domain,
                max_results=max_results
            )

            if not urls:
                return {
                    'answer': 'No relevant search results found for your query.',
                    'sources': [],
                    'metadata': {
                        'urls_scraped': 0,
                        'chunks_processed': 0,
                        'total_time_ms': int((time.time() - start_time) * 1000),
                        'target_domain': target_domain,
                        'bedrock_model_id': bedrock_model_id,
                        'chunk_size': chunk_size,
                        'chunk_overlap': chunk_overlap
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
                        'total_time_ms': int((time.time() - start_time) * 1000),
                        'target_domain': target_domain,
                        'bedrock_model_id': bedrock_model_id,
                        'chunk_size': chunk_size,
                        'chunk_overlap': chunk_overlap
                    }
                }

            logger.info(f"Successfully scraped {len(documents)} documents")

            # Step 3: Chunk documents
            chunks = text_processor.chunk_documents(documents)

            # Step 4: Rank chunks by relevance
            top_chunks, similarity_scores = text_processor.rank_chunks(
                chunks=chunks,
                query=query,
                max_chunks=max_chunks
            )

            # Step 5: Format context for LLM
            context = text_processor.format_chunks_for_context(top_chunks)

            # Step 6: Generate answer using LLM
            logger.info(f"Generating answer with Bedrock model: {bedrock_model_id}")
            answer = bedrock_service.generate_answer(query, context, system_prompt)

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
                    'total_time_ms': total_time_ms,
                    'target_domain': target_domain,
                    'bedrock_model_id': bedrock_model_id,
                    'chunk_size': chunk_size,
                    'chunk_overlap': chunk_overlap
                }
            }
        finally:
            # Restore original log level
            if log_level:
                logger.setLevel(original_log_level)


# Global handler instance (reused across Lambda invocations)
handler = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function.

    Expected request body:
    {
        "query": "What is the pricing for product X?",
        "max_results": 5,
        "max_chunks": 10,
        "system_prompt": "You are a helpful assistant. Context: {context}\n\nQuestion: {query}\n\nAnswer:",
        "target_domain": "example.com",
        "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "log_level": "INFO"
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
        system_prompt = body.get('system_prompt')
        target_domain = body.get('target_domain')
        bedrock_model_id = body.get('bedrock_model_id')
        chunk_size = body.get('chunk_size')
        chunk_overlap = body.get('chunk_overlap')
        log_level = body.get('log_level')

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

        # Validate system_prompt if provided
        if system_prompt:
            if not isinstance(system_prompt, str):
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'system_prompt must be a string'
                    })
                }
            if '{query}' not in system_prompt or '{context}' not in system_prompt:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'system_prompt must include {query} and {context} placeholders'
                    })
                }

        # Validate target_domain if provided
        if target_domain is not None:
            if not isinstance(target_domain, str) or not target_domain.strip():
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'target_domain must be a non-empty string'
                    })
                }

        # Validate bedrock_model_id if provided
        if bedrock_model_id is not None:
            if not isinstance(bedrock_model_id, str) or not bedrock_model_id.strip():
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'bedrock_model_id must be a non-empty string'
                    })
                }

        # Validate chunk_size if provided
        if chunk_size is not None:
            if not isinstance(chunk_size, int) or chunk_size < 100 or chunk_size > 10000:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'chunk_size must be an integer between 100 and 10000'
                    })
                }

        # Validate chunk_overlap if provided
        if chunk_overlap is not None:
            if not isinstance(chunk_overlap, int) or chunk_overlap < 0 or chunk_overlap > 1000:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'chunk_overlap must be an integer between 0 and 1000'
                    })
                }
            # Ensure overlap is less than chunk_size if both provided
            if chunk_size is not None and chunk_overlap >= chunk_size:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'chunk_overlap must be less than chunk_size'
                    })
                }

        # Validate log_level if provided
        if log_level is not None:
            if not isinstance(log_level, str):
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'log_level must be a string'
                    })
                }
            valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
            if log_level.upper() not in valid_log_levels:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': f'log_level must be one of: {", ".join(valid_log_levels)}'
                    })
                }

        # Process query
        result = handler.process_query(
            query=query,
            max_results=max_results,
            max_chunks=max_chunks,
            system_prompt=system_prompt,
            target_domain=target_domain,
            bedrock_model_id=bedrock_model_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            log_level=log_level
        )

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
