from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SignupReq(BaseModel):
    name: str
    email: str
    student_code: str
    password: str
    college: Optional[str] = ""
    branch: Optional[str] = ""
    semester: Optional[str] = ""


class LoginReq(BaseModel):
    email: str
    password: str


class AdminLoginReq(BaseModel):
    username: str
    password: str


class ExamStartReq(BaseModel):
    exam_id: str


class FrameReq(BaseModel):
    frame_b64: str
    student_id: str
    session_id: str


class SubmitAnswersReq(BaseModel):
    answers: dict  # {question_id: selected_option_index}
    exam_id: str
    force_cheater: bool = False


class CreateExamReq(BaseModel):
    title: str
    category: Optional[str] = "General"
    description: Optional[str] = ""
    duration_min: Optional[int] = 60
    total_marks: Optional[int] = 100
    pass_marks: Optional[int] = 40
