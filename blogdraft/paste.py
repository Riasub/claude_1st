"""붙여넣기 페이지(paste.html): 글과 사진이 제자리에 들어간 본문을 한 번에 복사.

claude.ai 아티팩트로 올리는 것을 전제로 <html>/<head>/<body> 없이 내용만 쓴다.
사진은 data: URI로 페이지 안에 넣어서, 복사할 때 글과 함께 클립보드에 담긴다.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

from .render import DIVIDER, disclosure, info_lines, place_marker, tags_text


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _data_uri(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.standard_b64encode(path.read_bytes()).decode("ascii")


def article_html(post: dict[str, Any], visit, place_info, photo_dir: Path) -> str:
    """네이버 에디터에 붙여 넣을 본문. 에디터가 잘 받는 단순한 태그(p, b, img)만 쓴다."""
    out: list[str] = []
    if d := disclosure(visit):
        out.append(f"<p>{_e(d)}</p><p><br></p>")
    for b in post["blocks"]:
        if b["kind"] == "photo":
            img = photo_dir / f"{b['photo']:02d}.jpg"
            if img.is_file():
                out.append(f'<p><img src="{_data_uri(img)}" alt="사진 {b["photo"]}"></p>')
            else:
                out.append(f"<p>[사진 {b['photo']}]</p>")
            if b["text"]:
                out.append(f'<p class="cap">{_e(b["text"])}</p>')
        elif b["kind"] == "heading":
            out.append(f"<p><b>▶ {_e(b['text'])}</b></p>")
        else:
            out.append(f"<p>{_e(b['text']).replace(chr(10), '<br>')}</p>")
        out.append("<p><br></p>")
    info = info_lines(visit, place_info)
    if info:
        lines = [DIVIDER, "📍 가게 정보"] + [f"{k} : {v}" for k, v in info] + [DIVIDER]
        out.append("".join(f"<p>{_e(line)}</p>" for line in lines))
        out.append("<p><br></p>")
    if marker := place_marker(visit):
        out.append(f'<p class="place">{_e(marker)}</p>')
    return "\n".join(out)


def paste_html(post: dict[str, Any], visit, place_info, photo_dir: Path) -> str:
    name = visit.get("place", {}).get("name", "후기")
    checks = "".join(f"<li>{_e(c)}</li>" for c in post["check"])
    check_box = (
        f'<section class="check" aria-label="발행 전 확인"><h2>발행 전에 확인하세요</h2><ul>{checks}</ul></section>'
        if checks
        else ""
    )
    tags = tags_text(post).strip()
    data = json.dumps({"title": post["title"], "tags": tags}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<title>{_e(name)} 블로그 초안</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap">
<style>
/* 한 단 문서: 위에 복사 순서(제목 → 본문 → 태그), 아래에 실제로 붙여 넣을 본문 */
:root {{
  --bg: #f6f7f5; --paper: #ffffff; --fg: #1f2421; --muted: #66706a; --line: #dfe3df;
  --accent: #17834f; --accent-fg: #ffffff; --warn-bg: #fff6df; --warn-line: #e6c36a;
  --font: "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #151816; --paper: #1d211f; --fg: #e7ebe8; --muted: #9aa59f; --line: #333a36;
  --accent: #3fbf7f; --accent-fg: #0d1a13; --warn-bg: #33301f; --warn-line: #7d6a33; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #151816; --paper: #1d211f; --fg: #e7ebe8; --muted: #9aa59f; --line: #333a36;
  --accent: #3fbf7f; --accent-fg: #0d1a13; --warn-bg: #33301f; --warn-line: #7d6a33; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.75 var(--font); word-break: keep-all; overflow-wrap: anywhere; }}
.wrap {{ max-width: 720px; margin: 0 auto; padding-block: 24px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 20px; }}
h1 {{ font-size: 1.15rem; margin: 0; color: var(--muted); font-weight: 500; }}
h2 {{ font-size: 1rem; margin: 0 0 6px; }}
.step {{ background: var(--paper); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
  display: grid; gap: 10px; min-width: 0; }}
.step-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
.step-label {{ font-size: .8rem; letter-spacing: .06em; color: var(--muted); }}
.value {{ font-weight: 700; font-size: 1.1rem; }}
.tags {{ color: var(--accent); }}
button {{ font: inherit; font-size: .9rem; font-weight: 500; border: 1px solid var(--accent); background: var(--accent);
  color: var(--accent-fg); border-radius: 8px; padding: 6px 14px; cursor: pointer; }}
button:focus-visible {{ outline: 3px solid var(--warn-line); outline-offset: 2px; }}
button.done {{ background: transparent; color: var(--accent); }}
.check {{ background: var(--warn-bg); border: 1px solid var(--warn-line); border-radius: 10px; padding: 12px 16px; }}
.check ul {{ margin: 0; padding-left: 20px; }}
.hint {{ font-size: .85rem; color: var(--muted); margin: 0; }}
#article {{ border-top: 1px dashed var(--line); padding-top: 12px; }}
#article p {{ margin: 0; }}
#article img {{ max-width: 100%; border-radius: 6px; display: block; }}
#article .cap {{ color: var(--muted); font-size: .9rem; text-align: center; }}
#article .place {{ border: 1px dashed var(--accent); border-radius: 6px; padding: 8px 12px; color: var(--accent); font-weight: 500; }}
</style>
<main class="wrap">
  <h1>{_e(name)} · 네이버 블로그 붙여넣기</h1>
  {check_box}
  <section class="step">
    <div class="step-head"><span class="step-label">1. 제목 칸에</span><button type="button" id="copy-title">제목 복사</button></div>
    <div class="value">{_e(post["title"])}</div>
  </section>
  <section class="step">
    <div class="step-head"><span class="step-label">2. 본문에 (글 + 사진)</span><button type="button" id="copy-body">본문 전체 복사</button></div>
    <p class="hint">PC 크롬에서 열어 복사한 뒤 네이버 블로그 글쓰기 본문에 붙여 넣으세요.
      사진이 안 들어가면 사진에서 오른쪽 클릭 → 이미지 복사로 하나씩 넣을 수 있어요.
      맨 끝 [📍 장소] 자리는 에디터의 '장소' 버튼으로 지도를 넣으세요.</p>
    <div id="article">
{article_html(post, visit, place_info, photo_dir)}
    </div>
  </section>
  <section class="step">
    <div class="step-head"><span class="step-label">3. 태그 칸에</span><button type="button" id="copy-tags">태그 복사</button></div>
    <div class="tags">{_e(tags)}</div>
  </section>
</main>
<script>
const DATA = {data};
function done(btn) {{ btn.classList.add("done"); btn.textContent = "복사됨 ✓"; }}
function copySelection(node) {{
  const range = document.createRange(); range.selectNodeContents(node);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  let ok = false; try {{ ok = document.execCommand("copy"); }} catch (e) {{}}
  return ok;
}}
async function copyText(btn, text, node) {{
  try {{ await navigator.clipboard.writeText(text); done(btn); }}
  catch (e) {{ if (copySelection(node)) done(btn); else btn.textContent = "직접 선택해서 복사하세요"; }}
}}
document.getElementById("copy-title").addEventListener("click", (ev) =>
  copyText(ev.currentTarget, DATA.title, document.querySelector(".value")));
document.getElementById("copy-tags").addEventListener("click", (ev) =>
  copyText(ev.currentTarget, DATA.tags, document.querySelector(".tags")));
document.getElementById("copy-body").addEventListener("click", async (ev) => {{
  const btn = ev.currentTarget, node = document.getElementById("article");
  // 화면에서 선택해 복사하는 방식이 에디터에서 가장 자연스럽게 붙는다 (글 + 사진)
  if (copySelection(node)) {{ done(btn); return; }}
  try {{
    const item = new ClipboardItem({{
      "text/html": new Blob([node.innerHTML], {{ type: "text/html" }}),
      "text/plain": new Blob([node.innerText], {{ type: "text/plain" }}),
    }});
    await navigator.clipboard.write([item]); done(btn);
  }} catch (e) {{ btn.textContent = "본문을 드래그해서 복사하세요"; }}
}});
</script>
"""


def write_paste(draft_dir: Path, post: dict[str, Any], visit, place_info) -> Path:
    path = draft_dir / "paste.html"
    path.write_text(paste_html(post, visit, place_info, draft_dir / "photos"), encoding="utf-8")
    return path
