from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import hash_password, verify_password, create_token, require_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    notify_new_results: bool


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email już zarejestrowany")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Nazwa użytkownika zajęta")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Hasło min. 6 znaków")

    user = User(
        email=req.email,
        username=req.username,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(token=create_token(user.id), username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Nieprawidłowy email lub hasło")
    return TokenResponse(token=create_token(user.id), username=user.username)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(require_user)):
    return UserResponse(
        id=user.id, email=user.email, username=user.username,
        notify_new_results=user.notify_new_results,
    )


@router.put("/notifications")
def update_notifications(enabled: bool, user: User = Depends(require_user), db: Session = Depends(get_db)):
    user.notify_new_results = enabled
    db.commit()
    return {"ok": True}
