"""명령어: new / build / render"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import naver, notion, photos as photo_mod, render, writer
from .visit import DRAFT_DIR, PHOTO_DIR, VisitError, create_visit, load_visit

REPO_ROOT = Path(__file__).resolve().parent.parent
PLACE_CACHE = "place.json"


def load_dotenv(path: Path) -> None:
    """.env 파일의 값을 환경 변수로 (이미 설정된 값은 덮어쓰지 않음)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def lookup_place(folder: Path, visit: dict, refresh: bool) -> dict | None:
    place = visit["place"]
    cache = folder / DRAFT_DIR / PLACE_CACHE
    if place.get("naver_search") is False:
        return None
    if cache.is_file() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8")) or None
    if naver.credentials() is None:
        print("· 네이버 API 키가 없어 가게 정보 검색을 건너뜁니다.")
        return None
    query = place.get("search_query") or " ".join(x for x in (place.get("area", ""), place["name"]) if x)
    try:
        results = naver.search_place(query)
    except naver.NaverError as e:
        print(f"· {e} - 가게 정보 없이 계속합니다.")
        return None
    match = naver.best_match(place["name"], results)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(match or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    if match:
        print(f"· 네이버에서 찾은 가게: {match['name']} / {match['road_address'] or match['address']}")
        print("  (다른 가게라면 visit.yaml의 search_query를 고치고 --refresh-place로 다시 실행하세요)")
    else:
        names = ", ".join(r["name"] for r in results) or "결과 없음"
        print(f"· 이름이 맞는 가게를 못 찾았어요 ({names}). search_query를 적어 보세요.")
    return match


def cmd_new(args) -> int:
    date = dt.date.fromisoformat(args.date) if args.date else None
    folder = create_visit(Path(args.root), args.name, date)
    print(f"만들었어요: {folder}")
    print(f"1) {folder / PHOTO_DIR} 에 사진을 넣고")
    print(f"2) {folder / 'visit.yaml'} 에 방문 기록을 적은 뒤")
    print(f"3) python -m blogdraft build \"{folder}\" 를 실행하세요.")
    return 0


def cmd_build(args) -> int:
    folder = Path(args.folder)
    visit = load_visit(folder)
    draft = folder / DRAFT_DIR
    draft.mkdir(exist_ok=True)

    place_info = lookup_place(folder, visit, args.refresh_place)
    skipped: list[str] = []
    photos = photo_mod.prepare_photos(folder / PHOTO_DIR, draft / "photos", visit["photos"], skipped)
    print(f"· 사진 {len(photos)}장 정리 완료 (위치정보 제거, 크기 조정)")
    for reason in skipped:
        print(f"· 건너뛴 사진: {reason}")

    system = writer.system_prompt(writer.load_style(REPO_ROOT))
    use_ai = not args.no_ai
    if use_ai and not os.environ.get("ANTHROPIC_API_KEY"):
        print("· ANTHROPIC_API_KEY가 없어 --no-ai 모드로 진행합니다.")
        use_ai = False

    if not use_ai:
        prompt = draft / "prompt.md"
        prompt.write_text(
            writer.prompt_markdown(system, visit, place_info, photos, draft / "post.json"), encoding="utf-8"
        )
        print(f"작성 요청서를 만들었어요: {prompt}")
        print("Claude Code 세션에서 \"이 방문 초안 써줘\"라고 하면 이 파일대로 초안을 씁니다.")
        return 0

    print("· Claude가 초안을 쓰는 중... (1~2분 걸릴 수 있어요)")
    content = writer.user_content(visit, place_info, photos, with_images=not args.no_images)
    post = writer.normalize_post(writer.write_with_claude(system, content), len(photos))
    return _finish(folder, post, visit, place_info)


def cmd_import_notion(args) -> int:
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    folder = notion.import_visit(spec, Path(args.root))
    print(folder)
    return 0


def cmd_render(args) -> int:
    folder = Path(args.folder)
    visit = load_visit(folder)
    draft = folder / DRAFT_DIR
    post_path = draft / "post.json"
    if not post_path.is_file():
        print(f"{post_path} 이(가) 없어요. 먼저 build를 실행하세요.", file=sys.stderr)
        return 1
    cache = draft / PLACE_CACHE
    place_info = (json.loads(cache.read_text(encoding="utf-8")) or None) if cache.is_file() else None
    photo_count = len(list((draft / "photos").glob("*.jpg")))
    post = writer.normalize_post(json.loads(post_path.read_text(encoding="utf-8")), photo_count)
    return _finish(folder, post, visit, place_info)


def _finish(folder: Path, post: dict, visit: dict, place_info) -> int:
    draft = folder / DRAFT_DIR
    render.write_outputs(draft, post, visit, place_info)
    if (folder / notion.NOTION_FILE).is_file():
        refs = notion.photo_refs_for(folder, draft / "photos")
        md = notion.notion_markdown(post, visit, place_info, refs, dt.date.today().isoformat())
        (draft / "notion.md").write_text(md, encoding="utf-8")
        print(f"노션용 초안: {draft / 'notion.md'}")
    print(f"초안 완성: {draft / 'preview.html'}")
    print("  브라우저로 열어 확인하고, 제목/본문/태그 복사 버튼으로 블로그에 붙여 넣으세요.")
    if post["check"]:
        print("  발행 전에 확인할 점:")
        for c in post["check"]:
            print(f"   - {c}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(prog="blogdraft", description="카페·음식점 후기 초안 만들기")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="새 방문 폴더 만들기")
    p.add_argument("name", help="가게 이름")
    p.add_argument("--date", help="방문일 (YYYY-MM-DD, 기본: 오늘)")
    p.add_argument("--root", default=str(REPO_ROOT / "visits"), help="방문 폴더를 만들 위치")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("build", help="사진 정리 + 가게 정보 검색 + 초안 쓰기")
    p.add_argument("folder", help="방문 폴더")
    p.add_argument("--no-ai", action="store_true", help="Claude API를 부르지 않고 작성 요청서(prompt.md)만 만들기")
    p.add_argument("--no-images", action="store_true", help="사진을 Claude에게 보내지 않기 (비용 절약)")
    p.add_argument("--refresh-place", action="store_true", help="네이버 가게 정보 다시 검색")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("import-notion", help="노션 페이지 정보(JSON)로 방문 폴더 만들기")
    p.add_argument("spec", help="노션 페이지 정보 JSON 파일 (형식은 blogdraft/notion.py 참고)")
    p.add_argument("--root", default=str(REPO_ROOT / "visits"), help="방문 폴더를 만들 위치")
    p.set_defaults(func=cmd_import_notion)

    p = sub.add_parser("render", help="post.json을 고친 뒤 미리보기 다시 만들기")
    p.add_argument("folder", help="방문 폴더")
    p.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (VisitError, writer.WriterError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
