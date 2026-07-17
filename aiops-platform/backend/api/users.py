"""用户管理 API"""

import bcrypt as _bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.db import async_session_factory
from models.user import User, UserRole
from sqlalchemy import select

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = ""
    role: str = "user"
    email: Optional[str] = ""
    phone: Optional[str] = ""


class UserUpdate(BaseModel):
    """用户更新（所有字段可选）"""
    username: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str]
    role: str
    email: Optional[str]
    enabled: int

    class Config:
        from_attributes = True


@router.get("/", response_model=list[UserResponse])
async def list_users():
    """获取用户列表"""
    async with async_session_factory() as session:
        result = await session.execute(select(User))
        return result.scalars().all()


@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate):
    """创建用户"""
    async with async_session_factory() as session:
        existing = await session.execute(
            select(User).where(User.username == user.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已存在")

        salt = _bcrypt.gensalt()
        new_user = User(
            username=user.username,
            password_hash=_bcrypt.hashpw(user.password.encode(), salt).decode(),
            display_name=user.display_name,
            role=user.role,
            email=user.email,
            phone=user.phone,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user


@router.get("/me")
async def get_current_user():
    """获取当前用户信息（简化版，无JWT验证）"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "email": user.email,
        }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    """获取单个用户"""
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate):
    """更新用户信息"""
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="用户不存在")
        existing.display_name = user.display_name
        existing.email = user.email
        existing.phone = user.phone
        existing.role = user.role
        if user.password:
            salt = _bcrypt.gensalt()
            existing.password_hash = _bcrypt.hashpw(user.password.encode(), salt).decode()
        await session.commit()
        await session.refresh(existing)
        return existing


@router.delete("/{user_id}")
async def delete_user(user_id: int):
    """删除用户"""
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        await session.delete(user)
        await session.commit()
        return {"message": "删除成功"}