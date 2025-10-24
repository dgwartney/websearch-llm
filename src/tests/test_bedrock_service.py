"""
Unit tests for BedrockService class.
Tests AWS Bedrock LLM integration.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from bedrock_service import BedrockService


class TestBedrockService:
    """Test suite for BedrockService class."""

    @pytest.fixture
    def bedrock_service(self):
        """Create BedrockService instance for testing."""
        with patch('bedrock_service.ChatBedrock') as mock_bedrock:
            mock_llm = Mock()
            mock_bedrock.return_value = mock_llm

            service = BedrockService(
                model_id="anthropic.claude-3-haiku-20240307-v1:0",
                aws_region="us-east-1",
                temperature=0.1,
                max_tokens=2000
            )
            service.llm = mock_llm
            return service

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        with patch('bedrock_service.ChatBedrock') as mock_bedrock:
            service = BedrockService()

            assert service.model_id == "anthropic.claude-3-haiku-20240307-v1:0"
            assert service.aws_region == "us-east-1"
            assert service.temperature == 0.1
            assert service.max_tokens == 2000
            assert service.prompt_template is not None

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        with patch('bedrock_service.ChatBedrock') as mock_bedrock:
            service = BedrockService(
                model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                aws_region="us-west-2",
                temperature=0.5,
                max_tokens=3000
            )

            assert service.model_id == "anthropic.claude-3-sonnet-20240229-v1:0"
            assert service.aws_region == "us-west-2"
            assert service.temperature == 0.5
            assert service.max_tokens == 3000

    def test_init_bedrock_failure(self):
        """Test handling of Bedrock initialization failure."""
        with patch('bedrock_service.ChatBedrock') as mock_bedrock:
            mock_bedrock.side_effect = Exception("Bedrock init failed")

            with pytest.raises(Exception) as exc_info:
                BedrockService()

            assert "Bedrock init failed" in str(exc_info.value)

    def test_generate_answer_success(self, bedrock_service):
        """Test successful answer generation."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.content = "This is the generated answer based on the context."
        bedrock_service.llm.invoke.return_value = mock_response

        query = "What is the pricing?"
        context = "[Source 1: url1]\nPricing information here."

        answer = bedrock_service.generate_answer(query, context)

        assert answer == "This is the generated answer based on the context."
        bedrock_service.llm.invoke.assert_called_once()

        # Verify the prompt contains query and context
        call_args = bedrock_service.llm.invoke.call_args[0][0]
        assert query in call_args
        assert context in call_args

    def test_generate_answer_response_without_content_attr(self, bedrock_service):
        """Test handling response without content attribute."""
        # Mock response that doesn't have content attribute
        mock_response = "Plain string response"
        bedrock_service.llm.invoke.return_value = mock_response

        query = "Test query"
        context = "Test context"

        answer = bedrock_service.generate_answer(query, context)

        assert answer == "Plain string response"

    def test_generate_answer_llm_exception(self, bedrock_service):
        """Test handling of LLM invocation exception."""
        bedrock_service.llm.invoke.side_effect = Exception("LLM error")

        query = "Test query"
        context = "Test context"

        with pytest.raises(Exception) as exc_info:
            bedrock_service.generate_answer(query, context)

        assert "LLM error" in str(exc_info.value)

    def test_generate_answer_empty_query(self, bedrock_service):
        """Test answer generation with empty query."""
        mock_response = Mock()
        mock_response.content = "Generated answer"
        bedrock_service.llm.invoke.return_value = mock_response

        answer = bedrock_service.generate_answer("", "Context here")

        assert answer == "Generated answer"

    def test_generate_answer_empty_context(self, bedrock_service):
        """Test answer generation with empty context."""
        mock_response = Mock()
        mock_response.content = "Generated answer"
        bedrock_service.llm.invoke.return_value = mock_response

        answer = bedrock_service.generate_answer("Query here", "")

        assert answer == "Generated answer"

    def test_generate_answer_long_context(self, bedrock_service):
        """Test answer generation with very long context."""
        mock_response = Mock()
        mock_response.content = "Generated answer"
        bedrock_service.llm.invoke.return_value = mock_response

        query = "Test query"
        context = "Long context. " * 1000  # Very long context

        answer = bedrock_service.generate_answer(query, context)

        assert answer == "Generated answer"
        # Verify LLM was invoked
        bedrock_service.llm.invoke.assert_called_once()

    def test_generate_answer_streaming_success(self, bedrock_service):
        """Test streaming answer generation."""
        # Mock streaming response
        mock_chunks = [
            Mock(content="This "),
            Mock(content="is "),
            Mock(content="streaming "),
            Mock(content="response.")
        ]
        bedrock_service.llm.stream.return_value = iter(mock_chunks)

        query = "Test query"
        context = "Test context"

        # Collect streaming chunks
        chunks = list(bedrock_service.generate_answer_streaming(query, context))

        assert chunks == ["This ", "is ", "streaming ", "response."]
        bedrock_service.llm.stream.assert_called_once()

    def test_generate_answer_streaming_without_content_attr(self, bedrock_service):
        """Test streaming with chunks that don't have content attribute."""
        mock_chunks = ["chunk1", "chunk2", "chunk3"]
        bedrock_service.llm.stream.return_value = iter(mock_chunks)

        query = "Test query"
        context = "Test context"

        chunks = list(bedrock_service.generate_answer_streaming(query, context))

        assert chunks == ["chunk1", "chunk2", "chunk3"]

    def test_generate_answer_streaming_exception(self, bedrock_service):
        """Test streaming exception handling."""
        bedrock_service.llm.stream.side_effect = Exception("Streaming error")

        query = "Test query"
        context = "Test context"

        with pytest.raises(Exception) as exc_info:
            list(bedrock_service.generate_answer_streaming(query, context))

        assert "Streaming error" in str(exc_info.value)

    def test_update_prompt_template_success(self, bedrock_service):
        """Test updating prompt template."""
        new_template = """Custom template.

Context: {context}
Query: {query}

Answer:"""

        bedrock_service.update_prompt_template(new_template)

        # Verify template was updated
        formatted = bedrock_service.prompt_template.format(
            query="test query",
            context="test context"
        )
        assert "Custom template" in formatted
        assert "test query" in formatted
        assert "test context" in formatted

    def test_update_prompt_template_missing_variables(self, bedrock_service):
        """Test updating prompt template with missing variables."""
        # Template missing required variables
        invalid_template = "This template doesn't have the required variables."

        with pytest.raises(ValueError):
            bedrock_service.update_prompt_template(invalid_template)

    def test_update_prompt_template_only_query(self, bedrock_service):
        """Test template with only query variable (should fail)."""
        template_only_query = "Query: {query}"

        with pytest.raises(ValueError):
            bedrock_service.update_prompt_template(template_only_query)

    def test_update_prompt_template_only_context(self, bedrock_service):
        """Test template with only context variable (should fail)."""
        template_only_context = "Context: {context}"

        with pytest.raises(ValueError):
            bedrock_service.update_prompt_template(template_only_context)

    def test_prompt_template_contains_instructions(self, bedrock_service):
        """Test that default prompt template contains instructions."""
        formatted = bedrock_service.prompt_template.format(
            query="test query",
            context="test context"
        )

        # Check for key instructions
        assert "context" in formatted.lower()
        assert "question" in formatted.lower() or "query" in formatted.lower()
        assert "answer" in formatted.lower()

    def test_prompt_template_format_with_special_chars(self, bedrock_service):
        """Test prompt template with special characters in query/context."""
        query = "What's the price? $100 or €90?"
        context = "[Source 1]\nPrice: $100\n\nPrice: €90"

        formatted = bedrock_service.prompt_template.format(
            query=query,
            context=context
        )

        assert "$100" in formatted
        assert "€90" in formatted
        assert "What's the price?" in formatted

    def test_generate_answer_uses_correct_model_kwargs(self):
        """Test that model_kwargs are passed correctly to ChatBedrock."""
        with patch('bedrock_service.ChatBedrock') as mock_bedrock:
            service = BedrockService(
                temperature=0.7,
                max_tokens=1500
            )

            # Verify ChatBedrock was called with correct kwargs
            mock_bedrock.assert_called_once()
            call_kwargs = mock_bedrock.call_args[1]
            assert call_kwargs['model_kwargs']['temperature'] == 0.7
            assert call_kwargs['model_kwargs']['max_tokens'] == 1500

    def test_generate_answer_multiple_calls(self, bedrock_service):
        """Test multiple answer generation calls."""
        mock_response1 = Mock(content="Answer 1")
        mock_response2 = Mock(content="Answer 2")

        bedrock_service.llm.invoke.side_effect = [mock_response1, mock_response2]

        answer1 = bedrock_service.generate_answer("Query 1", "Context 1")
        answer2 = bedrock_service.generate_answer("Query 2", "Context 2")

        assert answer1 == "Answer 1"
        assert answer2 == "Answer 2"
        assert bedrock_service.llm.invoke.call_count == 2

    def test_generate_answer_preserves_formatting(self, bedrock_service):
        """Test that answer preserves formatting from LLM."""
        mock_response = Mock()
        mock_response.content = "Answer with\n\nmultiple\n\nparagraphs."
        bedrock_service.llm.invoke.return_value = mock_response

        answer = bedrock_service.generate_answer("Test", "Test context")

        assert "\n\n" in answer
        assert answer == "Answer with\n\nmultiple\n\nparagraphs."
