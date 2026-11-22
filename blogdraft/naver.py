"""네이버 지역 검색 API로 가게 주소/전화번호/분류 찾기.

https://developers.naver.com/docs/serviceapi/search/local/local.md
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

LOCAL_SEARCH_URL = "https://openapi.naver.com/v1/search/local.json"


class NaverError(Exception):
    pass


def credentials() -> tuple[str, str] | None:
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        return None
    return cid, secret


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def search_place(query: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    creds = credentials()
    if creds is None:
        raise NaverError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 설정되지 않았어요.")
    url = LOCAL_SEARCH_URL + "?" + urllib.parse.urlencode({"query": query, "display": 5})
    req = urllib.request.Request(
        url,
        headers={"X-Naver-Client-Id": creds[0], "X-Naver-Client-Secret": creds[1]},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise NaverError(f"네이버 검색 실패 (HTTP {e.code}): {body}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise NaverError(f"네이버 검색에 연결하지 못했어요: {e}") from e

    results = []
    for item in data.get("items", []):
        results.append(
            {
                "name": _clean(item.get("title", "")),
                "category": _clean(item.get("category", "")),
                "address": item.get("address", "").strip(),
                "road_address": item.get("roadAddress", "").strip(),
                "telephone": item.get("telephone", "").strip(),
                "link": item.get("link", "").strip(),
            }
        )
    return results


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def best_match(name: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """가게 이름이 들어 있는 첫 결과. 이름이 전혀 안 맞으면 None (엉뚱한 가게 방지)."""
    target = _norm(name)
    for r in results:
        cand = _norm(r["name"])
        if target in cand or cand in target:
            return r
    return None
