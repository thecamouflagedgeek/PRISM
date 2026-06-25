import subprocess
import json

MODEL_NAME = "qwen2.5:3b"


def call_llm(prompt: str):

    result = subprocess.run(
        ["ollama", "run", MODEL_NAME],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        raise Exception(result.stderr)

    return result.stdout.strip()


def extract_financial_data(text: str):

    from llm.prompts import SALARY_PROMPT

    prompt = SALARY_PROMPT.format(
        text=text[:10000]
    )

    raw = call_llm(prompt)

    try:
        return json.loads(raw)

    except Exception:
        print("LLM OUTPUT:")
        print(raw)

        raise ValueError(
            "Failed to parse LLM JSON"
        )