import json
import logging
import time
from typing import Optional
from config import GROQ_API_KEY, LLM_PROVIDER, LLM_MODEL

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Wrapper around the Groq LLM API.
    Handles retries, JSON mode, and error handling.
    """
    
    def __init__(self):
        self.provider = LLM_PROVIDER
        self.model = LLM_MODEL
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
        logger.info(f"Initializing LLM Client for provider: {self.provider}, model: {self.model}")
        
        if self.provider == "groq":
            if not GROQ_API_KEY:
                raise ValueError("GROQ_API_KEY not set in environment or .env file.")
            try:
                from groq import Groq
                self.client = Groq(api_key=GROQ_API_KEY)
            except ImportError:
                raise ImportError("groq is not installed. Please run pip install groq")
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}. Must be 'groq'.")
        
    def call_llm(self, system_prompt: str, user_prompt: str, 
                json_mode: bool = True, temperature: float = 0.1,
                model: Optional[str] = None) -> str:
        """
        Makes an LLM API call with retry logic.
        
        Args:
            system_prompt: System instructions
            user_prompt: The actual query/content
            json_mode: Whether to enforce JSON output
            temperature: Lower = more deterministic
            model: Optional model override (e.g. LLM_MODEL_EXTRACTION)
            
        Returns:
            Raw LLM response text
            
        Raises:
            Exception: After max retries exhausted
        """
        active_model = model or self.model
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=active_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"} if json_mode else None,
                    max_tokens=4096,
                )
                result = response.choices[0].message.content
                
                logger.info(f"LLM call successful (attempt {attempt})")
                return result
                
            except Exception as e:
                logger.warning(
                    f"LLM call attempt {attempt}/{self.max_retries} failed: {str(e)}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
                else:
                    logger.error(f"LLM call failed after {self.max_retries} attempts")
                    raise