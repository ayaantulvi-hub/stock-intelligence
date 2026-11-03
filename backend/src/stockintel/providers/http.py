"""Shared HTTP handling. Errors carry the status only, so URLs with keys are never logged."""

import httpx

from stockintel.providers.base import FeedError, RateLimited


def get_json(client: httpx.Client, url: str, name: str, **kwargs) -> object:
    try:
        response = client.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise FeedError(f"{name}: request failed ({type(exc).__name__})") from None
    if response.status_code == 429:
        raise RateLimited(f"{name}: rate limit reached (HTTP 429)")
    if response.status_code != 200:
        raise FeedError(f"{name}: HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise FeedError(f"{name}: response was not valid JSON") from None
