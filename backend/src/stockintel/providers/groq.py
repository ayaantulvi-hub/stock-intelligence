"""Groq's free AI service. Docs: https://console.groq.com/docs/api-reference"""

import json

import httpx

from stockintel.providers.base import FeedError, RateLimited

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"


class GroqProvider:
    def __init__(self, key: str, client: httpx.Client | None = None):
        if not key:
            raise FeedError("Groq: GROQ_API_KEY is not set")
        self.client = client or httpx.Client(timeout=90)
        self.headers = {"Authorization": f"Bearer {key}"}

    def judge(self, system: str, user: str) -> dict:
        body = {
            "model": MODEL,
            "temperature": 0,
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
        if response.status_code != 200:
            raise FeedError(f"Groq: HTTP {response.status_code}")
        try:
            return json.loads(response.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise FeedError("Groq: the reply wasn't readable") from None
