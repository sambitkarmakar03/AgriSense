from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_field
from app.api.schemas import FieldCreate, FieldRead, FieldUpdate
from app.db.models import Field, User
from app.db.session import get_db

router = APIRouter(prefix="/fields", tags=["fields"])


@router.get("", response_model=list[FieldRead])
def list_fields(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Field]:
    return list(db.scalars(select(Field).where(Field.user_id == user.id).order_by(Field.id)).all())


@router.post("", response_model=FieldRead, status_code=status.HTTP_201_CREATED)
def create_field(body: FieldCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Field:
    field = Field(user_id=user.id, **body.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.get("/{field_id}", response_model=FieldRead)
def get_field(field_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Field:
    return get_owned_field(field_id, db, user)


@router.put("/{field_id}", response_model=FieldRead)
def update_field(
    field_id: int,
    body: FieldUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Field:
    field = get_owned_field(field_id, db, user)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    for name, value in updates.items():
        setattr(field, name, value)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_field(
    field_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    field = get_owned_field(field_id, db, user)
    db.delete(field)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
