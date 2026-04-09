from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .deps import RouteDeps
from .schemas import ExamStartReq, FrameReq, SubmitAnswersReq


def get_router(deps: RouteDeps) -> APIRouter:
    router = APIRouter(tags=["exam"])

    @router.get("/exams")
    async def list_exams(db: Session = Depends(deps.get_db)):
        exams = db.query(deps.Exam).filter(deps.Exam.is_active == True).all()
        return [
            {
                "id": e.id,
                "title": e.title,
                "category": e.category,
                "duration_min": e.duration_min,
                "total_marks": e.total_marks,
                "description": e.description,
            }
            for e in exams
        ]

    @router.get("/exam/questions/{category}")
    async def get_questions(category: str):
        qs = deps.QUESTION_BANK.get(category, deps.QUESTION_BANK["General Aptitude"])
        return [{"id": q["id"], "q": q["q"], "opts": q["opts"], "marks": q["marks"]} for q in qs]

    @router.post("/exam/start")
    async def start_exam(
        req: ExamStartReq,
        db: Session = Depends(deps.get_db),
        sid: str = Depends(deps.get_current_user_id),
    ):
        stu = db.query(deps.Student).filter(deps.Student.id == sid).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        exam = db.query(deps.Exam).filter(deps.Exam.id == req.exam_id).first()
        if not exam:
            raise HTTPException(404, "Exam not found")

        active = (
            db.query(deps.ExamSession)
            .filter(deps.ExamSession.student_id == sid, deps.ExamSession.is_active == True)
            .first()
        )
        if active:
            return {
                "session_id": active.id,
                "exam_title": exam.title,
                "exam_category": exam.category,
                "duration_min": exam.duration_min,
                "student_name": stu.name,
                "total_marks": exam.total_marks,
            }

        sess_id = deps.gen_id()
        db.add(deps.ExamSession(id=sess_id, student_id=sid, exam_id=req.exam_id, is_active=True))
        db.commit()

        deps.init_session(sid, sess_id, stu.name, req.exam_id)
        deps.bgraph.add_student(sid, 0, stu.name)
        for o in (
            db.query(deps.ExamSession)
            .filter(
                deps.ExamSession.exam_id == req.exam_id,
                deps.ExamSession.is_active == True,
                deps.ExamSession.id != sess_id,
            )
            .all()
        ):
            deps.bgraph.add_edge(sid, o.student_id)

        return {
            "session_id": sess_id,
            "exam_title": exam.title,
            "exam_category": exam.category,
            "duration_min": exam.duration_min,
            "student_name": stu.name,
            "total_marks": exam.total_marks,
            "message": "Exam started! Good luck.",
        }

    @router.post("/exam/submit")
    async def submit_exam(
        req: SubmitAnswersReq,
        db: Session = Depends(deps.get_db),
        sid: str = Depends(deps.get_current_user_id),
    ):
        # Calculate exam score
        qs = deps.QUESTION_BANK.get(req.exam_id, [])
        exam = db.query(deps.Exam).filter(deps.Exam.id == req.exam_id).first()
        if exam:
            qs = deps.QUESTION_BANK.get(exam.category, [])

        exam_score = 0
        for q in qs:
            ans = req.answers.get(str(q["id"]))
            if ans is not None and int(ans) == q["ans"]:
                exam_score += q["marks"]

        dbsess = (
            db.query(deps.ExamSession)
            .filter(deps.ExamSession.student_id == sid, deps.ExamSession.is_active == True)
            .first()
        )
        if dbsess:
            dbsess.exam_score = exam_score
            dbsess.answers = json.dumps(req.answers)
            db.commit()

        result = deps.finalize(sid, db)
        if not result:
            raise HTTPException(404, "No active session")
        deps.bgraph.update_score(sid, result.get("score", 0))
        return {
            **result,
            "exam_score": exam_score,
            "clusters": deps.bgraph.all_clusters(),
            "message": "Exam submitted successfully!",
        }

    @router.post("/analyze/frame")
    async def analyze_webcam(req: FrameReq, db: Session = Depends(deps.get_db)):
        det = deps.analyze_frame(req.frame_b64)
        for ev in det.get("events", []):
            if ev != "face_ok":
                await deps.pipeline(req.student_id, ev, f"Frame:{ev}", time.time(), db)
        return det

    return router
