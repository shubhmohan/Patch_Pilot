import json
import os

from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a CI failure triage assistant. Given raw CI logs, you:
1. Classify the failure as one of: FLAKY_TEST, REAL_BUG, ENV_CONFIG
2. Give a one-paragraph root-cause explanation
3. Suggest a concrete next step or fix

Respond ONLY as JSON, no preamble, no markdown fences:
{"classification": "...", "explanation": "...", "suggested_fix": "..."}"""


def classify_failure(log_text: str) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Here are the failing CI logs:\n\n{log_text[:8000]}"}
        ],
    )
    text = next((block.text for block in response.content if block.type == "text"), "{}")
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"classification": "UNKNOWN", "explanation": text, "suggested_fix": ""}
