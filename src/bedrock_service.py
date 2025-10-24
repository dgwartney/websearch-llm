"""
BedrockService class for AWS Bedrock LLM integration.
Handles answer generation using Claude models via LangChain.
"""
import logging
from typing import Optional
from langchain_aws import ChatBedrock
from langchain.prompts import PromptTemplate

logger = logging.getLogger(__name__)


class BedrockService:
    """Handles LLM operations using AWS Bedrock."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        aws_region: str = "us-east-1",
        temperature: float = 0.1,
        max_tokens: int = 2000
    ):
        """
        Initialize BedrockService.

        Args:
            model_id: Bedrock model ID (Claude recommended)
            aws_region: AWS region for Bedrock
            temperature: LLM temperature (0-1, lower = more deterministic)
            max_tokens: Maximum tokens in response
        """
        self.model_id = model_id
        self.aws_region = aws_region
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize LLM
        try:
            self.llm = ChatBedrock(
                model_id=model_id,
                region_name=aws_region,
                model_kwargs={
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            logger.info(f"Initialized Bedrock LLM: {model_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock LLM: {e}")
            raise

        # Define prompt template
        self.prompt_template = PromptTemplate(
            input_variables=["query", "context"],
            template="""You are a helpful assistant that answers questions based on provided context from web search results.

Context from web pages:
{context}

Question: {query}

Instructions:
- Answer the question based solely on the information in the context
- If the context doesn't contain enough information to answer fully, acknowledge this
- Cite specific sources when making claims (e.g., "According to Source 1...")
- Be concise but thorough in your answer
- If sources provide conflicting information, acknowledge the different perspectives
- Use a professional and helpful tone

Answer:"""
        )

    def generate_answer(self, query: str, context: str) -> str:
        """
        Generate an answer to the query based on the provided context.

        Args:
            query: User's question
            context: Context from scraped and chunked documents

        Returns:
            Generated answer
        """
        try:
            # Format prompt
            formatted_prompt = self.prompt_template.format(
                query=query,
                context=context
            )

            logger.info(
                f"Generating answer for query (context length: {len(context)} chars)"
            )

            # Invoke LLM
            response = self.llm.invoke(formatted_prompt)

            # Extract text from response
            if hasattr(response, 'content'):
                answer = response.content
            else:
                answer = str(response)

            logger.info(f"Generated answer ({len(answer)} chars)")

            return answer

        except Exception as e:
            logger.error(f"Error generating answer: {e}", exc_info=True)
            raise

    def generate_answer_streaming(self, query: str, context: str):
        """
        Generate answer with streaming response (for future implementation).

        Args:
            query: User's question
            context: Context from scraped and chunked documents

        Yields:
            Chunks of generated text
        """
        try:
            formatted_prompt = self.prompt_template.format(
                query=query,
                context=context
            )

            logger.info("Starting streaming answer generation")

            # Stream response
            for chunk in self.llm.stream(formatted_prompt):
                if hasattr(chunk, 'content'):
                    yield chunk.content
                else:
                    yield str(chunk)

        except Exception as e:
            logger.error(f"Error in streaming answer generation: {e}", exc_info=True)
            raise

    def update_prompt_template(self, new_template: str) -> None:
        """
        Update the prompt template (for customization).

        Args:
            new_template: New prompt template string
                         Must include {query} and {context} variables
        """
        # Validate that both required variables are present
        if '{query}' not in new_template:
            raise ValueError("Prompt template must include {query} variable")
        if '{context}' not in new_template:
            raise ValueError("Prompt template must include {context} variable")

        try:
            self.prompt_template = PromptTemplate(
                input_variables=["query", "context"],
                template=new_template
            )
            logger.info("Updated prompt template")
        except Exception as e:
            logger.error(f"Error updating prompt template: {e}")
            raise ValueError(f"Invalid prompt template: {e}")
