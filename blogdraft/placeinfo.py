"""네이버 플레이스에서 가게 정보(주소, 전화, 분류, 메뉴판) 가져오기.

공식 API가 아니라 네이버 모바일 검색과 플레이스 페이지에 들어 있는 데이터를 읽는다.
네이버가 페이지 구조를 바꾸거나 접속을 막으면 실패할 수 있으니, 실패해도 초안 작성은 계속한다.
한 번에 가게 하나만, 사람이 보는 속도로 조회한다.

필요한 네트워크 주소: m.search.naver.com, m.place.naver.com
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
SEARCH_URL = "https://m.search.naver.com/search.naver?"
PLACE_URL = "https://m.place.naver.com/restaurant/{id}/menu/list"
MAP_URL = "https://map.naver.com/p/entry/place/{id}"


class PlaceError(Exception):
    pass


def _get(url: str, referer: str = "https://m.search.naver.com/", timeout: float = 15.0, attempts: int = 3) -> str:
    """연결이 끊기면(처음 몇 번 끊기는 경우가 있음) 잠깐 쉬고 다시 시도한다."""
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": referer}
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise PlaceError(f"네이버 페이지를 열지 못했어요 (HTTP {e.code}).") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == attempts:
                raise PlaceError(f"네이버에 연결하지 못했어요: {e}") from e
            time.sleep(1.5 * attempt)
    raise PlaceError("네이버에 연결하지 못했어요.")  # pragma: no cover


def _norm(s: str) -> str:
    return re.sub(r"[\s\[\]()·]+", "", s).lower()


def find_place_id(name: str, area: str = "", html_text: str | None = None) -> str | None:
    """모바일 검색 결과에서 이름이 맞는 가게의 플레이스 ID."""
    query = " ".join(x for x in (name, area) if x)
    text = html_text if html_text is not None else _get(SEARCH_URL + urllib.parse.urlencode({"query": query}))
    target = _norm(name)
    for pid, pname in re.findall(r'"id":"(\d{6,})","name":"([^"]+)"', text):
        cand = _norm(pname)
        if cand and (target == cand or target in cand or cand in target):
            return pid
    return None


def _apollo(text: str) -> dict[str, Any]:
    m = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});\s*\n", text, re.S)
    if not m:
        raise PlaceError("네이버 플레이스 페이지 구조가 바뀌어서 읽지 못했어요.")
    return json.loads(m.group(1))


def parse_place(text: str, place_id: str) -> dict[str, Any]:
    st = _apollo(text)
    base = next((v for v in st.values() if isinstance(v, dict) and v.get("__typename") == "PlaceDetailBase"), {})
    items = {k.split(":", 1)[1]: v for k, v in st.items() if k.startswith("PlaceMenuItem:")}
    categories = [v for v in st.values() if isinstance(v, dict) and v.get("__typename") == "PlaceMenuCategory"]

    ordered: list[str] = []
    for cat in categories:
        if cat.get("kind") == "recommend":
            continue
        for iid in cat.get("itemIds") or []:
            if iid in items and iid not in ordered:
                ordered.append(iid)
    ordered += [iid for iid in items if iid not in ordered]

    menus = []
    for iid in ordered:
        v = items[iid]
        price = (v.get("price") or {}).get("displayText") or ""
        menus.append(
            {
                "name": (v.get("name") or "").strip(),
                "price": price.strip(),
                "description": (v.get("description") or "").strip(),
            }
        )
    return {
        "source": "naver_place",
        "place_id": place_id,
        "name": base.get("name", ""),
        "category": base.get("category", ""),
        "road_address": base.get("roadAddress", ""),
        "address": base.get("address", ""),
        "telephone": base.get("phone") or base.get("virtualPhone") or "",
        "link": MAP_URL.format(id=place_id),
        "menus": [m for m in menus if m["name"]],
    }


def lookup(name: str, area: str = "") -> dict[str, Any]:
    """가게 이름(+동네)으로 네이버 플레이스 정보 조회. 못 찾으면 PlaceError."""
    pid = find_place_id(name, area)
    if not pid:
        query = " ".join(x for x in (name, area) if x)
        raise PlaceError(f"네이버에서 '{query}'을(를) 찾지 못했어요. 가게 이름이나 동네를 확인해 주세요.")
    return parse_place(_get(PLACE_URL.format(id=pid)), pid)


def menu_text(info: dict[str, Any]) -> str:
    """사람이 보기 좋은 메뉴판 텍스트."""
    return "\n".join(f"- {m['name']}: {m['price'] or '가격 없음'}" for m in info.get("menus", []))
