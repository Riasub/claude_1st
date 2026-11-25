"""후기 초안 쓰기: 프롬프트 만들기, Claude 호출, 결과 검증."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .photos import Photo, image_block

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"

POST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "블로그 제목"},
        "alt_titles": {"type": "array", "items": {"type": "string"}, "description": "다른 제목 후보 2개"},
        "blocks": {
            "type": "array",
            "description": "본문을 위에서 아래 순서로. 사진 자리는 kind=photo",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["heading", "text", "photo"]},
                    "text": {"type": "string", "description": "heading/text의 내용. photo면 사진 아래 짧은 설명(없으면 빈 문자열)"},
                    "photo": {"type": "integer", "description": "kind=photo일 때 사진 번호(1부터). 아니면 0"},
                },
                "required": ["kind", "text", "photo"],
                "additionalProperties": False,
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}, "description": "# 없이, 띄어쓰기 없이 8~12개"},
        "check": {
            "type": "array",
            "items": {"type": "string"},
            "description": "발행 전에 글쓴이가 확인해야 할 점 (사진만 보고 추측한 부분 등)",
        },
    },
    "required": ["title", "alt_titles", "blocks", "tags", "check"],
    "additionalProperties": False,
}

RULES = """\
당신은 카페·음식점 방문 후기를 네이버 블로그 글로 다듬어 주는 편집자입니다.
글쓴이가 직접 남긴 방문 기록과 사진을 받아, 글쓴이 본인이 쓴 것처럼 자연스러운 후기 초안을 씁니다.

사실에 관한 규칙 (가장 중요):
- 방문 기록에 적혀 있거나 사진에서 분명히 보이는 것만 씁니다.
- 기록에 없는 가격, 메뉴 이름, 영업시간, 위치, 직원 응대, 맛 평가는 지어내지 않습니다.
- 사진만 보고 짐작한 내용(예: 메뉴 이름, 재료)은 단정하지 말고 check 목록에 확인 요청으로 남깁니다.
- 기록이 짧으면 글도 짧게 씁니다. 분량을 채우려고 꾸며내지 않습니다.
- 다른 가게와 비교하거나 다른 사람의 평가를 인용하지 않습니다.
- 네이버 메뉴판이 있으면, 글쓴이가 먹은 메뉴를 메뉴판의 정확한 이름과 가격으로 씁니다.
  어느 메뉴인지 확실하지 않으면(예: 같은 종류가 여러 개) 단정하지 말고 check에 확인 요청을 남깁니다.
  가격이 범위(예: 7,000~24,000원)로만 나와 있으면 글쓴이가 먹은 양의 가격을 지어내지 않습니다.
- 메뉴판의 설명은 가게가 쓴 소개이므로, 쓸 때는 맛 평가가 아니라 메뉴 구성 정보로만 씁니다.
- 네이버 공개 정보(편의시설)는 "네이버 기준"처럼 출처를 밝혀 쓸 수 있습니다.
- "네이버 리뷰 N개", "리뷰에서 ○○ 언급이 많아요" 같은 리뷰 수·통계 문장은 쓰지 않습니다.
- 검색어 참고가 있으면 제목 ':' 뒤 한줄평·첫 문단·태그에 자연스럽게 쓰고, '최근 글에서 이미 쓴 표현'과 소제목·첫 문장·끝맺음이 겹치지 않게 씁니다.
- 다른 사람의 후기 문장이나 표현을 베끼지 않습니다(표절, 네이버 유사 문서 불이익). 제목 목록은 어떤 점이 관심을 끄는지 참고만 합니다.

형식에 관한 규칙:
- 주소, 영업시간, 전화번호 정보 칸과 협찬 표시 문구는 프로그램이 따로 넣으니 본문에 쓰지 않습니다.
- 사진은 번호마다 정확히 한 번씩 kind=photo 블록으로 배치합니다. 순서는 글 흐름에 맞게 바꿔도 됩니다.
- heading은 짧은 소제목, text는 한 문단입니다.
- tags는 동네, 가게 종류, 가게 이름, 대표 메뉴, 방문 목적 위주로 씁니다.
"""


class WriterError(Exception):
    pass


def load_style(repo_root: Path) -> str:
    path = repo_root / "style.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def system_prompt(style: str) -> str:
    return RULES + ("\n\n아래는 글쓴이가 정한 스타일 가이드입니다:\n\n" + style if style else "")


def facts_text(visit: dict[str, Any], place_info: dict[str, Any] | None) -> str:
    facts = {k: v for k, v in visit.items() if k != "photos"}
    data: dict[str, Any] = {"방문 기록": facts}
    if place_info:
        data["네이버 가게 정보 (공식)"] = {
            k: place_info[k] for k in ("name", "category") if place_info.get(k)
        }
        public = {
            "편의시설": place_info.get("conveniences"),
            "가게 한줄 소개": place_info.get("micro_reviews"),
        }
        public = {k: v for k, v in public.items() if v}
        if public:
            data["네이버 공개 정보 (인용할 때 '네이버 기준'처럼 출처를 밝힘)"] = public
        if place_info.get("blog_titles"):
            data["다른 블로그 후기 제목 (어떤 점을 강조하는지 참고만. 문장을 가져오지 않음)"] = place_info["blog_titles"]
        if place_info.get("menus"):
            data["네이버 메뉴판 (공식, 메뉴 이름·가격은 이 표기를 따름)"] = [
                {k: m[k] for k in ("name", "price", "description") if m.get(k)} for m in place_info["menus"]
            ]
    return json.dumps(data, ensure_ascii=False, indent=2)


def photo_label(p: Photo) -> str:
    return f"[사진 {p.index}]" + (f" 글쓴이 설명: {p.caption}" if p.caption else "")


def user_content(visit, place_info, photos: list[Photo], with_images: bool = True) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": "방문 기록:\n" + facts_text(visit, place_info)}]
    if photos:
        content.append({"type": "text", "text": f"사진은 모두 {len(photos)}장입니다."})
    for p in photos:
        content.append({"type": "text", "text": photo_label(p)})
        if with_images:
            content.append(image_block(p.output))
    content.append({"type": "text", "text": "위 기록으로 블로그 후기 초안을 써 주세요."})
    return content


def normalize_post(post: dict[str, Any], photo_count: int) -> dict[str, Any]:
    """모델 출력 정리: 없는 사진 번호 제거, 중복 제거, 빠진 사진은 끝에 붙이기, 태그 정리."""
    seen: set[int] = set()
    blocks = []
    for b in post.get("blocks", []):
        kind = b.get("kind")
        text = (b.get("text") or "").strip()
        if kind == "photo":
            n = int(b.get("photo") or 0)
            if 1 <= n <= photo_count and n not in seen:
                seen.add(n)
                blocks.append({"kind": "photo", "text": text, "photo": n})
        elif kind in ("heading", "text") and text:
            blocks.append({"kind": kind, "text": text, "photo": 0})
    for n in range(1, photo_count + 1):
        if n not in seen:
            blocks.append({"kind": "photo", "text": "", "photo": n})

    tags, seen_tags = [], set()
    for t in post.get("tags", []):
        t = str(t).lstrip("#").replace(" ", "").strip()
        if t and t not in seen_tags:
            seen_tags.add(t)
            tags.append(t)

    title = (post.get("title") or "").strip()
    if not title:
        raise WriterError("초안에 제목이 없어요.")
    return {
        "title": title,
        "alt_titles": [s.strip() for s in post.get("alt_titles", []) if str(s).strip()],
        "blocks": blocks,
        "tags": tags[:30],
        "check": [s.strip() for s in post.get("check", []) if str(s).strip()],
    }


def write_with_claude(system: str, content: list[dict]) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    model = os.environ.get("BLOG_MODEL", DEFAULT_MODEL)
    effort = os.environ.get("BLOG_EFFORT", DEFAULT_EFFORT)
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # 안전 필터가 거절하면 서버가 다른 모델로 다시 시도
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": POST_SCHEMA},
            },
            system=system,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError as e:
        raise WriterError("Claude API 키가 올바르지 않아요. .env의 ANTHROPIC_API_KEY를 확인하세요.") from e
    except anthropic.RateLimitError as e:
        raise WriterError("Claude API 사용량 한도에 걸렸어요. 잠시 후 다시 시도하세요.") from e
    except anthropic.BadRequestError as e:
        raise WriterError(f"Claude API 요청 오류: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise WriterError(f"Claude API 오류 (HTTP {e.status_code}). 잠시 후 다시 시도하세요.") from e
    except anthropic.APIConnectionError as e:
        raise WriterError("Claude API에 연결하지 못했어요. 인터넷 연결을 확인하세요.") from e

    if response.stop_reason == "refusal":
        raise WriterError("Claude가 이 요청을 처리하지 않았어요. 방문 기록 내용을 확인해 주세요.")
    if response.stop_reason == "max_tokens":
        raise WriterError("초안이 너무 길어서 중간에 끊겼어요. 기록을 줄이거나 다시 시도하세요.")
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise WriterError(f"초안 형식을 읽지 못했어요 (request id: {response._request_id}).") from e


def keywords_section(keywords: dict[str, Any] | None) -> str:
    if not keywords or not (keywords.get("suggestions") or keywords.get("blog_titles")):
        return ""
    lines = ["## 검색어 참고 (네이버 자동완성 · 검색 결과 블로그 제목)", "",
             "제목 뒤 검색어, 첫 문단, 태그에 실제로 많이 찾는 말을 자연스럽게 넣으세요. 같은 말을 억지로 반복하지 않습니다.",
             "다른 블로그 제목은 검색어 조합만 참고하고 문장은 가져오지 않습니다.", ""]
    for q, items in (keywords.get("suggestions") or {}).items():
        if items:
            lines.append(f"- `{q}` 자동완성: {', '.join(items)}")
    if keywords.get("blog_titles"):
        lines += ["", "검색 결과 블로그 제목:"] + [f"- {t}" for t in keywords["blog_titles"]]
    return "\n".join(lines) + "\n"


def recent_section(recent: list[dict[str, Any]] | None) -> str:
    if not recent:
        return ""
    lines = ["## 최근 글에서 이미 쓴 표현 (반복하지 말 것)", "",
             "같은 틀이 반복되면 네이버에서 비슷한 글로 보고 노출이 줄 수 있어요. 소제목 이름, 첫 문장, 끝맺음을 이 글들과 다르게 쓰세요.", ""]
    for r in recent:
        lines.append(f"- {r['title']}: 첫 문장 「{r['first']}」 / 소제목 {', '.join(r['headings'])} / 끝 문장 「{r['last']}」")
    return "\n".join(lines) + "\n"


def recent_posts(visits_root: Path, exclude: Path, limit: int = 5) -> list[dict[str, Any]]:
    """다른 방문 폴더의 post.json에서 제목·첫 문장·소제목·끝 문장을 모은다."""
    out = []
    for post_path in sorted(visits_root.glob("*/draft/post.json"), reverse=True):
        if post_path.parent.parent.resolve() == exclude.resolve():
            continue
        try:
            post = json.loads(post_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        texts = [b.get("text", "") for b in post.get("blocks", []) if b.get("kind") == "text" and b.get("text")]
        out.append({
            "title": post.get("title", ""),
            "first": texts[0][:60] if texts else "",
            "last": texts[-1][:60] if texts else "",
            "headings": [b["text"] for b in post.get("blocks", []) if b.get("kind") == "heading"],
        })
    return out[:limit]


def prompt_markdown(system: str, visit, place_info, photos: list[Photo], post_path: Path,
                    keywords: dict[str, Any] | None = None, recent: list[dict[str, Any]] | None = None) -> str:
    """API 키 없이 Claude Code 세션에서 초안을 쓰도록 넘기는 지시문."""
    photo_lines = "\n".join(f"- {photo_label(p)} 파일: `{p.output}`" for p in photos) or "- (사진 없음)"
    extra = "\n".join(s for s in (keywords_section(keywords), recent_section(recent)) if s)
    return f"""# 후기 초안 작성 요청

이 파일은 `python -m blogdraft build --no-ai`가 만들었습니다.
Claude Code 세션이라면: 아래 사진 파일을 모두 열어 본 뒤, 규칙과 기록에 따라
아래 JSON 스키마에 맞는 초안을 `{post_path}`에 저장하고 `python -m blogdraft render <방문 폴더>`를 실행하세요.

## 규칙과 스타일

{system}

## 방문 기록

```json
{facts_text(visit, place_info)}
```

## 사진

{photo_lines}

{extra}
## 출력 JSON 스키마

```json
{json.dumps(POST_SCHEMA, ensure_ascii=False, indent=2)}
```
"""
