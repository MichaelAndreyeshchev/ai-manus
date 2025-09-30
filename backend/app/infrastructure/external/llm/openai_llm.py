from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI, BadRequestError
from app.domain.external.llm import LLM
from app.core.config import get_settings
import logging


logger = logging.getLogger(__name__)

class OpenAILLM(LLM):
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.api_base
        )
        
        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        logger.info(f"Initialized OpenAI LLM with model: {self._model_name}")
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def temperature(self) -> float:
        return self._temperature
    
    @property
    def max_tokens(self) -> int:
        return self._max_tokens
    
    async def ask(self, messages: List[Dict[str, str]], 
                tools: Optional[List[Dict[str, Any]]] = None,
                response_format: Optional[Dict[str, Any]] = None,
                tool_choice: Optional[str] = None) -> Dict[str, Any]:
        """Send chat request to OpenAI API with smart fallbacks.

        Fallbacks handled:
          - If the model rejects 'max_tokens', retry using 'max_completion_tokens'.
          - If the model rejects custom 'temperature', retry without temperature (default 1).
        """
        # Build base kwargs
        base_kwargs: Dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
        }
        if response_format is not None:
            base_kwargs["response_format"] = response_format
        if tools is not None:
            base_kwargs["tools"] = tools
            base_kwargs["parallel_tool_calls"] = False
        if tool_choice is not None:
            base_kwargs["tool_choice"] = tool_choice

        # Prepare mutable kwargs
        kwargs: Dict[str, Any] = dict(base_kwargs)
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        tokens_key = "max_tokens"
        kwargs[tokens_key] = self._max_tokens

        # Attempt with adaptive retries
        for attempt in range(3):
            try:
                logger.debug(
                    f"OpenAI request attempt={attempt+1} model={self._model_name} "
                    f"tokens_key={tokens_key} temp={'set' if 'temperature' in kwargs else 'default'} "
                    f"tools={bool(tools)}"
                )
                response = await self.client.chat.completions.create(**kwargs)
                logger.debug(f"Response from OpenAI: {response.model_dump()}")
                return response.choices[0].message.model_dump()
            except BadRequestError as e:
                message = str(e)
                updated = False
                # Handle unsupported max_tokens
                if ("Unsupported parameter: 'max_tokens'" in message or "param': 'max_tokens'" in message or "max_tokens" in message) and tokens_key != "max_completion_tokens":
                    value = kwargs.pop(tokens_key, None)
                    tokens_key = "max_completion_tokens"
                    if value is not None:
                        kwargs[tokens_key] = value
                    logger.info("Model rejected max_tokens; retrying with max_completion_tokens")
                    updated = True
                # Handle unsupported temperature custom value
                if ("Unsupported value: 'temperature'" in message or "param': 'temperature'" in message) and "temperature" in kwargs:
                    kwargs.pop("temperature", None)
                    logger.info("Model rejected non-default temperature; retrying with default (omit temperature)")
                    updated = True
                if updated:
                    continue
                logger.error(f"BadRequestError calling OpenAI API: {message}")
                raise
            except Exception as e:
                logger.error(f"Error calling OpenAI API: {str(e)}")
                raise
