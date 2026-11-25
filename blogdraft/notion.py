"""노션 연동: 노션 페이지 내용(JSON)으로 방문 폴더 만들기, 초안을 노션 형식으로 내보내기.

노션 API 호출 자체는 Claude Code 세션의 노션 커넥터가 하고, 여기서는 파일 변환만 한다.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .render import PLACE_HELP, disclosure, info_lines, place_marker, post_text, tags_text
from .visit import PHOTO_DIR, VISIT_FILE, VisitError, slugify

NOTION_FILE = "notion.json"
DRAFT_HEADING = "## ✍️ 블로그 초안"


def parse_menus(text: str) -> list[dict[str, Any]]:
    """'아인슈페너 6500 / 크로플 7,000원' -> [{'name': '아인슈페너', 'price': 6500}, ...]"""
    menus = []
    for part in re.split(r"[/\n,·]+(?![0-9]{3})", text or ""):
        part = part.strip(" -•\t")
        if not part:
            continue
        m = re.match(r"^(.*?)[\s:]*([0-9][0-9,]*)\s*원?\s*$", part)
        if m and m.group(1).strip():
            menus.append({"name": m.group(1).strip(), "price": int(m.group(2).replace(",", ""))})
        else:
            menus.append({"name": part})
    return menus


def _photo_date(photos: list[dict[str, Any]]) -> str:
    """방문일이 없으면 첫 사진의 촬영 날짜(EXIF)를 쓴다. 없으면 빈 문자열."""
    from .photos import _taken_at

    for item in photos:
        taken = _taken_at(Path(item["path"]))
        m = re.match(r"(\d{4}):(\d{2}):(\d{2})", taken)
        if m:
            return "-".join(m.groups())
    return ""


def import_visit(spec: dict[str, Any], root: Path) -> Path:
    """노션 페이지 정보로 방문 폴더를 만든다 (같은 페이지면 같은 폴더를 다시 씀).

    spec 예:
    {"page_url": "...", "name": "온새", "date": "2026-11-22", "type": "카페", "area": "성수동",
     "address": "", "menus": "아인슈페너 6500", "review": "...", "sponsored": false,
     "photos": [{"path": "/tmp/x/1.jpg", "ref": "notion-file-block://..."}]}
    """
    name = (spec.get("name") or "").strip()
    if not name:
        raise VisitError("노션 페이지에 가게 이름이 없어요.")
    date = (spec.get("date") or "").strip() or _photo_date(spec.get("photos") or [])
    page_key = re.sub(r"[^0-9a-f]", "", (spec.get("page_url") or "").lower())[-8:]
    folder = root / "-".join(x for x in (date, slugify(name), page_key) if x)
    photo_dir = folder / PHOTO_DIR
    if photo_dir.exists():
        shutil.rmtree(photo_dir)
    photo_dir.mkdir(parents=True)

    refs: dict[str, str] = {}
    captions: dict[str, str] = {}
    for i, item in enumerate(spec.get("photos") or [], start=1):
        src = Path(item["path"])
        if not src.is_file():
            raise VisitError(f"사진 파일이 없어요: {src}")
        dest = photo_dir / f"{i:02d}-{slugify(src.stem)}{src.suffix.lower() or '.jpg'}"
        shutil.copyfile(src, dest)
        captions[dest.name] = (item.get("caption") or "").strip()
        if item.get("ref"):
            refs[dest.name] = item["ref"]

    visit = {
        "place": {
            "name": name,
            "type": spec.get("type") or "",
            "area": spec.get("area") or "",
            "address": spec.get("address") or "",
            "naver_search": spec.get("naver_search", True),
            "search_query": spec.get("search_query") or "",
            "hours": spec.get("hours") or "",
        },
        "visit": {"date": date, **{k: spec[k] for k in ("with", "purpose", "waiting", "parking") if spec.get(k)}},
        "sponsored": bool(spec.get("sponsored")),
        "menus": parse_menus(spec.get("menus") or ""),
        "memo": (spec.get("review") or "").strip(),
        "photos": captions,
    }
    (folder / VISIT_FILE).write_text(
        "# 노션에서 가져온 방문 기록 (blogdraft import가 만든 파일)\n"
        + yaml.safe_dump(visit, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (folder / NOTION_FILE).write_text(
        json.dumps({"page_url": spec.get("page_url", ""), "refs": refs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return folder


def _text(s: str) -> str:
    """노션 마크다운 본문용 이스케이프."""
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = []
    for line in s.splitlines() or [""]:
        if re.match(r"^\s*([#>*+-]|\d+[.)]|`{3}|\$\$|\|)", line):
            line = "\\" + line.lstrip()
        lines.append(line)
    return "\\\n".join(lines)


def _fence(content: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", content)), default=0)
    bar = "`" * max(3, longest + 1)
    return f"{bar}text\n{content.rstrip()}\n{bar}"


def _cell(s: str) -> str:
    return _text(s).replace("|", "\\|").replace("\\\n", "<br />")


def notion_markdown(post: dict[str, Any], visit, place_info, photo_refs: dict[int, str], made_on: str) -> str:
    out = ["---", "", f"{DRAFT_HEADING} ({made_on})", ""]
    if post["check"]:
        items = "\n".join(f"- {_text(c)}" for c in post["check"])
        out += [f'<callout icon="⚠️" color="yellow_bg">\n발행 전에 확인하세요\n\n{items}\n</callout>', ""]
    out += ["### 제목", "", _fence(post["title"]), ""]
    if post["alt_titles"]:
        out += [f'<p color="gray">다른 제목 후보: {_text(" / ".join(post["alt_titles"]))}</p>', ""]
    out += ["### 본문 (복사용)", "", _fence(post_text(post, visit, place_info)), ""]
    out += ["### 태그", "", _fence(tags_text(post)), ""]
    out += ["### 미리보기", ""]
    if d := disclosure(visit):
        out += [f'<quote color="gray">{_text(d)}</quote>', ""]
    for b in post["blocks"]:
        if b["kind"] == "photo":
            label = f"사진 {b['photo']}" + (f" · {b['text']}" if b["text"] else "")
            ref = photo_refs.get(b["photo"])
            if ref:
                out.append(f'<image source="{ref}">{_text(label)}</image>')
            else:
                out.append(f"📷 {_text('[' + label + ']')}")
        elif b["kind"] == "heading":
            out.append(f"#### {_text(b['text'])}")
        else:
            out.append(_text(b["text"]))
        out.append("")
    info = info_lines(visit, place_info)
    if info:
        out += ["| 가게 정보 | |", "| --- | --- |"] + [f"| {_cell(k)} | {_cell(v)} |" for k, v in info] + [""]
    if marker := place_marker(visit):
        out += [f'<callout icon="📍" color="green_bg">\n{_text(marker)}\n\n{_text(PLACE_HELP)}\n</callout>', ""]
    return "\n".join(out).rstrip() + "\n"


def photo_refs_for(folder: Path, draft_photos: Path) -> dict[int, str]:
    """글 속 사진 번호 -> 노션 원본 이미지 참조."""
    nfile = folder / NOTION_FILE
    manifest = draft_photos / "photos.json"
    if not nfile.is_file() or not manifest.is_file():
        return {}
    refs = json.loads(nfile.read_text(encoding="utf-8")).get("refs", {})
    return {
        item["index"]: refs[item["source"]]
        for item in json.loads(manifest.read_text(encoding="utf-8"))
        if item["source"] in refs
    }
