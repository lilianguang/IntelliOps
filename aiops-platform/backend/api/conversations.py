"""对话历史与会话归档 API（用户隔离：普通用户仅见自己的会话，管理员可见全部）"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
from core.db import async_session_factory
from models.conversation import Conversation
from api.auth import get_current_user
from sqlalchemy import select, func

router = APIRouter()


def _serialize(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "conversation_id": conv.conversation_id,
        "tenant": conv.tenant,
        "user": conv.user,
        "skill": conv.skill,
        "title": conv.title,
        "query": conv.query,
        "summary": conv.summary,
        "risk_level": conv.risk_level.value if hasattr(conv.risk_level, "value") else conv.risk_level,
        "full_report": conv.full_report,
        "messages": conv.messages or [],
        "archived": conv.archived,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if getattr(conv, "updated_at", None) else None,
    }


def _is_admin(auth: dict) -> bool:
    return auth.get("role") == "admin"


@router.get("/conversations")
async def list_conversations(
    auth=Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    archived: Optional[int] = None,
    skill: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """获取历史对话列表（支持分页/筛选/关键字搜索）。普通用户仅见自己，管理员见全部。"""
    username = auth["username"]
    async with async_session_factory() as session:
        query = select(Conversation)
        # 用户隔离：非管理员只能看到自己的对话
        if not _is_admin(auth):
            query = query.where(Conversation.user == username)
        if archived is not None:
            query = query.where(Conversation.archived == archived)
        if skill:
            query = query.where(Conversation.skill == skill)
        if keyword:
            kw = f"%{keyword}%"
            query = query.where(
                (Conversation.title.like(kw)) | (Conversation.query.like(kw))
            )

        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        query = query.order_by(Conversation.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        items = [_serialize(c) for c in result.scalars().all()]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, auth=Depends(get_current_user)):
    """获取对话详情（含完整多轮消息）"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.conversation_id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        # 权限：非本人且非管理员禁止查看
        if conv.user != auth["username"] and not _is_admin(auth):
            raise HTTPException(status_code=403, detail="无权查看该会话")
        return _serialize(conv)


@router.put("/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str, auth=Depends(get_current_user), archived: int = 1
):
    """会话归档 / 取消归档"""
    if archived not in (0, 1):
        raise HTTPException(status_code=400, detail="archived 只能为 0 或 1")
    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.conversation_id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if conv.user != auth["username"] and not _is_admin(auth):
            raise HTTPException(status_code=403, detail="无权操作该会话")
        conv.archived = archived
        await session.commit()
    return {"message": "操作成功", "archived": archived}


@router.put("/conversations/batch-archive")
async def batch_archive_conversations(data: dict, auth=Depends(get_current_user)):
    """批量归档 / 取消归档

    Body: {"conversation_ids": ["uuid1","uuid2"], "archived": 1}
    仅操作当前用户名下的会话（管理员可操作全部）。
    """
    ids = data.get("conversation_ids") or []
    archived = 1 if data.get("archived", 1) else 0
    if not ids:
        raise HTTPException(status_code=400, detail="conversation_ids 不能为空")
    async with async_session_factory() as session:
        query = select(Conversation).where(Conversation.conversation_id.in_(ids))
        if not _is_admin(auth):
            query = query.where(Conversation.user == auth["username"])
        result = await session.execute(query)
        convs = result.scalars().all()
        for c in convs:
            c.archived = archived
        await session.commit()
    return {"message": "操作成功", "updated": len(convs)}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, auth=Depends(get_current_user)):
    """删除对话"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.conversation_id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if conv.user != auth["username"] and not _is_admin(auth):
            raise HTTPException(status_code=403, detail="无权删除该会话")
        await session.delete(conv)
        await session.commit()
    return {"message": "删除成功"}


class RenameRequest(BaseModel):
    title: str


@router.put("/conversations/{conversation_id}/rename")
async def rename_conversation(
    conversation_id: str, body: RenameRequest, auth=Depends(get_current_user)
):
    """重命名对话标题"""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if len(title) > 128:
        raise HTTPException(status_code=400, detail="标题不能超过128字符")
    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.conversation_id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if conv.user != auth["username"] and not _is_admin(auth):
            raise HTTPException(status_code=403, detail="无权操作该会话")
        conv.title = title
        await session.commit()
    return {"message": "重命名成功", "title": title}
