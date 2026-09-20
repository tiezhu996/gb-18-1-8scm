from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


class DifficultyQuota(BaseModel):
    """随机练习按难度配额抽题：简单/中等/困难三档各自的需求题数"""
    easy: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    hard: int = Field(default=0, ge=0)


class PracticeConfig(BaseModel):
    mode: str
    subject_id: str
    knowledge_ids: Optional[List[str]] = None
    question_count: int = 20
    difficulty: Optional[str] = None
    difficulty_quota: Optional[DifficultyQuota] = None


class QuotaTierStat(BaseModel):
    """单档配额的实际执行结果：需求、可用、实际入卷与补位进出"""
    difficulty: str
    demand: int
    available: int
    assigned: int
    backfilled_in: int
    backfilled_out: int


class QuotaResult(BaseModel):
    """配额抽题结果快照，随会话保存，供设置页/练习页展示实际补位结果"""
    total: int
    tiers: List[QuotaTierStat]


class PracticeQuestion(BaseModel):
    id: str
    type: str
    content: str
    options: Optional[List[dict]] = None
    difficulty: str
    knowledge_ids: List[str]


class PracticeSession(BaseModel):
    id: str
    mode: str
    subject_id: str
    knowledge_ids: Optional[List[str]]
    question_ids: List[str]
    current_index: int
    answers: dict
    total: int
    correct_count: int
    created_at: datetime
    updated_at: datetime


class PracticeSubmit(BaseModel):
    session_id: str
    question_id: str
    user_answer: Any


class PracticeResult(BaseModel):
    question_id: str
    is_correct: bool
    correct_answer: Any
    explanation: Optional[str]
    progress: dict
