from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserPublic
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import ConsentLog, User
from app.db.session import get_db

router = APIRouter(tags=["authentication"])


def _token_response(user: User) -> TokenResponse:
    try:
        token = create_access_token(user.id, user.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not body.consent_accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required to register.")
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    is_first_account = db.scalar(select(func.count()).select_from(User)) == 0
    admin_email = (get_settings().admin_email or "").strip().lower()
    role = "agronomist" if is_first_account and admin_email and body.email == admin_email else "farmer"
    user = User(
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=role,
    )
    db.add(user)
    try:
        db.flush()
        db.add(ConsentLog(user_id=user.id, text_version=body.consent_text_version))
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from exc
    return _token_response(user)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user)


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_my_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    db.delete(user)
    db.commit()
