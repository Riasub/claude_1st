import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from blogdraft import cli, naver, photos, render, writer
from blogdraft.visit import create_visit, load_visit, prune


def make_photo(path: Path, size=(3000, 2000), taken="2026:11:22 13:00:00", gps=True, orientation=None):
    im = Image.new("RGB", size, (200, 150, 100))
    exif = Image.Exif()
    exif.get_ifd(photos.EXIF_IFD)[photos.EXIF_DATETIME_ORIGINAL] = taken
    if gps:
        exif.get_ifd(0x8825)[2] = (37.0, 33.0, 0.0)  # GPSLatitude
    if orientation:
        exif[0x0112] = orientation
    im.save(path, "JPEG", exif=exif)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """테스트에서는 네이버에 접속하지 않는다."""
    from blogdraft import placeinfo

    def blocked(*args, **kwargs):
        raise placeinfo.PlaceError("테스트에서는 네트워크를 쓰지 않아요.")

    monkeypatch.setattr(placeinfo, "_get", blocked)


@pytest.fixture
def visit_dir(tmp_path):
    folder = create_visit(tmp_path, '카페 "온새"')
    yaml_path = folder / "visit.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace('area: ""', 'area: "성수동"')
    text = text.replace('  - name: ""\n    price:              # 숫자만 (예: 6500)\n    comment: ""',
                        '  - name: 아인슈페너\n    price: 6500\n    comment: "크림이 진함"')
    yaml_path.write_text(text, encoding="utf-8")
    make_photo(folder / "photos" / "b.jpg", taken="2026:11:22 13:05:00")
    make_photo(folder / "photos" / "a.jpg", taken="2026:11:22 13:10:00")
    make_photo(folder / "photos" / "c.jpg", taken="2026:11:22 13:01:00", orientation=6)
    return folder


def test_new_visit_template_loads_and_prunes(visit_dir):
    visit = load_visit(visit_dir)
    assert visit["place"]["name"] == '카페 "온새"'
    assert visit["menus"] == [{"name": "아인슈페너", "price": 6500, "comment": "크림이 진함"}]
    assert "good" not in visit and "ratings" not in visit  # 빈 칸은 빠짐
    assert visit["sponsored"] is False


def test_prune_keeps_false_and_zero():
    assert prune({"a": "", "b": [], "c": False, "d": 0, "e": [{"x": ""}]}) == {"c": False, "d": 0}


def test_photos_are_ordered_resized_and_stripped(visit_dir, tmp_path):
    out = tmp_path / "out"
    result = photos.prepare_photos(visit_dir / "photos", out, {"a.jpg": "외관"})
    assert [p.source.name for p in result] == ["a.jpg", "c.jpg", "b.jpg"]  # 설명 순서 -> 촬영 시간 순
    assert result[0].caption == "외관"
    with Image.open(out / "01.jpg") as im:
        assert max(im.size) == photos.BLOG_MAX_EDGE
        assert len(im.getexif()) == 0  # GPS 포함 메타데이터 없음
    with Image.open(out / "02.jpg") as im:  # orientation=6 -> 세로로 회전
        assert im.size[1] > im.size[0]


def test_normalize_post_fixes_photos_and_tags():
    post = {
        "title": " 제목 ",
        "alt_titles": ["a", " "],
        "blocks": [
            {"kind": "text", "text": "본문", "photo": 0},
            {"kind": "photo", "text": "", "photo": 2},
            {"kind": "photo", "text": "", "photo": 2},
            {"kind": "photo", "text": "", "photo": 9},
            {"kind": "text", "text": "  ", "photo": 0},
        ],
        "tags": ["#성수 카페", "성수카페", "디저트"],
        "check": [],
    }
    out = writer.normalize_post(post, 3)
    assert out["title"] == "제목"
    assert [b["photo"] for b in out["blocks"] if b["kind"] == "photo"] == [2, 1, 3]
    assert out["tags"] == ["성수카페", "디저트"]
    assert out["alt_titles"] == ["a"]


def test_render_escapes_and_adds_disclosure(visit_dir):
    visit = load_visit(visit_dir)
    visit["sponsored"] = True
    post = writer.normalize_post(
        {"title": "<b>t</b>", "alt_titles": [], "blocks": [{"kind": "text", "text": "</script>x", "photo": 0}],
         "tags": ["태그"], "check": ["메뉴 이름 확인"]}, 1)
    place = {"road_address": "서울 성동구 어딘가 1", "telephone": "02-000-0000"}
    page = render.preview_html(post, visit, place)
    assert "<b>t</b>" not in page and "&lt;b&gt;" in page
    assert "</script>x" not in page
    assert "제공받아 작성한 후기입니다" in page
    txt = render.post_text(post, visit, place)
    assert txt.index("제공받아") < txt.index("[사진 1]")
    assert "주소 : 서울 성동구 어딘가 1" in txt and "메뉴 : 아인슈페너 6,500원" in txt


def test_naver_search_and_match(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    seen = {}

    def fake_urlopen(req, timeout):
        seen["headers"] = dict(req.header_items())
        seen["url"] = req.full_url
        body = {"items": [
            {"title": "다른<b>가게</b>", "category": "카페", "address": "x", "roadAddress": "", "telephone": "", "link": ""},
            {"title": "카페 <b>온새</b> &amp; 베이크", "category": "카페,디저트", "address": "서울 성수동",
             "roadAddress": "서울 성동구 1", "telephone": "", "link": ""},
        ]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(naver.urllib.request, "urlopen", fake_urlopen)
    results = naver.search_place("성수동 온새")
    assert seen["headers"]["X-naver-client-secret"] == "secret"
    assert "query=%EC%84%B1" in seen["url"]
    match = naver.best_match("온새", results)
    assert match["name"] == "카페 온새 & 베이크"
    assert naver.best_match("없는집", results) is None


def test_write_with_claude_parses_and_handles_refusal(monkeypatch):
    import anthropic

    calls = {}

    def make(stop_reason, text):
        def create(**kwargs):
            calls.update(kwargs)
            return SimpleNamespace(stop_reason=stop_reason, _request_id="req_1",
                                   content=[SimpleNamespace(type="text", text=text)])
        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))

    monkeypatch.setattr(anthropic, "Anthropic", lambda: make("end_turn", '{"title": "x"}'))
    assert writer.write_with_claude("sys", [{"type": "text", "text": "hi"}]) == {"title": "x"}
    assert calls["model"] == writer.DEFAULT_MODEL
    assert calls["output_config"]["format"]["schema"] is writer.POST_SCHEMA
    assert calls["fallbacks"] == "default"

    monkeypatch.setattr(anthropic, "Anthropic", lambda: make("refusal", ""))
    with pytest.raises(writer.WriterError):
        writer.write_with_claude("sys", [])


def test_cli_build_no_ai_then_render(visit_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    assert cli.main(["build", str(visit_dir)]) == 0
    draft = visit_dir / "draft"
    prompt = (draft / "prompt.md").read_text(encoding="utf-8")
    assert "아인슈페너" in prompt and "[사진 3]" in prompt
    assert sorted(p.name for p in (draft / "photos").glob("*.jpg")) == ["01.jpg", "02.jpg", "03.jpg"]

    (draft / "post.json").write_text(json.dumps({
        "title": "성수동 카페 온새", "alt_titles": [], "tags": ["성수동카페"], "check": [],
        "blocks": [{"kind": "heading", "text": "분위기", "photo": 0}, {"kind": "photo", "text": "외관", "photo": 1}],
    }, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["render", str(visit_dir)]) == 0
    txt = (draft / "post.txt").read_text(encoding="utf-8")
    assert "[사진 1]\n외관" in txt and "[사진 3]" in txt
    assert (draft / "tags.txt").read_text(encoding="utf-8") == "#성수동카페\n"
    assert 'src="photos/01.jpg"' in (draft / "preview.html").read_text(encoding="utf-8")


def test_parse_menus():
    from blogdraft.notion import parse_menus

    assert parse_menus("아인슈페너 6500 / 크로플 7,000원\n물") == [
        {"name": "아인슈페너", "price": 6500},
        {"name": "크로플", "price": 7000},
        {"name": "물"},
    ]
    assert parse_menus("") == []


def test_import_notion_build_render_writes_notion_markdown(tmp_path, monkeypatch):
    from blogdraft import notion

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    src = tmp_path / "dl"
    src.mkdir()
    make_photo(src / "IMG 1.jpg", taken="2026:11:22 15:00:00")
    make_photo(src / "IMG 2.jpg", taken="2026:11:22 14:00:00")  # 더 이른 시간이지만 노션 순서가 우선
    (src / "broken.jpg").write_bytes(b"not an image")
    spec = {
        "page_url": "https://www.notion.so/abc123def4567890abcdef1234567890",
        "name": "온새", "date": "2026-11-22", "type": "카페", "area": "성수동",
        "menus": "아인슈페너 6500", "review": "크림이 진했어요 <b>굿</b>", "sponsored": True,
        "naver_search": False,
        "photos": [
            {"path": str(src / "IMG 1.jpg"), "ref": "notion-file-block://a?name=1.jpg"},
            {"path": str(src / "broken.jpg"), "ref": "notion-file-block://b"},
            {"path": str(src / "IMG 2.jpg"), "ref": "notion-file-block://c?name=2.jpg"},
        ],
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    root = tmp_path / "visits"
    assert cli.main(["import", str(spec_path), "--root", str(root)]) == 0
    folder = next(root.iterdir())
    assert folder.name.endswith("34567890")
    visit = load_visit(folder)
    assert visit["menus"] == [{"name": "아인슈페너", "price": 6500}]
    assert visit["place"]["naver_search"] is False

    assert cli.main(["build", str(folder)]) == 0  # 깨진 사진은 건너뜀
    draft = folder / "draft"
    (draft / "post.json").write_text(json.dumps({
        "title": "성수동 카페 온새", "alt_titles": ["다른 제목"], "tags": ["성수동카페"], "check": ["메뉴 확인"],
        "blocks": [{"kind": "text", "text": "- 목록처럼 보이는 문장 <script>", "photo": 0},
                   {"kind": "photo", "text": "외관", "photo": 2}],
    }, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["render", str(folder)]) == 0
    md = (draft / "notion.md").read_text(encoding="utf-8")
    assert notion.DRAFT_HEADING in md
    assert '<image source="notion-file-block://c?name=2.jpg">사진 2 · 외관</image>' in md
    assert '<image source="notion-file-block://a?name=1.jpg">사진 1</image>' in md
    assert "notion-file-block://b" not in md
    assert "\\- 목록처럼 보이는 문장 &lt;script&gt;" in md
    assert "제공받아 작성한 후기입니다" in md and "| 메뉴 | 아인슈페너 6,500원 |" in md
    assert "```text\n#성수동카페\n```" in md


def test_place_marker_and_region_after_store_info(visit_dir):
    visit = load_visit(visit_dir)
    post = writer.normalize_post({"title": "[성수동] 카페 \"온새\" 후기", "alt_titles": [], "tags": [], "check": [],
                                  "blocks": [{"kind": "text", "text": "본문", "photo": 0}]}, 0)
    txt = render.post_text(post, visit, None)
    assert "지역 : 성수동" in txt
    assert txt.rstrip().endswith('[📍 장소: 카페 "온새"]')
    assert txt.index("📍 가게 정보") < txt.index("[📍 장소:")
    assert "장소&#x27; 버튼" in render.preview_html(post, visit, None)
    # 주소가 있으면 지역 줄은 빠짐
    assert "지역 :" not in render.post_text(post, visit, {"road_address": "서울 성동구 1"})


def test_paste_page_embeds_photos_in_order(visit_dir, tmp_path):
    from blogdraft import paste

    visit = load_visit(visit_dir)
    draft = tmp_path / "draft"
    photos.prepare_photos(visit_dir / "photos", draft / "photos", {})
    post = writer.normalize_post({"title": "[성수동] 온새 후기", "alt_titles": [], "tags": ["성수카페"], "check": ["확인 <1>"],
                                  "blocks": [{"kind": "heading", "text": "분위기", "photo": 0},
                                             {"kind": "photo", "text": "외관", "photo": 2}]}, 3)
    page = paste.write_paste(draft, post, visit, None).read_text(encoding="utf-8")
    assert page.startswith("<title>")
    assert "<html" not in page and "<body" not in page
    assert page.count('src="data:image/jpeg;base64,') == 3
    body = page[page.index('<div id="article">'):]
    assert body.index("<b>분위기</b>") < body.index('alt="사진 2"') < body.index('alt="사진 1"')
    assert "[📍 장소: " in body and "확인 &lt;1&gt;" in page


PLACE_PAGE = """<script>window.__APOLLO_STATE__ = {
"PlaceDetailBase:1": {"__typename": "PlaceDetailBase", "name": "타코의밤", "category": "요리주점",
  "roadAddress": "충남 아산시 탕정면 매곡한들5길 6-4 103호", "address": "충남 아산시 탕정면 매곡리 1415", "phone": "041-424-4565"},
"PlaceMenuItem:a": {"__typename": "PlaceMenuItem", "name": "가쓰오 수제 타코야끼", "price": {"displayText": "7,000~24,000원"}, "description": "큼지막한 문어"},
"PlaceMenuItem:b": {"__typename": "PlaceMenuItem", "name": "[매콤짭짤] 문어 뽈뽀", "price": {"displayText": "15,900원"}, "description": null},
"c1": {"__typename": "PlaceMenuCategory", "kind": "recommend", "itemIds": ["b"]},
"c2": {"__typename": "PlaceMenuCategory", "kind": "normal", "itemIds": ["a", "b"]}
};
</script>"""


def test_place_parse_and_lookup(monkeypatch):
    from blogdraft import placeinfo

    search = '..."id":"1390149","name":"순환5"...,"id":"2031983709","name":"타코의밤",...'
    assert placeinfo.find_place_id("타코의 밤", "탕정", html_text=search) == "2031983709"
    assert placeinfo.find_place_id("없는집", html_text=search) is None

    info = placeinfo.parse_place(PLACE_PAGE, "2031983709")
    assert info["telephone"] == "041-424-4565" and info["category"] == "요리주점"
    assert [m["name"] for m in info["menus"]] == ["가쓰오 수제 타코야끼", "[매콤짭짤] 문어 뽈뽀"]
    assert info["menus"][1]["price"] == "15,900원"
    assert info["link"] == "https://map.naver.com/p/entry/place/2031983709"

    pages = {"search": search, "place": PLACE_PAGE}
    monkeypatch.setattr(placeinfo, "_get", lambda url, **kw: pages["place" if "m.place" in url else "search"])
    assert placeinfo.lookup("타코의밤", "탕정")["name"] == "타코의밤"
    with pytest.raises(placeinfo.PlaceError):
        placeinfo.parse_place("<html>no data</html>", "1")


def test_official_menu_reaches_prompt_and_store_info(visit_dir):
    from blogdraft import placeinfo

    visit = load_visit(visit_dir)
    info = placeinfo.parse_place(PLACE_PAGE, "2031983709")
    facts = writer.facts_text(visit, info)
    assert "[매콤짭짤] 문어 뽈뽀" in facts and "15,900원" in facts
    rows = dict(render.info_lines(visit, info))
    assert rows["전화"] == "041-424-4565"
    assert rows["네이버 지도"].endswith("/2031983709")


def test_import_uses_photo_date_when_date_missing(tmp_path):
    from blogdraft import notion

    make_photo(tmp_path / "p.jpg", taken="2026:10:01 19:07:30")
    folder = notion.import_visit({"name": "오미영피자", "naver_search": False,
                                  "photos": [{"path": str(tmp_path / "p.jpg")}]}, tmp_path / "visits")
    assert folder.name.startswith("2026-10-01-")
    assert load_visit(folder)["visit"]["date"] == "2026-10-01"


def test_naver_get_retries_after_reset(monkeypatch):
    import urllib.request
    from blogdraft import placeinfo

    monkeypatch.undo()  # no_network 픽스처 해제: 여기서는 urlopen만 가짜로 바꾼다
    monkeypatch.setattr(placeinfo.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def flaky(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError(ConnectionResetError(104, "reset"))
        return Resp("ok".encode())

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    assert placeinfo._get("https://m.search.naver.com/x") == "ok" and calls["n"] == 3


def test_import_passes_waiting_to_store_info(tmp_path):
    from blogdraft import notion

    folder = notion.import_visit({"name": "오미영피자", "date": "2026-10-01", "naver_search": False,
                                  "waiting": "캐치테이블 웨이팅 가능"}, tmp_path)
    visit = load_visit(folder)
    assert dict(render.info_lines(visit, None))["웨이팅"] == "캐치테이블 웨이팅 가능"


def test_place_public_info_reaches_prompt_and_store_info(visit_dir):
    from blogdraft import placeinfo

    page = PLACE_PAGE.replace('"phone": "041-424-4565"}',
        '"phone": "041-424-4565", "conveniences": ["예약", "주차"], "microReviews": ["한줄 소개"]},\n'
        '"VisitorReviewStatsResult:1": {"__typename": "VisitorReviewStatsResult", "review": {"totalCount": 330},'
        ' "analysis": {"themes": [{"label": "맛", "count": 128}]}},\n'
        '"FsasReview:x": {"__typename": "FsasReview", "title": "다른 블로그 제목"}')
    info = placeinfo.parse_place(page, "1")
    assert info["conveniences"] == ["예약", "주차"] and info["review_total"] == 330
    assert info["review_themes"] == [{"label": "맛", "count": 128}] and info["blog_titles"] == ["다른 블로그 제목"]
    facts = writer.facts_text(load_visit(visit_dir), info)
    assert "네이버 공개 정보" in facts and "참고만" in facts
    assert dict(render.info_lines(load_visit(visit_dir), info))["편의시설"] == "예약, 주차"


def test_keywords_research_and_prompt_sections(monkeypatch, tmp_path, visit_dir):
    from blogdraft import keywords, placeinfo

    pages = {
        "ac": json.dumps({"items": [[["탕정 타코야끼"], ["탕정 타코야끼 맛집"]]]}),
        "search": '<a href="https://m.blog.naver.com/x/1" class="t">[탕정] 타코의밤 타코야끼 후기</a>'
                  '<a href="https://m.blog.naver.com/y">블로그이름</a>',
    }
    monkeypatch.setattr(placeinfo, "_get", lambda url, **kw: pages["ac" if "ac.search" in url else "search"])
    monkeypatch.setattr(keywords, "_get", lambda url, **kw: pages["ac" if "ac.search" in url else "search"])
    r = keywords.research("탕정", "타코의밤", ["타코야끼"])
    assert r["suggestions"]["탕정 타코야끼"] == ["탕정 타코야끼", "탕정 타코야끼 맛집"]
    assert r["blog_titles"] == ["[탕정] 타코의밤 타코야끼 후기"]

    other = tmp_path / "visits" / "2026-01-01-다른집" / "draft"
    other.mkdir(parents=True)
    (other / "post.json").write_text(json.dumps({"title": "[A] 다른집 후기", "blocks": [
        {"kind": "text", "text": "첫 문장이에요"}, {"kind": "heading", "text": "📌 한눈에 보기"},
        {"kind": "text", "text": "끝 문장이에요"}]}, ensure_ascii=False), encoding="utf-8")
    recent = writer.recent_posts(tmp_path / "visits", tmp_path / "visits" / "현재")
    assert recent == [{"title": "[A] 다른집 후기", "first": "첫 문장이에요", "last": "끝 문장이에요",
                       "headings": ["📌 한눈에 보기"]}]
    md = writer.prompt_markdown("규칙", load_visit(visit_dir), None, [], tmp_path / "post.json", keywords=r, recent=recent)
    assert "탕정 타코야끼 맛집" in md and "이미 쓴 표현" in md and "📌 한눈에 보기" in md
