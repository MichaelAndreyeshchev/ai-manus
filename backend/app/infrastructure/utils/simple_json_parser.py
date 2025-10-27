import json
import re
from typing import Any, Dict, List, Optional, Union
import logging

from app.domain.utils.json_parser import JsonParser


logger = logging.getLogger(__name__)


class SimpleJsonParser(JsonParser):
    """
    Lightweight JSON parser without any LLM dependency.
    Tries multiple local strategies to extract/clean JSON strings.
    """

    def __init__(self):
        self._strategies = [
            self._try_direct_parse,
            self._try_markdown_block_parse,
            self._try_cleanup_and_parse,
        ]

    async def parse(self, text: str, default_value: Optional[Any] = None) -> Union[Dict, List, Any]:
        logger.info(f"Parsing text (simple): {text}")
        if not text or not text.strip():
            if default_value is not None:
                return default_value
            raise ValueError("Empty input string")

        cleaned_output = text.strip()

        for strategy in self._strategies:
            try:
                result = await strategy(cleaned_output)
                if result is not None:
                    logger.info(f"Successfully parsed (simple) using: {strategy.__name__}")
                    return result
            except Exception as e:
                logger.warning(f"Simple strategy {strategy.__name__} failed: {str(e)}")
                continue

        if default_value is not None:
            logger.warning("All simple parsing strategies failed, returning default value")
            return default_value

        raise ValueError(f"Failed to parse JSON from text: {text[:1000]}...")

    async def _try_direct_parse(self, text: str) -> Optional[Any]:
        return json.loads(text)

    async def _try_markdown_block_parse(self, text: str) -> Optional[Any]:
        patterns = [
            r'```json\s*\n(.*?)\n```',
            r'```\s*\n(.*?)\n```',
            r'`([^`]*)`',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue
        return None

    async def _try_cleanup_and_parse(self, text: str) -> Optional[Any]:
        prefixes = ["json:", "result:", "output:", "response:"]
        suffixes = [".", "..."]

        cleaned = text
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
        for suffix in suffixes:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()

        cleaned = self._fix_json_formatting(cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    def _fix_json_formatting(self, text: str) -> str:
        text = re.sub(r"(?<!\\)'([^']*?)(?<!\\)'", r'"\1"', text)
        text = re.sub(r',\s*(?=[}\]])', '', text)
        text = re.sub(r'(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)

        def fix_unescaped_quotes_in_values(match):
            key_part = match.group(1)
            value_content = match.group(2)
            escaped_content = re.sub(r'(?<!\\)"', r'\\"', value_content)
            return f'{key_part}{escaped_content}"'

        text = re.sub(r'("[\w\s\-_]+"\s*:\s*")(.*?)"(?=\s*[,}\]])', fix_unescaped_quotes_in_values, text)
        return text


