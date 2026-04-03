"""
Flashcard Generation Service
Extracts key concepts from knowledge base documents and generates flashcards.
"""
import json
import re
import time
import httpx
from typing import List, Dict, Any
from pathlib import Path

from workflow_engine.logger import get_logger
from fastapi_app.schemas import Flashcard

log = get_logger(__name__)


async def generate_flashcards_with_llm(
    text_content: str,
    api_url: str,
    api_key: str,
    model: str,
    language: str,
    card_count: int,
) -> List[Flashcard]:
    """
    Generate flashcards from text content using LLM.

    Args:
        text_content: Document text content
        api_url: LLM API URL
        api_key: API Key
        model: Model name
        language: Language (zh/en)
        card_count: Number of flashcards to generate

    Returns:
        List of Flashcards
    """
    # Limit text length to avoid token limits
    max_chars = 10000
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars] + "..."

    # Build Prompt
    prompt = _build_flashcard_prompt(text_content, language, card_count)

    log.info(f"[flashcard_service] Starting LLM call for Flashcards, model: {model}, count: {card_count}")

    try:
        # Ensure API URL contains full path
        if not api_url.endswith('/chat/completions'):
            if api_url.endswith('/'):
                api_url = api_url + 'chat/completions'
            else:
                api_url = api_url + '/chat/completions'

        # Call LLM API
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        # Parse LLM response
        content = result["choices"][0]["message"]["content"]
        flashcards = _parse_flashcards_from_llm_response(content, card_count)

        log.info(f"[flashcard_service] Successfully generated {len(flashcards)} flashcards")
        return flashcards

    except Exception as e:
        log.error(f"[flashcard_service] LLM call failed: {e}")
        raise Exception(f"Failed to generate flashcards: {str(e)}")


def _build_flashcard_prompt(text_content: str, language: str, card_count: int) -> str:
    """Build prompt for flashcard generation."""
    lang_name = "Chinese" if language == "zh" else "English"

    prompt = f"""You are a professional educational content expert, skilled at extracting key knowledge points from materials and creating flashcards.

Please extract {card_count} most important knowledge points from the content below and generate a flashcard for each.

Requirements:
1. Question must be clear, specific, and easy to remember.
2. Answer must be accurate and concise (under 100 words).
3. Prioritize core concepts, definitions, important facts, and key terms.
4. Use {lang_name} for questions and answers.
5. Can include different types of questions (concept explanation, fill-in-the-blank, Q&A, etc.).

Content:
{text_content}

Please return in JSON array format, each flashcard containing:
- question: Question text
- answer: Answer text
- type: Type (qa/concept/fill_blank)
- source_excerpt: Relevant excerpt from the source (optional, max 100 words)

Example Format:
[
  {{
    "question": "What is machine learning?",
    "answer": "Machine learning is a branch of AI that uses algorithms to allow computers to learn patterns from data.",
    "type": "qa",
    "source_excerpt": "Machine Learning is..."
  }}
]

Return only the JSON array, no extra explanation."""

    return prompt


def _try_parse_json_array(json_str: str):
    """Attempt to parse JSON array, back off to the last complete object if needed."""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    brace_depth = 0
    in_string = False
    escape = False
    candidates = []
    for i, ch in enumerate(json_str):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0:
                candidates.append(i)

    for pos in reversed(candidates):
        attempt = json_str[:pos + 1] + ']'
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No valid JSON array found", json_str, 0)


def _parse_flashcards_from_llm_response(content: str, card_count: int) -> List[Flashcard]:
    """
    Parse flashcard data from LLM response.

    Args:
        content: LLM response content
        card_count: Expected flashcard count

    Returns:
        List of Flashcards
    """
    try:
        # Extract JSON (handling possible markdown blocks)
        json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*)', content)
        if json_match:
            json_str = json_match.group(1)
            json_str = re.sub(r'\s*```\s*$', '', json_str)
        else:
            # fallback: find starting [
            idx = content.find('[')
            json_str = content[idx:] if idx >= 0 else content.strip()

        flashcards_data = _try_parse_json_array(json_str)

        # Convert to Flashcard objects
        flashcards = []
        for i, card_data in enumerate(flashcards_data[:card_count]):
            question = card_data.get("question", "").strip()
            answer = card_data.get("answer", "").strip()

            if not question or not answer:
                continue

            flashcards.append(Flashcard(
                id=f"card_{int(time.time())}_{i}",
                question=question,
                answer=answer,
                type=card_data.get("type", "qa"),
                source_excerpt=card_data.get("source_excerpt", "")[:200] if card_data.get("source_excerpt") else None,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ))

        return flashcards

    except Exception as e:
        log.error(f"[flashcard_service] Failed to parse LLM response: {e}")
        raise Exception(f"Failed to parse flashcard data: {str(e)}")
