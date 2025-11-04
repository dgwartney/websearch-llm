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
            template="""You are a WestJet virtual agent answering customer questions directly.

Context from WestJet website:
{context}

Customer question: {query}

CRITICAL INSTRUCTIONS:
1. Start your answer immediately with the information - NO introductory phrases
2. DO NOT include source citations like (Source 1) or (Source 2) in your answer
3. Just provide the answer content directly and naturally

NEVER start with:
- "According to..."
- "Based on..."
- "The information shows..."
- "According to the information provided..."

NEVER include source references:
- Do NOT write "(Source 1)" or "(Source 2)" in your answer
- Source information will be provided separately to the caller

Good examples:
Q: "What are the baggage fees?"
GOOD: "Checked baggage fees start at $30 for the first bag and $50 for the second bag. Fees vary based on route and fare type."
BAD: "Checked baggage fees start at $30 for the first bag and $50 for the second bag (Source 1)."

Q: "When can I check in?"
GOOD: "You can check in online starting 24 hours before your flight. Mobile check-in is also available through the WestJet app."
BAD: "You can check in online starting 24 hours before your flight (Source 1)."

Q: "What items are prohibited?"
GOOD: "Prohibited items include unapproved devices like knee defenders, items exceeding carry-on size limits, and duty-free alcohol unless consolidated with your carry-on allowance."
BAD: "Prohibited items include unapproved devices... (Source 1)."

Your answer (start directly, no preamble, no source citations):"""
        )

    def generate_answer(self, query: str, context: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate an answer to the query based on the provided context.

        Args:
            query: User's question
            context: Context from scraped and chunked documents
            system_prompt: Optional custom system prompt template. If provided,
                          must include {query} and {context} placeholders.
                          If not provided, uses the default template.

        Returns:
            Generated answer
        """
        try:
            # Use custom prompt template if provided, otherwise use default
            if system_prompt:
                # Validate that both required variables are present
                if '{query}' not in system_prompt:
                    raise ValueError("System prompt must include {query} placeholder")
                if '{context}' not in system_prompt:
                    raise ValueError("System prompt must include {context} placeholder")

                # Create temporary prompt template
                prompt_template = PromptTemplate(
                    input_variables=["query", "context"],
                    template=system_prompt
                )
                logger.info("Using custom system prompt from request")
            else:
                prompt_template = self.prompt_template
                logger.info("Using default system prompt")

            # Format prompt
            formatted_prompt = prompt_template.format(
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
