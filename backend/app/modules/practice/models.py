from typing import Optional, List, Any, Literal
from datetime import datetime
from pydantic import BaseModel

# 难度三档取值，与题库 difficulty 字段保持一致
DifficultyLevel = Literal["easy", "medium", "hard"]


class PracticeConfig(BaseModel):
    mode: str
    subject_id: str
    knowledge_ids: Optional[List[str]] = None
    question_count: int = 20
    difficulty: Optional[str] = None
    # 随机练习按难度配额抽题：三档需求题数，给出后三档之和必须等于总题数
    easy_count: Optional[int] = None
    medium_count: Optional[int] = None
    hard_count: Optional[int] = None


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


class QuotaTransfer(BaseModel):
    """一条补位记录：from_difficulty 有余量，补了 to_difficulty 的缺口。"""
    from_difficulty: DifficultyLevel
    to_difficulty: DifficultyLevel
    count: int


class QuotaLevelStat(BaseModel):
    """单档配额信息：需求、可用、实际抽中、被其他档补走/补入后的数量。"""
    requested: int
    available: int
    allocated: int
    filled: int


class QuotaReport(BaseModel):
    """配额抽题成功后的快照结果，设置页据此展示实际补位情况。"""
    total_requested: int
    total_available: int
    levels: dict
    transfers: List[QuotaTransfer]


class QuotaShortageDetail(BaseModel):
    """整批拒绝时返回的缺口报告：每档需求、可用数和缺口。"""
    code: str
    message: str
    total_requested: int
    total_available: int
    total_shortage: int
    levels: dict
