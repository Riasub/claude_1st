"""초안을 붙여 넣기 좋은 파일로 만들기: post.txt, tags.txt, preview.html."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

DIVIDER = "━━━━━━━━━━━━━━━"


def disclosure(visit: dict[str, Any]) -> str:
    """협찬 표시 (공정위 추천·보증 심사지침: 글 첫 부분에 경제적 대가를 밝힘)."""
    if not visit.get("sponsored"):
        return ""
    note = visit.get("sponsor_note") or "업체로부터 제품 또는 서비스를 제공받아"
    return f"이 글은 {note} 작성한 후기입니다."


def _won(price: Any) -> str:
    try:
        return f"{int(price):,}원"
    except (TypeError, ValueError):
        return str(price)


def info_lines(visit: dict[str, Any], place_info: dict[str, Any] | None) -> list[tuple[str, str]]:
    place = visit.get("place", {})
    v = visit.get("visit", {})
    found = place_info or {}
    rows = [
        ("상호", place.get("name", "")),
        ("주소", place.get("address") or found.get("road_address") or found.get("address", "")),
        ("지역", "" if place.get("address") or found else place.get("area", "")),
        ("전화", found.get("telephone", "")),
        ("영업시간", place.get("hours", "")),
        ("주차", v.get("parking", "")),
        ("웨이팅", v.get("waiting", "")),
        ("방문일", v.get("date", "")),
    ]
    menus = [
        m["name"] + (f" {_won(m['price'])}" if m.get("price") not in (None, "") else "")
        for m in visit.get("menus", [])
        if isinstance(m, dict) and m.get("name")
    ]
    if menus:
        rows.append(("메뉴", ", ".join(menus)))
    if found.get("conveniences"):
        rows.append(("편의시설", ", ".join(found["conveniences"])))
    if found.get("link"):
        rows.append(("네이버 지도", found["link"]))
    return [(k, str(val)) for k, val in rows if str(val).strip()]


def place_marker(visit: dict[str, Any]) -> str:
    """글 맨 끝, 네이버 에디터의 '장소' 버튼으로 지도 카드를 넣을 자리."""
    name = visit.get("place", {}).get("name", "")
    return f"[📍 장소: {name}]" if name else ""


PLACE_HELP = "네이버 블로그 에디터의 '장소' 버튼으로 가게를 검색해 이 자리에 지도 카드를 넣으세요."


def post_text(post: dict[str, Any], visit, place_info) -> str:
    parts: list[str] = []  # 제목은 네이버 에디터의 제목 칸에 따로 넣으므로 본문에서 뺀다
    if d := disclosure(visit):
        parts += [d, ""]
    for b in post["blocks"]:
        if b["kind"] == "photo":
            parts.append(f"[사진 {b['photo']}]")
            if b["text"]:
                parts.append(b["text"])
        elif b["kind"] == "heading":
            parts.append(f"▶ {b['text']}")
        else:
            parts.append(b["text"])
        parts.append("")
    info = info_lines(visit, place_info)
    if info:
        parts += [DIVIDER, "📍 가게 정보"] + [f"{k} : {val}" for k, val in info] + [DIVIDER, ""]
    if marker := place_marker(visit):
        parts += [marker, ""]
    return "\n".join(parts).rstrip() + "\n"


def tags_text(post: dict[str, Any]) -> str:
    return " ".join("#" + t for t in post["tags"]) + "\n"


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def preview_html(post: dict[str, Any], visit, place_info) -> str:
    body: list[str] = []
    if d := disclosure(visit):
        body.append(f'<p class="disclosure">{_e(d)}</p>')
    for b in post["blocks"]:
        if b["kind"] == "photo":
            cap = f"<figcaption>{_e(b['text'])}</figcaption>" if b["text"] else ""
            body.append(
                f'<figure><span class="badge">사진 {b["photo"]}</span>'
                f'<img src="photos/{b["photo"]:02d}.jpg" alt="사진 {b["photo"]}">{cap}</figure>'
            )
        elif b["kind"] == "heading":
            body.append(f"<h2>{_e(b['text'])}</h2>")
        else:
            body.append(f"<p>{_e(b['text']).replace(chr(10), '<br>')}</p>")
    info = info_lines(visit, place_info)
    if info:
        rows = "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in info)
        body.append(f'<div class="info"><h3>📍 가게 정보</h3><table>{rows}</table></div>')
    if marker := place_marker(visit):
        body.append(f'<p class="place"><strong>{_e(marker)}</strong><br>{_e(PLACE_HELP)}</p>')

    checks = "".join(f"<li>{_e(c)}</li>" for c in post["check"])
    check_box = (
        f'<aside class="check"><strong>발행 전에 확인하세요</strong><ul>{checks}</ul></aside>' if checks else ""
    )
    alts = "".join(f"<li>{_e(t)}</li>" for t in post["alt_titles"])
    alt_box = f'<details><summary>다른 제목 후보</summary><ul>{alts}</ul></details>' if alts else ""
    copy_data = json.dumps(
        {"title": post["title"], "body": post_text(post, visit, place_info), "tags": tags_text(post).strip()},
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(post["title"])}</title>
<style>
:root {{ --bg:#fff; --fg:#222; --muted:#777; --line:#e5e5e5; --accent:#03c75a; --warn:#fff6e0; --warn-line:#f0c36d; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#18191b; --fg:#e8e8e8; --muted:#9a9a9a; --line:#333; --warn:#3a3020; --warn-line:#8a6d2f; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:17px/1.8 -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; word-break:keep-all; overflow-wrap:anywhere; }}
main {{ max-width:720px; margin:0 auto; padding:24px 16px 80px; }}
.toolbar {{ position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line); padding:10px 16px; display:flex; gap:8px; flex-wrap:wrap; justify-content:center; z-index:1; }}
button {{ border:1px solid var(--accent); background:var(--accent); color:#fff; border-radius:6px; padding:6px 12px; font-size:14px; cursor:pointer; }}
button.done {{ background:transparent; color:var(--accent); }}
h1 {{ font-size:26px; line-height:1.4; }}
h2 {{ font-size:20px; margin-top:36px; border-left:4px solid var(--accent); padding-left:10px; }}
figure {{ margin:24px 0; position:relative; }}
figure img {{ width:100%; border-radius:6px; display:block; }}
figcaption {{ color:var(--muted); font-size:14px; text-align:center; margin-top:6px; }}
.badge {{ position:absolute; top:8px; left:8px; background:rgba(0,0,0,.65); color:#fff; font-size:13px; padding:2px 8px; border-radius:4px; }}
.disclosure {{ border:1px solid var(--line); padding:10px 14px; border-radius:6px; font-size:15px; color:var(--muted); }}
.info {{ border-top:2px solid var(--fg); margin-top:40px; padding-top:8px; }}
.info table {{ border-collapse:collapse; width:100%; font-size:15px; }}
.info th {{ text-align:left; width:84px; color:var(--muted); font-weight:normal; vertical-align:top; padding:4px 0; }}
.info td {{ padding:4px 0; }}
.check {{ background:var(--warn); border:1px solid var(--warn-line); border-radius:6px; padding:12px 16px; font-size:15px; }}
.check ul, details ul {{ margin:6px 0 0; padding-left:20px; }}
.place {{ border:1px dashed var(--accent); border-radius:6px; padding:12px 14px; font-size:15px; color:var(--muted); }}
.tags {{ color:var(--accent); margin-top:24px; word-break:keep-all; }}
details {{ color:var(--muted); font-size:15px; margin-top:8px; }}
</style></head>
<body>
<div class="toolbar">
  <button data-copy="title">제목 복사</button>
  <button data-copy="body">본문 복사</button>
  <button data-copy="tags">태그 복사</button>
</div>
<main>
{check_box}
<h1>{_e(post["title"])}</h1>
{alt_box}
{"".join(body)}
<p class="tags">{_e(tags_text(post).strip())}</p>
</main>
<script>
const DATA = {copy_data};
document.querySelectorAll("button[data-copy]").forEach((btn) => {{
  btn.addEventListener("click", async () => {{
    const text = DATA[btn.dataset.copy];
    try {{ await navigator.clipboard.writeText(text); }}
    catch (e) {{
      const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta);
      ta.select(); document.execCommand("copy"); ta.remove();
    }}
    btn.classList.add("done"); btn.textContent = "복사됨 ✓";
  }});
}});
</script>
</body></html>
"""


def write_outputs(draft_dir: Path, post: dict[str, Any], visit, place_info) -> list[Path]:
    files = {
        "post.json": json.dumps(post, ensure_ascii=False, indent=2) + "\n",
        "post.txt": post_text(post, visit, place_info),
        "tags.txt": tags_text(post),
        "preview.html": preview_html(post, visit, place_info),
    }
    written = []
    for name, text in files.items():
        path = draft_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
