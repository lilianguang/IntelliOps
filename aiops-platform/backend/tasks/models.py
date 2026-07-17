"""任务队列模型"""

from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """任务模型"""
    task_id: str
    skill: str
    query: str
    time_range: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: Optional[str] = None