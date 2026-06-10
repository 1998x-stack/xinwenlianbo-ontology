import os, json, time, requests
from typing import Optional

DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

def _get_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY environment variable not set.\n"
                          "Set it with:  export DEEPSEEK_API_KEY='your-key-here'\n"
                          "Get a key from: https://platform.deepseek.com/api_keys")
    return key

def chat(prompt: str, system: str = "", model: str = DEFAULT_MODEL,
         temperature: float = 0.3, max_tokens: int = 2000,
         retries: int = 3) -> Optional[str]:
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}

    for attempt in range(retries):
        try:
            r = requests.post(f"{DEEPSEEK_BASE}/v1/chat/completions",
                            headers=headers, json=body, timeout=120)
            if r.status_code != 200:
                print(f"API error {r.status_code}: {r.text[:200]}")
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                return None
            return r.json()["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            print(f"Network error (attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None

def chat_json(prompt: str, system: str = "", model: str = DEFAULT_MODEL) -> Optional[dict]:
    text = chat(prompt, system, model, temperature=0.1, max_tokens=2000)
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
