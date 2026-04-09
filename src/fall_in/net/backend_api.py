"""
Minimal REST client helpers for the local Fall-In backend.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

REST_BASE_URL = "http://localhost:8000"


def request_json(
    method: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    url = REST_BASE_URL + path
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        url,
        data=body,
        method=method.upper(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", str(exc))
        except Exception:
            detail = str(exc)
        raise RuntimeError(detail)
    except OSError as exc:
        raise RuntimeError(f"서버에 연결할 수 없습니다: {exc}")


def get_json(path: str, token: str, timeout: float = 8.0) -> dict[str, Any]:
    return request_json("GET", path, token=token, timeout=timeout)


def post_json(
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    return request_json("POST", path, payload=payload, token=token, timeout=timeout)


def put_json(
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    return request_json("PUT", path, payload=payload, token=token, timeout=timeout)
