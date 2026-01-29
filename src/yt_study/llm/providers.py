"""LLM provider configuration using LiteLLM."""

import logging
import os
from typing import Optional

from litellm import acompletion
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


class LLMProvider:
    """LLM provider interface using LiteLLM."""
    
    def __init__(self, model: str = "gemini/gemini-2.0-flash"):
        """
        Initialize LLM provider.
        
        Args:
            model: LiteLLM-compatible model string
                   Examples:
                   - gemini/gemini-2.0-flash
                   - gpt-4o
                   - anthropic/claude-3-5-sonnet-20241022
                   - groq/llama-3.3-70b-versatile
                   - xai/grok-2-latest
                   - mistral/mistral-large-latest
        """
        self.model = model
        self._set_api_keys()
        
    def _set_api_keys(self):
        """Ensure API keys are set in environment."""
        # LiteLLM reads from environment variables automatically
        # Just verify we have at least one key set
        api_keys = [
            os.getenv("GEMINI_API_KEY"),
            os.getenv("OPENAI_API_KEY"),
            os.getenv("ANTHROPIC_API_KEY"),
            os.getenv("GROQ_API_KEY"),
            os.getenv("XAI_API_KEY"),
            os.getenv("MISTRAL_API_KEY"),
        ]
        
        if not any(api_keys):
            logger.warning("No LLM API keys configured in environment")
            # We don't print here to avoid UI breakage during import or init
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate text using the configured LLM.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User query/content
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate (None for model default)
            
        Returns:
            Generated text
            
        Raises:
            Exception: If generation fails
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "num_retries": 3,
            }
            
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            
            response = await acompletion(**kwargs)
            
            content = response.choices[0].message.content.strip()
            
            # Clean up wrapping code blocks (common in some LLMs)
            # e.g., ```markdown ... ``` or ``` ... ```
            if content.startswith("```") and content.endswith("```"):
                lines = content.splitlines()
                if len(lines) >= 2:
                    # Check if first line is a fence
                    if lines[0].strip().startswith("```"):
                        # Strip first and last lines
                        content = "\n".join(lines[1:-1]).strip()
            
            return content
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise Exception(f"Failed to generate with {self.model}: {str(e)}")


def get_provider(model: str = "gemini/gemini-2.0-flash") -> LLMProvider:
    """
    Get an LLM provider instance.
    
    Args:
        model: LiteLLM-compatible model string
        
    Returns:
        LLMProvider instance
    """
    return LLMProvider(model=model)
