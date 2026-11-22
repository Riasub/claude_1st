"""방문 기록(visit.yaml) 읽기와 정리."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml

TEMPLATE = Path(__file__).parent / "templates" / "visit.yaml"
VISIT_FILE = "visit.yaml"
PHOTO_DIR = "photos"
DRAFT_DIR = "draft"


class VisitError(Exception):
    """방문 기록에 문제가 있을 때."""


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def prune(value: Any) -> Any:
    """비어 있는 항목을 재귀적으로 지운다. 템플릿에서 안 채운 칸이 글에 섞이지 않게."""
    if isinstance(value, dict):
        out = {k: prune(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if not _is_empty(v)}
    if isinstance(value, list):
        out = [prune(v) for v in value]
        return [v for v in out if not _is_empty(v)]
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w가-힣-]+", "-", name.strip()).strip("-")
    return slug or "visit"


def create_visit(root: Path, name: str, date: dt.date | None = None) -> Path:
    date = date or dt.date.today()
    folder = root / f"{date.isoformat()}-{slugify(name)}"
    if folder.exists():
        raise VisitError(f"이미 있는 폴더예요: {folder}")
    (folder / PHOTO_DIR).mkdir(parents=True)
    safe_name = name.replace("\\", "\\\\").replace('"', '\\"')
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("{name}", safe_name).replace("{date}", date.isoformat())
    (folder / VISIT_FILE).write_text(text, encoding="utf-8")
    return folder


def load_visit(folder: Path) -> dict[str, Any]:
    path = folder / VISIT_FILE
    if not path.is_file():
        raise VisitError(f"{path} 파일이 없어요. 먼저 `python -m blogdraft new \"가게 이름\"`을 실행하세요.")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise VisitError(f"{path} 형식이 잘못됐어요: {e}") from e
    if not isinstance(raw, dict):
        raise VisitError(f"{path} 형식이 잘못됐어요.")

    photos_meta = raw.get("photos") or {}
    if not isinstance(photos_meta, dict):
        raise VisitError("photos: 항목은 '파일명: 설명' 형식이어야 해요.")

    visit = prune(raw)
    visit["photos"] = {str(k): str(v).strip() for k, v in photos_meta.items() if v is not None}
    visit["sponsored"] = bool(raw.get("sponsored"))

    name = (visit.get("place") or {}).get("name", "")
    if not name:
        raise VisitError("place.name(가게 이름)을 적어 주세요.")
    return visit
