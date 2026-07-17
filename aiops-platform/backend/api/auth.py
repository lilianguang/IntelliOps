"""用户认证 API - 登录/登出"""

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt
from core.db import async_session_factory
from models.user import User
from config.settings import settings
from sqlalchemy import select

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """用户登录"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == req.username, User.enabled == 1)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 验证密码（使用bcrypt）
    try:
        if not _bcrypt.checkpw(
            req.password.encode(),
            user.password_hash.encode()
        ):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
    except Exception:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 生成JWT
    expiry = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    role_val = user.role.value if hasattr(user.role, 'value') else user.role
    token_data = {
        "sub": user.username,
        "role": role_val,
        "exp": expiry,
    }
    token = jwt.encode(token_data, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    return LoginResponse(
        access_token=token,
        username=user.username,
        role=role_val,
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """JWT验证 - 解析token获取当前用户"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username is None:
            raise HTTPException(status_code=401, detail="无效的token")
        return {"username": username, "role": role}
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="无效的token或token已过期")
