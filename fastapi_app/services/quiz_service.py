"""
Quiz Generation Service
Generates multiple-choice quizzes from knowledge base documents.
"""
import json
import re
import time
import httpx
from typing import List, Dict, Any
from pathlib import Path

from workflow_engine.logger import get_logger
from fastapi_app.schemas import QuizQuestion, QuizOption

log = get_logger(__name__)


async def generate_quiz_with_llm(
    text_content: str,
    api_url: str,
    api_key: str,
    model: str,
    language: str,
    question_count: int,
) -> List[QuizQuestion]:
    """
    Generate quiz questions from text content using LLM.

    Args:
        text_content: Document text content
        api_url: LLM API URL
        api_key: API Key
        model: Model name
        language: Language (zh/en)
        question_count: Number of questions to generate

    Returns:
        List of Quiz questions
    """
    # Limit text length to avoid token limits
    max_chars = 10000
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars] + "..."

    # Build Prompt
    prompt = _build_quiz_prompt(text_content, language, question_count)

    log.info(f"[quiz_service] Starting LLM call for Quiz, model: {model}, count: {question_count}")

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
        questions = _parse_quiz_from_llm_response(content, question_count)

        log.info(f"[quiz_service] Successfully generated {len(questions)} questions")
        return questions

    except Exception as e:
        log.error(f"[quiz_service] LLM call failed: {e}")
        raise Exception(f"Failed to generate Quiz: {str(e)}")


def _build_quiz_prompt(text_content: str, language: str, question_count: int) -> str:
    """
    Build prompt for quiz generation.

    Principles:
    1. Focus on understanding and application rather than simple memorization.
    2. Reasonable options with distracting incorrect answers.
    3. Clear answers based on the document.
    4. Cover key knowledge points.
    """
    if language == "zh":
        prompt = f"""Based on the following document content, generate {question_count} high-quality multiple-choice quiz questions.

Document Content:
{text_content}

Requirements:
1. Question Type: Multiple choice, each question must have exactly 4 options (A, B, C, D)
2. Test understanding and application, clear and unambiguous, with plausible distractors
3. Difficulty Distribution: Easy 30%, Medium 50%, Hard 20%
4. explanation field: 1-2 sentences briefly explaining the reason for the correct answer, do not analyze each incorrect option individually

Please return strictly in the following JSON format (do not add extra fields):
```json
[
  {{
    "id": "q1",
    "question": "Question content",
    "options": [
      {{"label": "A", "text": "Option A"}},
      {{"label": "B", "text": "Option B"}},
      {{"label": "C", "text": "Option C"}},
      {{"label": "D", "text": "Option D"}}
    ],
    "correct_answer": "A",
    "explanation": "Short explanation (1-2 sentences)"
  }}
]
```

Please ensure the returned JSON is complete and valid."""
    else:
        prompt = f"""Based on the following document content, generate {question_count} high-quality multiple-choice quiz questions.

Document Content:
{text_content}

Requirements:
1. Question Type: Multiple choice, each question must have exactly 4 options (A, B, C, D)
2. Test understanding and application, not just memorization. Clear and unambiguous.
3. Difficulty Distribution: Easy 30%, Medium 50%, Hard 20%
4. explanation field: 1-2 sentences briefly explaining why the answer is correct. Do NOT analyze each wrong option.

Return strictly in this JSON format (no extra fields):
```json
[
  {{
    "id": "q1",
    "question": "Question text",
    "options": [
      {{"label": "A", "text": "Option A"}},
      {{"label": "B", "text": "Option B"}},
      {{"label": "C", "text": "Option C"}},
      {{"label": "D", "text": "Option D"}}
    ],
    "correct_answer": "A",
    "explanation": "Brief explanation (1-2 sentences)"
  }}
]
```

Ensure the response is complete, valid JSON."""

    return prompt


def _try_parse_json_array(json_str: str):
    """Attempt to parse JSON array, back off to the last complete object if needed."""
    # Try directly first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Find positions of all top-level '}' (marking ends of question objects)
    # Try truncation + closing from end to beginning
    brace_depth = 0
    bracket_depth = 0
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
        elif ch == '[':
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1

    # Attempt from the last complete object backwards
    for pos in reversed(candidates):
        attempt = json_str[:pos + 1] + ']'
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No valid JSON array found", json_str, 0)


def _parse_quiz_from_llm_response(content: str, question_count: int) -> List[QuizQuestion]:
    """
    Parse Quiz questions from LLM response content.
    """
    try:
        # Attempt JSON extraction (might be in markdown blocks)
        # Use greedy match for truncated content without closing ```
        json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*)', content)
        if json_match:
            json_str = json_match.group(1)
            # Remove possible trailing ```
            json_str = re.sub(r'\s*```\s*$', '', json_str)
        else:
            json_str = content.strip()

        questions_data = _try_parse_json_array(json_str)

        # Convert to QuizQuestion objects
        questions = []
        for i, q_data in enumerate(questions_data[:question_count]):
            options = []
            for opt in q_data.get("options", [])[:4]:
                options.append(QuizOption(
                    label=opt.get("label", ""),
                    text=opt.get("text", "")
                ))
            while len(options) < 4:
                label = chr(65 + len(options))
                options.append(QuizOption(label=label, text=""))

            question = QuizQuestion(
                id=q_data.get("id", f"q{i+1}"),
                question=q_data.get("question", ""),
                options=options,
                correct_answer=q_data.get("correct_answer", "A"),
                explanation=q_data.get("explanation", ""),
            )
            questions.append(question)

        if not questions:
            raise Exception("Question list is empty after parsing")

        log.info(f"[quiz_service] Successfully parsed {len(questions)} questions (requested {question_count})")
        return questions

    except Exception as e:
        log.error(f"[quiz_service] Failed to parse Quiz: {e}")
        log.error(f"[quiz_service] LLM Response: {content[:500]}")
        raise Exception(f"Failed to parse Quiz: {str(e)}")

