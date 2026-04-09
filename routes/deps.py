from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class RouteDeps:
    # ---- DB ----
    get_db: Callable[[], Any]

    # ---- Models ----
    Student: Any
    Exam: Any
    ExamSession: Any
    Violation: Any
    AdminUser: Any

    # ---- Auth helpers ----
    hash_password: Callable[[str], str]
    verify_password: Callable[[str, str], bool]
    create_token: Callable[[Dict[str, Any]], str]
    get_current_user_id: Callable[..., str]

    # ---- Exam / logic ----
    gen_id: Callable[[], str]
    QUESTION_BANK: Dict[str, Any]
    init_session: Callable[..., None]
    finalize: Callable[..., Dict[str, Any]]
    build_exam_summary: Callable[..., Dict[str, Any]]
    analyze_frame: Callable[[str], Dict[str, Any]]
    pipeline: Callable[..., Any]

    # ---- In-memory state / DSA ----
    sessions: Dict[str, Any]
    admin_ws_list: list
    student_ws_map: Dict[str, Any]
    vheap: Any
    bgraph: Any

    # ---- UI ----
    load_ui_page: Callable[[str], str]
