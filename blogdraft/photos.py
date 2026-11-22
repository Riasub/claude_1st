"""사진 정리: 회전 보정, 크기 조정, 위치정보 등 메타데이터 제거, 순서 정하기."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

try:  # 아이폰 HEIC 사진 지원 (설치되어 있을 때만)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
BLOG_MAX_EDGE = 1600   # 블로그 업로드용
AI_MAX_EDGE = 1024     # Claude에게 보여줄 때 (비용 절약)
EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_IFD = 0x8769


@dataclass
class Photo:
    index: int          # 1부터 시작하는 글 속 사진 번호
    source: Path
    output: Path
    caption: str        # visit.yaml에 적은 설명 (없으면 "")


def _taken_at(path: Path) -> str:
    """촬영 시각(EXIF). 없으면 빈 문자열 -> 파일명 순."""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            value = exif.get_ifd(EXIF_IFD).get(EXIF_DATETIME_ORIGINAL) or exif.get(0x0132)
            return str(value or "")
    except Exception:
        return ""


def find_photos(photo_dir: Path, captions: dict[str, str]) -> list[Path]:
    if not photo_dir.is_dir():
        return []
    files = [p for p in photo_dir.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_EXTS]
    by_name = {p.name: p for p in files}
    ordered = [by_name[name] for name in captions if name in by_name]
    rest = sorted((p for p in files if p not in ordered), key=lambda p: (_taken_at(p) or "~", p.name))
    return ordered + rest


def _open_upright(path: Path) -> Image.Image:
    try:
        im = Image.open(path)
    except Exception as e:  # HEIC 등 지원 안 되는 형식
        raise ValueError(
            f"{path.name}을(를) 열 수 없어요. JPG로 바꿔서 다시 넣어 주세요. ({e})"
        ) from e
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    return im


def _resized(im: Image.Image, max_edge: int) -> Image.Image:
    im = im.copy()
    im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return im


def prepare_photos(
    photo_dir: Path, out_dir: Path, captions: dict[str, str], skipped: list[str] | None = None
) -> list[Photo]:
    """블로그용 사진을 01.jpg, 02.jpg ... 로 저장한다.

    새로 저장할 때 EXIF를 넣지 않으므로 GPS 위치, 기기 정보가 모두 빠진다.
    skipped 리스트를 넘기면 열 수 없는 사진은 건너뛰고 그 이유를 거기에 담는다 (없으면 오류).
    순서와 원본 파일명은 out_dir/photos.json 에도 기록한다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    photos: list[Photo] = []
    for src in find_photos(photo_dir, captions):
        try:
            im = _open_upright(src)
        except ValueError as e:
            if skipped is None:
                raise
            skipped.append(str(e))
            continue
        index = len(photos) + 1
        out = out_dir / f"{index:02d}.jpg"
        _resized(im, BLOG_MAX_EDGE).save(out, "JPEG", quality=90, optimize=True)
        photos.append(Photo(index=index, source=src, output=out, caption=captions.get(src.name, "")))
    manifest = [{"index": p.index, "source": p.source.name, "caption": p.caption} for p in photos]
    (out_dir / "photos.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return photos


def image_block(path: Path) -> dict:
    """Claude API에 넣을 이미지 블록 (작게 줄인 JPEG)."""
    with Image.open(path) as im:
        small = _resized(im.convert("RGB"), AI_MAX_EDGE)
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=80)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(buf.getvalue()).decode("ascii"),
        },
    }
