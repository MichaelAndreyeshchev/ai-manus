from typing import List, Dict, Any, Optional
import httpx
from app.domain.external.llm import LLM
from app.core.config import get_settings
import logging
import json


logger = logging.getLogger(__name__)

class N8nLLM(LLM):
    def __init__(self):
        settings = get_settings()
        self.webhook_url = settings.n8n_webhook_url
        
        self._model_name = "n8n-workflow"
        self._temperature = 0.7
        self._max_tokens = 2000
        logger.info(f"Initialized N8n LLM with webhook: {self.webhook_url}")
    
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
        """Send chat request to n8n workflow"""
        try:
            user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            
            payload = {
                "input": user_message,
                "sessionId": "default_session"  # This can be made dynamic later
            }
            
            logger.debug(f"Sending request to n8n workflow: {payload}")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                response_text = response.text
                logger.debug(f"Response from n8n: {response_text}")
                
                return {
                    "role": "assistant",
                    "content": response_text,
                    "tool_calls": None
                }
        except Exception as e:
            logger.error(f"Error calling n8n workflow: {str(e)}")
            raise
