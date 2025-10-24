"""
Unit tests for TextProcessor class.
Tests chunking, ranking, and formatting functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from langchain.schema import Document
from text_processor import TextProcessor


class TestTextProcessor:
    """Test suite for TextProcessor class."""

    @pytest.fixture
    def text_processor(self):
        """Create TextProcessor instance for testing."""
        with patch('text_processor.BedrockEmbeddings'):
            processor = TextProcessor(
                chunk_size=1000,
                chunk_overlap=200,
                embedding_model_id="amazon.titan-embed-text-v1",
                aws_region="us-east-1"
            )
            # Mock embeddings for testing
            processor.embeddings = Mock()
            return processor

    @pytest.fixture
    def text_processor_no_embeddings(self):
        """Create TextProcessor without embeddings (simulates failure)."""
        with patch('text_processor.BedrockEmbeddings') as mock_embed:
            mock_embed.side_effect = Exception("Embeddings failed")
            processor = TextProcessor()
            return processor

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        return [
            Document(
                page_content="This is a sample document with some content for testing. " * 20,
                metadata={'source': 'https://example.com/page1'}
            ),
            Document(
                page_content="Another document with different content that needs chunking. " * 15,
                metadata={'source': 'https://example.com/page2'}
            )
        ]

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        with patch('text_processor.BedrockEmbeddings'):
            processor = TextProcessor()
            assert processor.chunk_size == 1000
            assert processor.chunk_overlap == 200
            assert processor.text_splitter is not None

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        with patch('text_processor.BedrockEmbeddings'):
            processor = TextProcessor(
                chunk_size=500,
                chunk_overlap=100,
                embedding_model_id="custom-model",
                aws_region="us-west-2"
            )
            assert processor.chunk_size == 500
            assert processor.chunk_overlap == 100

    def test_init_embeddings_failure(self, text_processor_no_embeddings):
        """Test handling of embeddings initialization failure."""
        assert text_processor_no_embeddings.embeddings is None

    def test_chunk_documents_success(self, text_processor, sample_documents):
        """Test successful document chunking."""
        chunks = text_processor.chunk_documents(sample_documents)

        assert len(chunks) > 0
        assert all(isinstance(chunk, Document) for chunk in chunks)
        # Should have more chunks than original documents
        assert len(chunks) >= len(sample_documents)

    def test_chunk_documents_empty_list(self, text_processor):
        """Test chunking empty document list."""
        chunks = text_processor.chunk_documents([])
        assert chunks == []

    def test_chunk_documents_single_document(self, text_processor):
        """Test chunking a single document."""
        doc = Document(
            page_content="Short content.",
            metadata={'source': 'https://example.com'}
        )
        chunks = text_processor.chunk_documents([doc])

        assert len(chunks) >= 1
        assert chunks[0].metadata['source'] == 'https://example.com'

    def test_chunk_documents_preserves_metadata(self, text_processor, sample_documents):
        """Test that chunking preserves document metadata."""
        chunks = text_processor.chunk_documents(sample_documents)

        # All chunks should have source metadata
        for chunk in chunks:
            assert 'source' in chunk.metadata

    def test_chunk_documents_exception_handling(self, text_processor):
        """Test chunking handles exceptions gracefully."""
        with patch.object(text_processor.text_splitter, 'split_documents') as mock_split:
            mock_split.side_effect = Exception("Chunking error")

            docs = [Document(page_content="test", metadata={})]
            result = text_processor.chunk_documents(docs)

            # Should return original documents on error
            assert result == docs

    def test_rank_chunks_under_limit(self, text_processor):
        """Test ranking when chunks are already under max limit."""
        chunks = [
            Document(page_content=f"Chunk {i}", metadata={'source': f'url{i}'})
            for i in range(5)
        ]

        result = text_processor.rank_chunks(chunks, "test query", max_chunks=10)

        # Should return all chunks when under limit
        assert len(result) == 5

    def test_rank_chunks_empty_list(self, text_processor):
        """Test ranking empty chunk list."""
        result = text_processor.rank_chunks([], "test query", max_chunks=10)
        assert result == []

    def test_rank_chunks_no_embeddings(self, text_processor_no_embeddings):
        """Test ranking when embeddings are not available."""
        chunks = [
            Document(page_content=f"Chunk {i}", metadata={'source': f'url{i}'})
            for i in range(15)
        ]

        result = text_processor_no_embeddings.rank_chunks(chunks, "test query", max_chunks=10)

        # Should return first N chunks when embeddings unavailable
        assert len(result) == 10
        assert result[0].page_content == "Chunk 0"

    def test_rank_chunks_with_embeddings_success(self, text_processor):
        """Test ranking with successful embeddings."""
        chunks = [
            Document(page_content=f"Content about topic {i}", metadata={'source': f'url{i}'})
            for i in range(15)
        ]

        # Mock embeddings
        query_embedding = [0.1, 0.2, 0.3]
        chunk_embeddings = [
            [0.1 + i*0.01, 0.2 + i*0.01, 0.3 + i*0.01]
            for i in range(15)
        ]

        text_processor.embeddings.embed_query.side_effect = [query_embedding] + chunk_embeddings

        result = text_processor.rank_chunks(chunks, "test query", max_chunks=10)

        # Should return top 10 chunks
        assert len(result) == 10
        # Embeddings should have been called
        assert text_processor.embeddings.embed_query.call_count == 16  # 1 query + 15 chunks

    def test_rank_chunks_embedding_exception_handling(self, text_processor):
        """Test handling of embedding exceptions for individual chunks."""
        chunks = [
            Document(page_content=f"Chunk {i}", metadata={'source': f'url{i}'})
            for i in range(5)
        ]

        # Mock query embedding success, but some chunk embeddings fail
        def embed_side_effect(text):
            if "Chunk 2" in text:
                raise Exception("Embedding failed")
            return [0.1, 0.2, 0.3]

        text_processor.embeddings.embed_query.side_effect = embed_side_effect

        result = text_processor.rank_chunks(chunks, "test query", max_chunks=3)

        # Should still return results, failed chunks get score 0
        assert len(result) == 3

    def test_rank_chunks_all_embeddings_fail(self, text_processor):
        """Test ranking when all embeddings fail."""
        chunks = [
            Document(page_content=f"Chunk {i}", metadata={'source': f'url{i}'})
            for i in range(15)
        ]

        text_processor.embeddings.embed_query.side_effect = Exception("All embeddings failed")

        result = text_processor.rank_chunks(chunks, "test query", max_chunks=10)

        # Should fall back to returning first N chunks
        assert len(result) == 10

    def test_cosine_similarity_identical_vectors(self):
        """Test cosine similarity with identical vectors."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.0, 2.0, 3.0]

        similarity = TextProcessor._cosine_similarity(vec1, vec2)

        assert abs(similarity - 1.0) < 0.0001  # Should be 1.0

    def test_cosine_similarity_orthogonal_vectors(self):
        """Test cosine similarity with orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]

        similarity = TextProcessor._cosine_similarity(vec1, vec2)

        assert abs(similarity - 0.0) < 0.0001  # Should be 0.0

    def test_cosine_similarity_opposite_vectors(self):
        """Test cosine similarity with opposite vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]

        similarity = TextProcessor._cosine_similarity(vec1, vec2)

        assert abs(similarity - (-1.0)) < 0.0001  # Should be -1.0

    def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity with zero vector."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]

        similarity = TextProcessor._cosine_similarity(vec1, vec2)

        assert similarity == 0.0  # Should be 0.0

    def test_cosine_similarity_both_zero(self):
        """Test cosine similarity with both vectors zero."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [0.0, 0.0, 0.0]

        similarity = TextProcessor._cosine_similarity(vec1, vec2)

        assert similarity == 0.0

    def test_format_chunks_for_context_single_chunk(self, text_processor):
        """Test formatting a single chunk for context."""
        chunks = [
            Document(
                page_content="This is the content.",
                metadata={'source': 'https://example.com/page1'}
            )
        ]

        context = text_processor.format_chunks_for_context(chunks)

        assert "[Source 1: https://example.com/page1]" in context
        assert "This is the content." in context

    def test_format_chunks_for_context_multiple_chunks(self, text_processor):
        """Test formatting multiple chunks for context."""
        chunks = [
            Document(
                page_content="First chunk content.",
                metadata={'source': 'https://example.com/page1'}
            ),
            Document(
                page_content="Second chunk content.",
                metadata={'source': 'https://example.com/page2'}
            )
        ]

        context = text_processor.format_chunks_for_context(chunks)

        assert "[Source 1: https://example.com/page1]" in context
        assert "[Source 2: https://example.com/page2]" in context
        assert "First chunk content." in context
        assert "Second chunk content." in context
        assert "---" in context  # Separator between chunks

    def test_format_chunks_for_context_empty_list(self, text_processor):
        """Test formatting empty chunk list."""
        context = text_processor.format_chunks_for_context([])
        assert context == ""

    def test_format_chunks_for_context_missing_source(self, text_processor):
        """Test formatting chunks with missing source metadata."""
        chunks = [
            Document(
                page_content="Content without source.",
                metadata={}
            )
        ]

        context = text_processor.format_chunks_for_context(chunks)

        assert "[Source 1: Unknown source]" in context
        assert "Content without source." in context

    def test_format_chunks_for_context_strips_whitespace(self, text_processor):
        """Test that formatting strips leading/trailing whitespace."""
        chunks = [
            Document(
                page_content="  \n\n  Content with whitespace  \n\n  ",
                metadata={'source': 'https://example.com'}
            )
        ]

        context = text_processor.format_chunks_for_context(chunks)

        # Should not have excessive whitespace
        assert context.count('\n\n\n') == 0
        assert "Content with whitespace" in context

    def test_chunk_documents_large_text(self, text_processor):
        """Test chunking very large text."""
        large_text = "This is a sentence. " * 500  # ~10,000 chars
        doc = Document(page_content=large_text, metadata={'source': 'large.txt'})

        chunks = text_processor.chunk_documents([doc])

        # Should create multiple chunks
        assert len(chunks) > 1
        # Each chunk should be roughly chunk_size or smaller
        for chunk in chunks:
            assert len(chunk.page_content) <= text_processor.chunk_size + text_processor.chunk_overlap

    def test_rank_chunks_sorting_order(self, text_processor):
        """Test that rank_chunks returns chunks in descending similarity order."""
        chunks = [
            Document(page_content=f"Chunk {i}", metadata={'source': f'url{i}'})
            for i in range(10)
        ]

        # Mock embeddings with specific similarity scores
        query_embedding = [1.0, 0.0, 0.0]
        # Create embeddings with decreasing similarity
        chunk_embeddings = [
            [1.0 - i*0.1, 0.0, 0.0]
            for i in range(10)
        ]

        text_processor.embeddings.embed_query.side_effect = [query_embedding] + chunk_embeddings

        result = text_processor.rank_chunks(chunks, "test query", max_chunks=5)

        # Should return first 5 chunks (highest similarity)
        assert len(result) == 5
        # First result should be Chunk 0 (highest similarity)
        assert result[0].page_content == "Chunk 0"
