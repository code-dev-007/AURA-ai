from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .deps import RouteDeps
from .schemas import AdminLoginReq, LoginReq, SignupReq


def get_router(deps: RouteDeps) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/signup")
    async def signup(req: SignupReq, db: Session = Depends(deps.get_db)):
        if db.query(deps.Student).filter(deps.Student.email == req.email).first():
            raise HTTPException(400, "Email already registered")
        if db.query(deps.Student).filter(deps.Student.student_code == req.student_code).first():
            raise HTTPException(400, "Student ID already exists")
        s = deps.Student(
            id=deps.gen_id(),
            name=req.name,
            email=req.email,
            student_code=req.student_code,
            hashed_password=deps.hash_password(req.password),
            college=req.college,
            branch=req.branch,
            semester=req.semester,
        )
        db.add(s)
        db.commit()
        return {"message": "Account created!", "student_id": s.id}

    @router.post("/login")
    async def login(req: LoginReq, db: Session = Depends(deps.get_db)):
        s = db.query(deps.Student).filter(deps.Student.email == req.email).first()
        if not s or not deps.verify_password(req.password, s.hashed_password):
            raise HTTPException(401, "Invalid email or password")
        token = deps.create_token({"sub": s.id, "name": s.name})
        return {
            "access_token": token,
            "token_type": "bearer",
            "student_id": s.id,
            "student_name": s.name,
            "student_code": s.student_code,
        }

    @router.post("/admin/login")
    async def admin_login(req: AdminLoginReq, db: Session = Depends(deps.get_db)):
        a = db.query(deps.AdminUser).filter(deps.AdminUser.username == req.username).first()
        if not a or not deps.verify_password(req.password, a.hashed_password):
            raise HTTPException(401, "Invalid admin credentials")
        return {
            "access_token": deps.create_token({"sub": req.username, "role": "admin"}),
            "token_type": "bearer",
        }

    return router
