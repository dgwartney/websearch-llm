"""
TextProcessor class for document chunking and semantic ranking.
Uses LangChain text splitters and AWS Bedrock embeddings.
"""
import logging
from typing import List
import numpy as np
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import BedrockEmbeddings
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
    ) -> tuple[List[Document], List[float]]:
        """
        Rank chunks by semantic similarity to query using embeddings.

        OPTIMIZATION: Limits chunks to process before embedding to avoid timeouts.

        Args:
            chunks: List of document chunks
            query: Search query for ranking
            max_chunks: Maximum number of chunks to return

        Returns:
            Tuple of (top-ranked chunks, their similarity scores)
        """
        if not chunks:
            return [], []

        # If chunks are already under limit, return all with no scores
        if len(chunks) <= max_chunks:
            logger.info(f"Chunk count ({len(chunks)}) under limit, returning all")
            return chunks, [0.0] * len(chunks)

        # If embeddings not available, return first N chunks with no scores
        if not self.embeddings:
            logger.warning("Embeddings not available, returning first N chunks")
            return chunks[:max_chunks], [0.0] * max_chunks

        # OPTIMIZATION: Limit chunks to process to avoid timeout
        # Process at most 3x the requested chunks to balance quality vs performance
        max_chunks_to_process = min(len(chunks), max_chunks * 3)
        chunks_to_rank = chunks[:max_chunks_to_process]

        if len(chunks) > max_chunks_to_process:
            logger.info(
                f"Limiting ranking from {len(chunks)} to {max_chunks_to_process} chunks "
                f"to avoid timeout (requesting top {max_chunks})"
            )

        try:
            # Embed query once
            query_embedding = self.embeddings.embed_query(query)

            # OPTIMIZATION: Batch embed all chunks at once instead of one-by-one
            chunk_texts = [chunk.page_content for chunk in chunks_to_rank]

            try:
                # Try batch embedding (faster)
                chunk_embeddings = self.embeddings.embed_documents(chunk_texts)
                logger.info(f"Batch embedded {len(chunk_texts)} chunks")
            except Exception as batch_error:
                logger.warning(f"Batch embedding failed, falling back to individual: {batch_error}")
                # Fallback to individual embeddings
                chunk_embeddings = []
                for text in chunk_texts:
                    try:
                        emb = self.embeddings.embed_query(text)
                        chunk_embeddings.append(emb)
                    except Exception as e:
                        logger.warning(f"Error embedding chunk: {e}")
                        # Use zero vector for failed embeddings
                        chunk_embeddings.append([0.0] * len(query_embedding))

            # Calculate similarity scores
            chunk_scores = []
            for chunk, chunk_embedding in zip(chunks_to_rank, chunk_embeddings):
                similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                chunk_scores.append((chunk, similarity))

            # Sort by similarity (highest first)
            chunk_scores.sort(key=lambda x: x[1], reverse=True)

            # Return top N chunks and their scores
            top_chunk_scores = chunk_scores[:max_chunks]
            top_chunks = [chunk for chunk, score in top_chunk_scores]
            top_scores = [score for chunk, score in top_chunk_scores]

            logger.info(
                f"Ranked {len(chunks_to_rank)} chunks, selected top {len(top_chunks)} "
                f"(top scores: {[f'{score:.3f}' for score in top_scores[:3]]})"
            )

            return top_chunks, top_scores

        except Exception as e:
            logger.error(f"Error ranking chunks: {e}", exc_info=True)
            # Fallback: return first N chunks with no scores
            return chunks[:max_chunks], [0.0] * min(max_chunks, len(chunks))

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
