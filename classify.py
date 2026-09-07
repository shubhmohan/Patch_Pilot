import json
import os

from groq import Groq

client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """You are a CI failure triage assistant. Given raw CI logs, you:
1. Classify the failure as one of: FLAKY_TEST, REAL_BUG, ENV_CONFIG
2. Give a one-paragraph root-cause explanation
3. Suggest a concrete next step or fix

Respond ONLY as JSON, no preamble, no markdown fences:
{"classification": "...", "explanation": "...", "suggested_fix": "..."}"""

# Groq deprecated its older Llama chat models (llama-3.3-70b-versatile,
# llama-3.1-8b-instant) in mid-2026. This is the current recommended
# general-purpose replacement. If you get a "model not found" or
# "decommissioned" error, check console.groq.com/docs/deprecations for
# whatever the current recommended model is and swap this constant.
MODEL = "openai/gpt-oss-120b"


def classify_failure(log_text: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here are the failing CI logs:\n\n{log_text[:8000]}"},
        ],
    )
    text = response.choices[0].message.content or "{}"
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"classification": "UNKNOWN", "explanation": text, "suggested_fix": ""}