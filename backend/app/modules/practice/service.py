from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime
import json
import random
from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.questions.service import QuestionService


# 难度三档
DIFFICULTY_LEVELS = ("easy", "medium", "hard")
# 某档不足时，从有余量的档补位的优先级：中等 → 简单 → 困难
FILL_ORDER = ("medium", "easy", "hard")


class QuotaShortageError(Exception):
    """配额无法补足时整批拒绝，携带每档需求、可用数和缺口。"""

    def __init__(self, detail: dict):
        self.detail = detail
        super().__init__(detail.get("message", "题目数量不足，无法按配额创建练习"))


class PracticeService:
    @staticmethod
    async def create_session(
        user_id: str,
        mode: str,
        subject_id: str,
        knowledge_ids: Optional[List[str]] = None,
        question_count: int = 20,
        difficulty: Optional[str] = None,
        easy_count: Optional[int] = None,
        medium_count: Optional[int] = None,
        hard_count: Optional[int] = None
    ) -> dict:
        quota_counts = PracticeService._parse_quota_counts(
            mode, question_count, easy_count, medium_count, hard_count
        )

        db = get_db()
        redis = get_redis()

        quota_snapshot: Optional[dict] = None
        if quota_counts is not None:
            # 随机练习按难度配额抽题：不足档按 中等→简单→困难 顺序补位，
            # 仍不足则整批拒绝，绝不产生短会话或半个会话
            questions, quota_snapshot = await PracticeService._draw_quota_questions(
                subject_id=subject_id,
                knowledge_ids=knowledge_ids,
                quota_counts=quota_counts
            )
        elif mode == "random":
            questions = await QuestionService.get_random_questions(
                subject_id=subject_id,
                knowledge_ids=knowledge_ids,
                difficulty=difficulty,
                count=question_count
            )
        else:
            query = {"subject_id": subject_id}
            if knowledge_ids:
                query["knowledge_ids"] = {"$in": knowledge_ids}
            if difficulty:
                query["difficulty"] = difficulty
            cursor = db.questions.find(query).limit(question_count)
            questions = await cursor.to_list(length=question_count)

        if not questions:
            raise ValueError("没有找到符合条件的题目")

        question_ids = [str(q["_id"]) for q in questions]
        session_dict: Dict[str, Any] = {
            "user_id": user_id,
            "mode": mode,
            "subject_id": subject_id,
            "knowledge_ids": knowledge_ids,
            "question_ids": question_ids,
            "current_index": 0,
            "answers": {},
            "total": len(question_ids),
            "correct_count": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        # 创建成功后按题号快照继续：把配额与实际补位结果一并固化到会话
        if quota_snapshot is not None:
            session_dict["quota"] = quota_snapshot

        result = await db.practice_sessions.insert_one(session_dict)
        session_dict["_id"] = str(result.inserted_id)
        session_dict["id"] = str(result.inserted_id)

        if redis:
            key = f"practice:{user_id}:{str(result.inserted_id)}"
            await redis.setex(key, 3600 * 24, json.dumps(session_dict, default=str))

        return session_dict

    @staticmethod
    def _parse_quota_counts(
        mode: str,
        question_count: int,
        easy_count: Optional[int],
        medium_count: Optional[int],
        hard_count: Optional[int]
    ) -> Optional[Dict[str, int]]:
        """校验三档配额入参，返回 {easy, medium, hard}，未走配额模式时返回 None。"""
        raw = {
            "easy": easy_count,
            "medium": medium_count,
            "hard": hard_count
        }
        provided = [value for value in raw.values() if value is not None]
        if not provided:
            return None

        if mode != "random":
            raise ValueError("按难度配额抽题仅支持随机练习模式")
        if any(value is None for value in raw.values()):
            raise ValueError("请同时填写简单、中等、困难三档题数")
        if any(value < 0 for value in raw.values()):
            raise ValueError("各难度题数不能为负数")

        quota_counts = {level: int(raw[level]) for level in DIFFICULTY_LEVELS}
        total = sum(quota_counts.values())
        if total != question_count:
            raise ValueError(
                f"三档题数之和（{total}）必须等于总题数（{question_count}）"
            )
        if total <= 0:
            raise ValueError("总题数必须大于 0")
        return quota_counts

    @staticmethod
    async def _draw_quota_questions(
        subject_id: str,
        knowledge_ids: Optional[List[str]],
        quota_counts: Dict[str, int]
    ):
        """按难度配额抽题的全部业务：余量统计 → 补位 → 整批校验 → 抽样。"""
        available = await QuestionService.count_questions_by_difficulty(
            subject_id, knowledge_ids
        )
        requested = {level: quota_counts[level] for level in DIFFICULTY_LEVELS}
        total_requested = sum(requested.values())

        # 各档先用本档题，缺口等待有余量的档补位。
        # allocated：实际从该档题库抽出的题数（补位会多抽）
        # covered：该档需求已被满足的题数（含其他档补入）
        allocated = {
            level: min(requested[level], available[level])
            for level in DIFFICULTY_LEVELS
        }
        covered = dict(allocated)
        transfers: List[Dict[str, str | int]] = []

        # 对每个缺档，按 中等→简单→困难 的顺序从有余量的档借题；
        # 借位档跳过缺档自身
        for deficit_level in DIFFICULTY_LEVELS:
            need = requested[deficit_level] - covered[deficit_level]
            if need <= 0:
                continue

            for donor in FILL_ORDER:
                if need == 0:
                    break
                if donor == deficit_level:
                    continue
                surplus = available[donor] - allocated[donor]
                if surplus <= 0:
                    continue
                take = min(need, surplus)
                allocated[donor] += take
                covered[deficit_level] += take
                need -= take
                transfers.append({
                    "from_difficulty": donor,
                    "to_difficulty": deficit_level,
                    "count": take
                })

        # 补足后仍缺题：整批拒绝，返回每档需求、可用数和缺口
        shortage = {
            level: requested[level] - covered[level]
            for level in DIFFICULTY_LEVELS
            if covered[level] < requested[level]
        }
        total_shortage = sum(shortage.values())
        if total_shortage > 0:
            levels_detail = {
                level: {
                    "requested": requested[level],
                    "available": available[level],
                    "shortage": requested[level] - covered[level]
                }
                for level in DIFFICULTY_LEVELS
            }
            raise QuotaShortageError({
                "code": "QUOTA_SHORTAGE",
                "message": "题库余量不足，无法按难度配额凑齐本次练习，已整批取消",
                "total_requested": total_requested,
                "total_available": sum(available.values()),
                "total_shortage": total_shortage,
                "levels": levels_detail
            })

        # 逐档抽样并排除已抽中的题号，保证同一会话题号不重复
        questions: List[dict] = []
        used_ids: List[str] = []
        for level in DIFFICULTY_LEVELS:
            need = allocated[level]
            if need <= 0:
                continue
            picked = await QuestionService.sample_questions_by_difficulty(
                subject_id=subject_id,
                difficulty=level,
                count=need,
                knowledge_ids=knowledge_ids,
                exclude_ids=used_ids
            )
            if len(picked) != need:
                # 并发等原因导致余量变化，为避免短会话同样整批拒绝
                raise QuotaShortageError({
                    "code": "QUOTA_SHORTAGE",
                    "message": "抽题过程中题库余量发生变化，已整批取消，请重试",
                    "total_requested": total_requested,
                    "total_available": sum(available.values()),
                    "total_shortage": total_requested - len(used_ids) - len(picked),
                    "levels": {
                        level: {
                            "requested": requested[level],
                            "available": available[level],
                            "shortage": requested[level] - covered[level]
                        }
                        for level in DIFFICULTY_LEVELS
                    }
                })
            used_ids.extend(str(q["_id"]) for q in picked)
            questions.extend(picked)

        # 打乱快照顺序，避免简单/中等/困难各成一坨
        random.shuffle(questions)

        received = {level: 0 for level in DIFFICULTY_LEVELS}
        for transfer in transfers:
            received[transfer["to_difficulty"]] += transfer["count"]

        quota_snapshot = {
            "total_requested": total_requested,
            "total_available": sum(available.values()),
            "levels": {
                level: {
                    "requested": requested[level],
                    "available": available[level],
                    "allocated": allocated[level],
                    "filled": received[level]
                }
                for level in DIFFICULTY_LEVELS
            },
            "transfers": transfers
        }
        return questions, quota_snapshot

    @staticmethod
    async def get_session(session_id: str, user_id: str) -> Optional[dict]:
        db = get_db()
        redis = get_redis()

        if redis:
            key = f"practice:{user_id}:{session_id}"
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)

        if not ObjectId.is_valid(session_id):
            return None
        session = await db.practice_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id
        })

        if session:
            session["id"] = str(session["_id"])
            session["_id"] = str(session["_id"])
            if redis:
                key = f"practice:{user_id}:{session_id}"
                await redis.setex(key, 3600 * 24, json.dumps(session, default=str))

        return session

    @staticmethod
    async def get_current_question(session: dict) -> Optional[dict]:
        current_index = session.get("current_index", 0)
        question_ids = session.get("question_ids", [])
        if 0 <= current_index < len(question_ids):
            return await QuestionService.get_question_by_id(question_ids[current_index])
        return None

    @staticmethod
    async def submit_answer(
        session_id: str,
        user_id: str,
        question_id: str,
        user_answer: Any
    ) -> Dict[str, Any]:
        db = get_db()
        redis = get_redis()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        result = await QuestionService.check_answer(question_id, user_answer, user_id)

        current_index = session.get("current_index", 0)
        question_ids = session.get("question_ids", [])

        is_new_answer = question_id not in session.get("answers", {})
        new_answers = session.get("answers", {}).copy()
        new_answers[question_id] = {
            "user_answer": user_answer,
            "is_correct": result.is_correct,
            "submitted_at": datetime.utcnow().isoformat()
        }

        new_correct_count = session.get("correct_count", 0)
        if result.is_correct and is_new_answer:
            new_correct_count += 1

        update_data = {
            "answers": new_answers,
            "correct_count": new_correct_count,
            "current_index": min(current_index + 1, len(question_ids)),
            "updated_at": datetime.utcnow()
        }

        await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": update_data}
        )

        if not result.is_correct:
            await PracticeService._add_to_errors(user_id, question_id)

        session.update(update_data)
        if redis:
            key = f"practice:{user_id}:{session_id}"
            await redis.setex(key, 3600 * 24, json.dumps(session, default=str))

        progress = {
            "current": session["current_index"],
            "total": session["total"],
            "correct": new_correct_count,
            "accuracy": round(new_correct_count / session["current_index"] * 100, 1) if session["current_index"] > 0 else 0
        }

        return {
            "question_id": question_id,
            "is_correct": result.is_correct,
            "correct_answer": result.correct_answer,
            "explanation": result.explanation,
            "progress": progress,
            "is_finished": session["current_index"] >= session["total"]
        }

    @staticmethod
    async def _add_to_errors(user_id: str, question_id: str):
        db = get_db()
        question = await QuestionService.get_question_by_id(question_id)
        if not question:
            return

        existing = await db.errors.find_one({
            "user_id": user_id,
            "question_id": question_id
        })

        if existing:
            await db.errors.update_one(
                {"_id": existing["_id"]},
                {
                    "$inc": {"wrong_count": 1},
                    "$set": {"last_wrong_at": datetime.utcnow()}
                }
            )
        else:
            await db.errors.insert_one({
                "user_id": user_id,
                "question_id": question_id,
                "subject_id": question.get("subject_id"),
                "knowledge_ids": question.get("knowledge_ids", []),
                "wrong_count": 1,
                "created_at": datetime.utcnow(),
                "last_wrong_at": datetime.utcnow(),
                "mastered": False
            })

    @staticmethod
    async def navigate_question(
        session_id: str,
        user_id: str,
        direction: str
    ) -> Optional[dict]:
        db = get_db()
        redis = get_redis()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        question_ids = session.get("question_ids", [])
        current_index = session.get("current_index", 0)

        if direction == "prev":
            new_index = max(0, current_index - 1)
        elif direction == "next":
            new_index = min(len(question_ids) - 1, current_index + 1)
        else:
            new_index = current_index

        await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"current_index": new_index}}
        )

        session["current_index"] = new_index
        if redis:
            key = f"practice:{user_id}:{session_id}"
            await redis.setex(key, 3600 * 24, json.dumps(session, default=str))

        if 0 <= new_index < len(question_ids):
            return await QuestionService.get_question_by_id(question_ids[new_index])
        return None

    @staticmethod
    async def get_session_progress(session_id: str, user_id: str) -> dict:
        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        answers = session.get("answers", {})
        correct_count = sum(1 for a in answers.values() if a.get("is_correct"))

        return {
            "current": session.get("current_index", 0),
            "total": session.get("total", 0),
            "correct": correct_count,
            "accuracy": round(correct_count / len(answers) * 100, 1) if answers else 0,
            "answers": answers
        }
