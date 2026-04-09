from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .deps import RouteDeps
from .schemas import CreateExamReq


def get_router(deps: RouteDeps) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/live")
    async def live():
        return [
            {
                "student_id": sid,
                "student_name": s["name"],
                "score": s["score"],
                "tab_switches": s["tabs"],
                "minimizes": s["mins"],
                "face_missing": s["faces"],
                "phone_det": s["phone"],
                "head_turns": s["head"],
                "verdict": "⚠️ SUSPICIOUS" if s["score"] >= 10 else "✅ CLEAN",
            }
            for sid, s in deps.sessions.items()
            if s.get("active")
        ]

    @router.get("/report/{exam_id}")
    async def exam_report(exam_id: str, db: Session = Depends(deps.get_db)):
        return deps.build_exam_summary(exam_id, db)

    @router.get("/leaderboard")
    async def leaderboard():
        return deps.vheap.get_ranked()

    @router.get("/clusters")
    async def clusters():
        return deps.bgraph.all_clusters()

    @router.post("/exam/create")
    async def create_exam(req: CreateExamReq, db: Session = Depends(deps.get_db)):
        e = deps.Exam(
            id=deps.gen_id(),
            title=req.title,
            category=req.category,
            description=req.description,
            duration_min=req.duration_min,
            total_marks=req.total_marks,
            pass_marks=req.pass_marks,
            is_active=True,
        )
        db.add(e)
        db.commit()
        return {"message": "Exam created", "exam_id": e.id}

    @router.get("/students")
    async def all_students(db: Session = Depends(deps.get_db)):
        students = db.query(deps.Student).all()
        result = []
        for s in students:
            latest = (
                db.query(deps.ExamSession)
                .filter(deps.ExamSession.student_id == s.id)
                .order_by(deps.ExamSession.started_at.desc())
                .first()
            )
            result.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "email": s.email,
                    "student_code": s.student_code,
                    "college": s.college,
                    "branch": s.branch,
                    "total_exams": db.query(deps.ExamSession)
                    .filter(deps.ExamSession.student_id == s.id)
                    .count(),
                    "last_verdict": latest.verdict if latest else "N/A",
                }
            )
        return result

    return router
