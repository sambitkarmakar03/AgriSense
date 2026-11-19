from pathlib import Path
import re
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.schemas import KBRead, KBUpdateRequest, KBVersionRead
from app.db.models import KBVersion, User
from app.db.session import get_db
from app.expert.engine import parse_knowledge_base

router = APIRouter(prefix="/kb", tags=["knowledge base"])
KB_DIRECTORY = Path(__file__).resolve().parents[1] / "expert"
REQUIRED_IRRIGATION_RULES = {"IR-1", "IR-2", "IR-3", "IR-4", "IR-5", "IR-6"}


def _require_irrigation_kind(kind: str) -> None:
    if kind != "irrigation":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge-base kind not found.")


def _db_versions(db: Session) -> list[KBVersion]:
    return list(
        db.scalars(select(KBVersion).where(KBVersion.kind == "irrigation").order_by(KBVersion.id)).all()
    )


def get_effective_knowledge_base(db: Session) -> tuple[str, str, KBVersion | None]:
    latest = db.scalar(
        select(KBVersion).where(KBVersion.kind == "irrigation").order_by(KBVersion.id.desc()).limit(1)
    )
    if latest is not None:
        parse_knowledge_base(latest.yaml_text)
        return latest.version, latest.yaml_text, latest
    path = KB_DIRECTORY / "irrigation_kb_v2.yaml"
    text = path.read_text(encoding="utf-8")
    return "v2", text, None


def _version_number(version: str) -> int:
    match = re.fullmatch(r"v(\d+)", version)
    return int(match.group(1)) if match else 0


def _validate_editable_irrigation_yaml(yaml_text: str) -> dict[str, Any]:
    try:
        data = parse_knowledge_base(yaml_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    by_id = {str(rule["id"]): rule for rule in data["rules"]}
    missing = REQUIRED_IRRIGATION_RULES - set(by_id)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Irrigation knowledge base is missing required rules: {', '.join(sorted(missing))}.",
        )
    if by_id["IR-2"]["priority"] != 1:
        raise HTTPException(
            status_code=422,
            detail="IR-2 must retain priority 1 so heavy forecast rain takes precedence.",
        )
    return data


@router.get("/{kind}", response_model=KBRead)
def get_knowledge_base(
    kind: str,
    version: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> KBRead:
    _require_irrigation_kind(kind)
    if version is None:
        selected_version, yaml_text, record = get_effective_knowledge_base(db)
    else:
        record = db.scalar(
            select(KBVersion).where(KBVersion.kind == kind, KBVersion.version == version).limit(1)
        )
        if record is not None:
            selected_version, yaml_text = record.version, record.yaml_text
        elif version in {"v1", "v2"}:
            selected_version = version
            yaml_text = (KB_DIRECTORY / f"irrigation_kb_{version}.yaml").read_text(encoding="utf-8")
            record = None
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge-base version not found.")
    return KBRead(
        kind=kind,
        version=selected_version,
        yaml_text=yaml_text,
        author_id=record.author_id if record else None,
        ts=record.ts if record else None,
    )


@router.put("/{kind}", response_model=KBRead)
def update_knowledge_base(
    kind: str,
    body: KBUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("agronomist")),
) -> KBRead:
    _require_irrigation_kind(kind)
    current_version, _current_yaml, _record = get_effective_knowledge_base(db)
    if body.expected_version is not None and body.expected_version != current_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Knowledge base is now {current_version}.")
    data = _validate_editable_irrigation_yaml(body.yaml_text)
    all_versions = ["v1", "v2", *(row.version for row in _db_versions(db))]
    next_version = f"v{max(map(_version_number, all_versions), default=2) + 1}"
    data["version"] = next_version
    stored_yaml = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    record = KBVersion(kind=kind, version=next_version, yaml_text=stored_yaml, author_id=user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return KBRead(kind=kind, version=record.version, yaml_text=record.yaml_text, author_id=record.author_id, ts=record.ts)


@router.get("/{kind}/versions", response_model=list[KBVersionRead])
def list_knowledge_base_versions(
    kind: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[KBVersionRead]:
    _require_irrigation_kind(kind)
    packaged = [
        KBVersionRead(kind=kind, version=version, author_id=None, ts=None, source="packaged")
        for version in ("v1", "v2")
    ]
    database = [
        KBVersionRead(kind=row.kind, version=row.version, author_id=row.author_id, ts=row.ts, source="database")
        for row in _db_versions(db)
    ]
    return sorted(packaged + database, key=lambda row: _version_number(row.version))
