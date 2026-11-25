"""검색어 조사: 네이버 자동완성 검색어와 검색 결과의 블로그 제목.

제목·태그·본문에 사람들이 실제로 검색하는 말을 자연스럽게 넣기 위한 참고 자료다.
다른 블로그 제목은 어떤 검색어 조합이 쓰이는지 보는 용도로만 쓰고, 문장을 가져오지 않는다.

필요한 네트워크 주소: ac.search.naver.com, m.search.naver.com
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
from typing import Any

from .placeinfo import SEARCH_URL, PlaceError, _get

AC_URL = "https://ac.search.naver.com/nx/ac?"


def suggest(query: str) -> list[str]:
    """네이버 자동완성 검색어 (많이 찾는 순)."""
    params = {"q": query, "con": 1, "frm": "nv", "ans": 2, "r_format": "json", "r_enc": "UTF-8",
              "r_unicode": 0, "t_koreng": 1, "run": 2, "rev": 4, "q_enc": "UTF-8", "st": 100}
    text = _get(AC_URL + urllib.parse.urlencode(params), referer="https://search.naver.com/")
    try:
        items = json.loads(text).get("items") or [[]]
    except json.JSONDecodeError as e:
        raise PlaceError("자동완성 결과를 읽지 못했어요.") from e
    return [x[0] for x in items[0] if x and isinstance(x[0], str)]


def blog_titles(query: str, limit: int = 10) -> list[str]:
    """네이버 모바일 검색 결과에 나온 블로그 글 제목 (검색어 단어가 들어간 것만)."""
    text = _get(SEARCH_URL + urllib.parse.urlencode({"query": query}))
    words = [w for w in query.split() if len(w) >= 2]
    titles: list[str] = []
    for m in re.finditer(r'href="https://(?:m\.)?blog\.naver\.com/[^"]+"[^>]*>(.*?)</a>', text, re.S):
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if 8 <= len(title) <= 80 and title not in titles and any(w in title for w in words):
            titles.append(title)
    return titles[:limit]


def research(area: str, name: str, foods: list[str]) -> dict[str, Any]:
    """동네·가게 이름·음식 종류로 검색어를 모은다. 일부가 실패해도 나머지는 돌려준다."""
    queries = []
    for food in foods:
        queries.append(f"{area} {food}".strip())
    queries += [f"{area} 맛집".strip(), name]
    result: dict[str, Any] = {"suggestions": {}, "blog_titles": [], "errors": []}
    for q in dict.fromkeys(q for q in queries if q):
        try:
            result["suggestions"][q] = suggest(q)[:10]
        except PlaceError as e:
            result["errors"].append(f"{q}: {e}")
    for q in dict.fromkeys(q for q in queries[:2] if q):
        try:
            for t in blog_titles(q):
                if t not in result["blog_titles"]:
                    result["blog_titles"].append(t)
        except PlaceError as e:
            result["errors"].append(f"{q}: {e}")
    return result
