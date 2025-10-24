"""
TextProcessor class for document chunking and semantic ranking.
Uses LangChain text splitters and AWS Bedrock embeddings.
"""
import logging
from typing import List
import numpy as np
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_aws import BedrockEmbeddings
from langchain.schema import Document

logger = logging.getLogger(__name__)


class TextProcessor:
    """Handles text chunking and semantic ranking using embeddings."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        embedding_model_id: str = "amazon.titan-embed-text-v1",
        aws_region: str = "us-east-1"
    ):
        """
        Initialize TextProcessor.

        Args:
            chunk_size: Size of each text chunk in characters
            chunk_overlap: Overlap between chunks in characters
            embedding_model_id: Bedrock embedding model ID
            aws_region: AWS region for Bedrock
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        # Initialize embeddings
        try:
            self.embeddings = BedrockEmbeddings(
                model_id=embedding_model_id,
                region_name=aws_region
            )
            logger.info(f"Initialized embeddings with model: {embedding_model_id}")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            self.embeddings = None

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into smaller chunks.

        Args:
            documents: List of documents to chunk

        Returns:
            List of chunked documents
        """
        try:
            chunks = self.text_splitter.split_documents(documents)
            logger.info(
                f"Split {len(documents)} documents into {len(chunks)} chunks"
            )
            return chunks

        except Exception as e:
            logger.error(f"Error chunking documents: {e}", exc_info=True)
            return documents  # Return original documents as fallback

    def rank_chunks(
        self,
        chunks: List[Document],
        query: str,
        max_chunks: int = 10
    ) -> List[Document]:
        """
        Rank chunks by semantic similarity to query using embeddings.

        Args:
            chunks: List of document chunks
            query: Search query for ranking
            max_chunks: Maximum number of chunks to return

        Returns:
            Top-ranked chunks
        """
        if not chunks:
            return []

        # If chunks are already under limit, return all
        if len(chunks) <= max_chunks:
            logger.info(f"Chunk count ({len(chunks)}) under limit, returning all")
            return chunks

        # If embeddings not available, return first N chunks
        if not self.embeddings:
            logger.warning("Embeddings not available, returning first N chunks")
            return chunks[:max_chunks]

        try:
            # Embed query
            query_embedding = self.embeddings.embed_query(query)

            # Calculate similarity scores for each chunk
            chunk_scores = []
            for chunk in chunks:
                try:
                    chunk_embedding = self.embeddings.embed_query(chunk.page_content)
                    similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                    chunk_scores.append((chunk, similarity))
                except Exception as e:
                    logger.warning(f"Error embedding chunk: {e}")
                    # Assign low score to failed chunks
                    chunk_scores.append((chunk, 0.0))

            # Sort by similarity (highest first)
            chunk_scores.sort(key=lambda x: x[1], reverse=True)

            # Return top N chunks
            top_chunks = [chunk for chunk, score in chunk_scores[:max_chunks]]

            logger.info(
                f"Ranked {len(chunks)} chunks, selected top {len(top_chunks)} "
                f"(scores: {[score for _, score in chunk_scores[:5]][:3]}...)"
            )

            return top_chunks

        except Exception as e:
            logger.error(f"Error ranking chunks: {e}", exc_info=True)
            # Fallback: return first N chunks
            return chunks[:max_chunks]

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score (0-1)
        """
        vec1_arr = np.array(vec1)
        vec2_arr = np.array(vec2)

        dot_product = np.dot(vec1_arr, vec2_arr)
        norm1 = np.linalg.norm(vec1_arr)
        norm2 = np.linalg.norm(vec2_arr)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def format_chunks_for_context(self, chunks: List[Document]) -> str:
        """
        Format chunks into a context string for LLM.

        Args:
            chunks: List of document chunks

        Returns:
            Formatted context string
        """
        context_parts = []

        for i, chunk in enumerate(chunks, 1):
            source = chunk.metadata.get('source', 'Unknown source')
            content = chunk.page_content.strip()

            context_parts.append(f"[Source {i}: {source}]\n{content}")

        return "\n\n---\n\n".join(context_parts)
