"""Groq's free AI service. Docs: https://console.groq.com/docs/api-reference"""

import json

import httpx

from stockintel.providers.base import FeedError, RateLimited

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
ATTEMPTS = 3


class GroqProvider:
    def __init__(self, key: str, client: httpx.Client | None = None):
        if not key:
            raise FeedError("Groq: GROQ_API_KEY is not set")
        self.client = client or httpx.Client(timeout=90)
        self.headers = {"Authorization": f"Bearer {key}"}

    def judge(self, system: str, user: str) -> dict:
        """Ask for a JSON reply. Groq returns HTTP 400 when the model's reply isn't valid JSON;
        its docs advise retrying, so up to three tries, the later ones slightly less rigid."""
        problem = ""
        for attempt in range(ATTEMPTS):
            body = {
                "model": MODEL,
                "temperature": 0 if attempt == 0 else 0.3,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            try:
                response = self.client.post(URL, json=body, headers=self.headers)
            except httpx.HTTPError as exc:
                raise FeedError(f"Groq: request failed ({type(exc).__name__})") from None
            if response.status_code == 429:
                raise RateLimited("Groq: free limit reached (HTTP 429)")
            if response.status_code == 400:
                problem = _error_code(response)
                continue
            if response.status_code != 200:
                raise FeedError(
                    f"Groq: HTTP {response.status_code} {_error_code(response)}".strip()
                )
            try:
                return json.loads(response.json()["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError, ValueError):
                problem = "unreadable reply"
        raise FeedError(f"Groq: no valid reply after {ATTEMPTS} tries ({problem})")


def _error_code(response: httpx.Response) -> str:
    """Groq's short error code, such as json_validate_failed. Never the request itself."""
    try:
        error = response.json().get("error") or {}
        return str(error.get("code") or error.get("type") or "")[:60]
    except ValueError:
        return ""
