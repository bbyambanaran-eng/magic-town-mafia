"""Small JSON GET helper. No API keys are read or sent."""

from __future__ import annotations

import requests

from magic_town.errors import FetchError

USER_AGENT = "MagicTown/0.1 (educational Streamlit app; public weather and GBIF data)"


def get_json(url: str, params: dict) -> tuple[dict, str]:
    """Return parsed JSON and the final HTTPS URL that produced it."""
    try:
        response = requests.get(
            url,
            params=params,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=(15, 30),
        )
    except requests.Timeout as exc:
        raise FetchError("timeout", str(exc)) from exc
    except requests.RequestException as exc:
        raise FetchError("network", str(exc)) from exc

    final_url = response.url
    if not final_url.startswith("https://"):
        raise FetchError("shape", "response URL was not https")

    if response.status_code != 200:
        body = " ".join(response.text[:300].split())
        raise FetchError("http", f"HTTP {response.status_code}: {body}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FetchError("json", str(exc)) from exc

    if not isinstance(payload, dict):
        raise FetchError("shape", "top-level JSON is not an object")
    return payload, final_url
