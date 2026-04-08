"""
╔══════════════════════════════════════════════════════════════════════╗
║         AURA AI v2.0 — EXAM PROCTORING SYSTEM                       ║
║         Single File · Production Ready · Best DSA Project            ║
║                                                                      ║
║  RUN:   python app.py                                                ║
║  URLs:  http://localhost:8000/          → Home                       ║
║         http://localhost:8000/student   → Student Portal             ║
║         http://localhost:8000/admin     → Admin Dashboard            ║
║  Login: admin / admin123                                             ║
╚══════════════════════════════════════════════════════════════════════╝

DSA ALGORITHMS USED:
  1. Deque          → O(1) real-time event buffer per student
  2. Trie           → O(k) cheat pattern sequence detection
  3. Graph + BFS    → O(V+E) coordinated cheating cluster detection
  4. Max-Heap       → O(log n) student violation ranker
  5. Sliding Window → O(n) burst tab-switch detector
  6. Hash Map       → O(1) session lookup per event
  7. Weighted Score → O(n) violation scorer
"""

# ═══════════════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════════════
import json, time, uuid, base64, heapq, warnings, os
from pathlib import Path
import cv2, numpy as np
from collections import deque, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Optional, List

warnings.filterwarnings("ignore")

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
import uvicorn

# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — DATABASE
# ═══════════════════════════════════════════════════════════════════════
# Load `.env` early (safe no-op if missing)
if load_dotenv:
    load_dotenv()


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aura_v2.db")
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()

def get_db():
    db = SessionLocal()
    try:    yield db
    finally: db.close()

def gen_id(): return str(uuid.uuid4())

class Student(Base):
    __tablename__ = "students"
    id              = Column(String, primary_key=True, default=gen_id)
    name            = Column(String, nullable=False)
    email           = Column(String, unique=True, nullable=False)
    student_code    = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    college         = Column(String, default="")
    branch          = Column(String, default="")
    semester        = Column(String, default="")
    created_at      = Column(DateTime, default=datetime.utcnow)
    sessions        = relationship("ExamSession", back_populates="student")

class Exam(Base):
    __tablename__ = "exams"
    id           = Column(String, primary_key=True, default=gen_id)
    title        = Column(String, nullable=False)
    category     = Column(String, default="General")   # General, DSA, Coding, Math, Science
    description  = Column(String, default="")
    duration_min = Column(Integer, default=60)
    total_marks  = Column(Integer, default=100)
    pass_marks   = Column(Integer, default=40)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    sessions     = relationship("ExamSession", back_populates="exam")

class ExamSession(Base):
    __tablename__ = "exam_sessions"
    id              = Column(String, primary_key=True, default=gen_id)
    student_id      = Column(String, ForeignKey("students.id"), nullable=False)
    exam_id         = Column(String, ForeignKey("exams.id"), nullable=False)
    started_at      = Column(DateTime, default=datetime.utcnow)
    ended_at        = Column(DateTime, nullable=True)
    violation_score = Column(Integer, default=0)
    exam_score      = Column(Integer, default=0)
    tab_switches    = Column(Integer, default=0)
    minimizes       = Column(Integer, default=0)
    face_missing    = Column(Integer, default=0)
    multi_faces     = Column(Integer, default=0)
    phone_detected  = Column(Integer, default=0)
    head_turns      = Column(Integer, default=0)
    answers         = Column(Text, default="{}")
    verdict         = Column(String, default="PENDING")
    is_active       = Column(Boolean, default=True)
    student         = relationship("Student", back_populates="sessions")
    exam            = relationship("Exam", back_populates="sessions")
    violations      = relationship("Violation", back_populates="session")

class Violation(Base):
    __tablename__ = "violations"
    id         = Column(String, primary_key=True, default=gen_id)
    session_id = Column(String, ForeignKey("exam_sessions.id"), nullable=False)
    event_type = Column(String, nullable=False)
    timestamp  = Column(DateTime, default=datetime.utcnow)
    severity   = Column(Integer, default=1)
    details    = Column(String, default="")
    session    = relationship("ExamSession", back_populates="violations")

class AdminUser(Base):
    __tablename__ = "admin_users"
    id              = Column(String, primary_key=True, default=gen_id)
    username        = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

def create_tables(): Base.metadata.create_all(bind=engine)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — AUTH
# ═══════════════════════════════════════════════════════════════════════
SECRET_KEY    = os.getenv("SECRET_KEY", "dev_only_change_me")
ALGORITHM     = os.getenv("ALGORITHM", "HS256")
TOKEN_HOURS   = _env_int("TOKEN_HOURS", 8)
pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(p: str) -> str:
    return pwd_context.hash(p[:72])

def verify_password(p: str, h: str) -> bool:
    try:    return pwd_context.verify(p[:72], h)
    except: return False

def create_token(data: dict) -> str:
    d = data.copy()
    d["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    return jwt.encode(d, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid = payload.get("sub")
        if not uid: raise HTTPException(401, "Invalid token")
        return uid
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — DSA #1: EVENT QUEUE (Deque)
# ═══════════════════════════════════════════════════════════════════════
class EventQueue:
    """
    DSA: collections.deque — O(1) push/pop both ends.
    Stores last 50 events per student as sliding buffer.
    Used to feed recent events into Trie for pattern matching.
    """
    def __init__(self, maxlen=50):
        self.buffer = deque(maxlen=maxlen)

    def push(self, etype: str, details: str = ""):
        self.buffer.append({"type": etype, "ts": time.time(), "details": details})

    def get_recent(self, n=10): return list(self.buffer)[-n:]
    def get_types(self):        return [e["type"] for e in self.buffer]
    def count(self, t: str):    return sum(1 for e in self.buffer if e["type"] == t)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — DSA #2: CHEAT TRIE (Pattern Detection)
# ═══════════════════════════════════════════════════════════════════════
class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end   = False
        self.name     = None
        self.weight   = 0

class CheatTrie:
    """
    DSA: Trie (Prefix Tree) — O(k) pattern lookup.
    Pre-loads 13 cheat sequences as trie paths.
    Scans last 8 events per pipeline tick.
    """
    def __init__(self):
        self.root = TrieNode()
        for seq, name, w in [
            (["tab_switch","tab_switch","tab_switch"],       "rapid_tab_switching",      10),
            (["blur","tab_switch","focus"],                  "tab_escape_attempt",         7),
            (["minimize","minimize"],                        "repeated_minimize",           6),
            (["face_missing","face_missing","face_missing"], "prolonged_absence",           9),
            (["multiple_faces","tab_switch"],                "collaboration_attempt",      12),
            (["blur","minimize","blur"],                     "distraction_pattern",         5),
            (["phone_detected","face_missing"],              "phone_cheat_attempt",        11),
            (["second_screen","tab_switch"],                 "second_device_cheat",        13),
            (["head_turn_left","head_turn_right"],           "looking_at_notes",            7),
            (["tab_switch","face_missing","tab_switch"],     "systematic_cheat_sequence",  15),
            (["multiple_faces","face_missing"],              "switcher_with_helper",       14),
            (["phone_detected","tab_switch"],                "phone_tab_combo",            12),
            (["head_turn_left","head_turn_left","head_turn_left"], "persistent_left_gaze",  8),
        ]:
            n = self.root
            for e in seq:
                n.children.setdefault(e, TrieNode())
                n = n.children[e]
            n.is_end, n.name, n.weight = True, name, w

    def match(self, events: list) -> list:
        matched = []
        for i in range(len(events)):
            n = self.root
            for e in events[i:]:
                if e in n.children:
                    n = n.children[e]
                    if n.is_end:
                        matched.append((n.name, n.weight))
                        break
                else: break
        return matched

# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — DSA #3: BEHAVIOR GRAPH + BFS
# ═══════════════════════════════════════════════════════════════════════
class BehaviorGraph:
    """
    DSA: Graph (Adjacency List) + BFS — O(V+E).
    Students in same exam = nodes. Same-time joiners = edges.
    BFS finds coordinated cheating clusters.
    """
    def __init__(self):
        self.graph  = defaultdict(list)
        self.scores = {}
        self.names  = {}

    def add_student(self, sid, score=0, name=""):
        self.scores[sid] = score
        self.names[sid]  = name

    def update_score(self, sid, score):
        self.scores[sid] = score

    def add_edge(self, a, b):
        if b not in self.graph[a]: self.graph[a].append(b)
        if a not in self.graph[b]: self.graph[b].append(a)

    def bfs_cluster(self, start, threshold=15):
        if self.scores.get(start, 0) < threshold: return []
        visited, q, flagged = set(), deque([start]), []
        while q:
            node = q.popleft()
            if node in visited: continue
            visited.add(node)
            if self.scores.get(node, 0) >= threshold:
                flagged.append({"student_id": node, "name": self.names.get(node,"?"),
                                "score": self.scores[node]})
                for nb in self.graph[node]:
                    if nb not in visited: q.append(nb)
        return flagged

    def all_clusters(self, threshold=15):
        visited, clusters = set(), []
        for sid in self.scores:
            if sid not in visited and self.scores[sid] >= threshold:
                c = self.bfs_cluster(sid, threshold)
                [visited.add(s["student_id"]) for s in c]
                if c: clusters.append(c)
        return clusters

# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — DSA #4: MAX-HEAP RANKER
# ═══════════════════════════════════════════════════════════════════════
class ViolationHeap:
    """
    DSA: heapq (Max-Heap via negation) — O(log n) insert.
    Ranks all students by violation score at exam end.
    Deduplicates by student_id using seen set.
    """
    def __init__(self):
        self._heap    = []
        self._entries = {}

    def push(self, sid, score, name=""):
        heapq.heappush(self._heap, (-score, sid, name))
        self._entries[sid] = score

    def get_ranked(self):
        seen, result = set(), []
        for neg, sid, name in sorted(self._heap):
            if sid not in seen:
                seen.add(sid)
                s = -neg
                result.append({"student_id": sid, "name": name, "score": s,
                               "verdict": "CHEATER" if s >= 15 else "NOT CHEATER"})
        return result

# ═══════════════════════════════════════════════════════════════════════
# SECTION 7 — DSA #5: SLIDING WINDOW (Burst Detection)
# ═══════════════════════════════════════════════════════════════════════
class SlidingWindow:
    """
    DSA: Sliding Window on timestamps — O(n) per check.
    Detects burst events (e.g., 3 tab switches in 30 seconds).
    Prunes stale events on each record() call.
    """
    def __init__(self, window_sec=30, burst_n=3):
        self.window = window_sec
        self.n      = burst_n
        self.events = []

    def record(self, etype):
        now = time.time()
        self.events.append({"t": now, "e": etype})
        self.events = [x for x in self.events if now - x["t"] <= self.window]

    def is_burst(self, etype):
        cutoff = time.time() - self.window
        return sum(1 for x in self.events if x["e"] == etype and x["t"] >= cutoff) >= self.n

# ═══════════════════════════════════════════════════════════════════════
# SECTION 8 — VIOLATION WEIGHTS (DSA #6: Weighted Scorer + Hash Map)
# ═══════════════════════════════════════════════════════════════════════
# DSA: Hash Map — O(1) weight lookup per violation event
WEIGHTS = {
    "tab_switch":3,"window_minimize":2,"blur":1,"face_missing":5,
    "multiple_faces":8,"phone_detected":10,"second_screen":11,
    "head_turn_left":3,"head_turn_right":3,"audio_spike":4,
    "rapid_tab_switching":10,"tab_escape_attempt":7,"repeated_minimize":6,
    "prolonged_absence":9,"collaboration_attempt":12,"distraction_pattern":5,
    "phone_cheat_attempt":11,"second_device_cheat":13,"looking_at_notes":7,
    "systematic_cheat_sequence":15,"switcher_with_helper":14,
    "phone_tab_combo":12,"persistent_left_gaze":8,
}
THRESHOLD = 15

def compute_score(v): return sum(WEIGHTS.get(x, 1) for x in v)
def get_verdict(s):   return "CHEATER" if s >= THRESHOLD else "NOT CHEATER"
def describe(e):
    return {
        "tab_switch":"Student switched browser tab",
        "window_minimize":"Student minimized exam window",
        "blur":"Exam window lost focus",
        "face_missing":"No face detected in webcam",
        "multiple_faces":"Multiple faces — possible collaboration",
        "phone_detected":"Smartphone detected in camera frame",
        "second_screen":"Secondary screen/laptop detected",
        "head_turn_left":"Student looking sharply left",
        "head_turn_right":"Student looking sharply right",
        "rapid_tab_switching":"Burst of rapid tab switches",
        "collaboration_attempt":"External collaboration detected",
        "prolonged_absence":"Face absent for extended time",
        "looking_at_notes":"Student reading from notes",
        "systematic_cheat_sequence":"Full cheat sequence detected",
        "phone_tab_combo":"Phone + tab switch combination",
        "persistent_left_gaze":"Persistent left gaze detected",
    }.get(e, "Suspicious behavior detected")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 9 — OPENCV 360° DETECTION
# ═══════════════════════════════════════════════════════════════════════
_CASCADE       = cv2.data.haarcascades
face_cascade   = cv2.CascadeClassifier(_CASCADE + "haarcascade_frontalface_default.xml")
profile_casc   = cv2.CascadeClassifier(_CASCADE + "haarcascade_profileface.xml")
eye_cascade    = cv2.CascadeClassifier(_CASCADE + "haarcascade_eye.xml")

def decode_frame(b64):
    if "," in b64: b64 = b64.split(",")[1]
    arr = np.frombuffer(base64.b64decode(b64), np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def head_dir(frame, rect):
    x,y,w,h = rect
    gray = cv2.cvtColor(frame[y:y+h,x:x+w], cv2.COLOR_BGR2GRAY)
    eyes = eye_cascade.detectMultiScale(gray, 1.1, 4)
    if len(eyes)==0: return "head_turned"
    if len(eyes)==1:
        ex = eyes[0][0]
        if ex < w*0.35: return "head_turn_left"
        if ex > w*0.55: return "head_turn_right"
    return "face_forward"

def detect_phone(frame):
    edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(5,5),0),50,150)
    for cnt in cv2.findContours(edges,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        approx = cv2.approxPolyDP(cnt, 0.02*cv2.arcLength(cnt,True), True)
        area   = cv2.contourArea(cnt)
        if len(approx)==4 and 500<area<30000:
            x,y,w,h = cv2.boundingRect(approx)
            asp = w/h if h>0 else 0
            if (0.4<asp<0.75 or 1.3<asp<2.5) and np.mean(frame[y:y+h,x:x+w])>100:
                return True
    return False

def detect_glow(frame):
    mask = cv2.inRange(cv2.cvtColor(frame,cv2.COLOR_BGR2HSV),
                       np.array([0,0,200]), np.array([180,30,255]))
    return (np.sum(mask>0)/(frame.shape[0]*frame.shape[1]))>0.15

def analyze_frame(b64):
    res = {"events":[],"face_count":0,"phone":False,"screen":False}
    try:
        frame = decode_frame(b64)
        if frame is None: res["events"].append("face_missing"); return res
        gray  = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray,1.1,5,minSize=(60,60))
        profs = profile_casc.detectMultiScale(gray,1.1,5,minSize=(50,50))
        total = len(faces)+len(profs)
        res["face_count"] = total
        if   total==0: res["events"].append("face_missing")
        elif total>=2: res["events"].append("multiple_faces")
        elif len(faces)==1:
            d = head_dir(frame, faces[0])
            if d in ("head_turn_left","head_turn_right"): res["events"].append(d)
        if detect_phone(frame): res["phone"]=True; res["events"].append("phone_detected")
        if detect_glow(frame):  res["screen"]=True; res["events"].append("second_screen")
        if not res["events"]: res["events"].append("face_ok")
    except Exception as ex:
        res["events"].append("face_missing"); res["error"]=str(ex)
    return res

# ═══════════════════════════════════════════════════════════════════════
# SECTION 10 — GLOBAL SESSION STATE (DSA #6: Hash Map)
# ═══════════════════════════════════════════════════════════════════════
sessions:       Dict[str, dict]      = {}   # O(1) student lookup
admin_ws_list:  list                 = []
student_ws_map: Dict[str, WebSocket] = {}
vheap    = ViolationHeap()
bgraph   = BehaviorGraph()
trie     = CheatTrie()

def init_session(sid, session_id, name, exam_id):
    sessions[sid] = {
        "session_id": session_id, "name": name, "exam_id": exam_id,
        "started": time.time(),
        "eq":  EventQueue(50),
        "sw":  SlidingWindow(30, 3),
        "violations": [], "score": 0,
        "tabs":0,"mins":0,"faces":0,"mfaces":0,"phone":0,"head":0,
        "answers": {}, "active": True,
    }

async def pipeline(sid, etype, details, ts, db):
    """
    DSA Pipeline per event:
    Step 1: Deque push
    Step 2: Sliding Window record
    Step 3: Direct weight lookup (Hash Map)
    Step 4: Burst check (Sliding Window)
    Step 5: Trie sequence match
    Step 6: Weighted score update
    Step 7: DB commit
    Step 8: Admin WebSocket broadcast
    """
    s = sessions.get(sid)
    if not s: return {}
    new_v = []

    s["eq"].push(etype, details)                    # Step 1: Deque
    s["sw"].record(etype)                           # Step 2: Sliding Window

    if etype in WEIGHTS and etype != "face_ok":     # Step 3: Hash Map
        new_v.append(etype)
        if   etype=="tab_switch":      s["tabs"]  +=1
        elif etype=="window_minimize": s["mins"]  +=1
        elif etype=="face_missing":    s["faces"] +=1
        elif etype=="multiple_faces":  s["mfaces"]+=1
        elif etype=="phone_detected":  s["phone"] +=1
        elif etype in("head_turn_left","head_turn_right"): s["head"]+=1

    if s["sw"].is_burst(etype):                     # Step 4: Burst check
        burst = f"rapid_{etype}"
        if burst in WEIGHTS and burst not in new_v: new_v.append(burst)

    recent = s["eq"].get_types()[-8:]               # Step 5: Trie match
    for pname, _ in trie.match(recent):
        if pname not in s["violations"]: new_v.append(pname)

    added = compute_score(new_v)                    # Step 6: Score
    s["score"] += added
    s["violations"] += new_v

    for v in new_v:                                 # Step 7: DB
        if v in WEIGHTS:
            db.add(Violation(session_id=s["session_id"], event_type=v,
                             timestamp=datetime.fromtimestamp(ts),
                             severity=WEIGHTS.get(v,1), details=describe(v)))
    dbsess = db.query(ExamSession).filter(ExamSession.id==s["session_id"]).first()
    if dbsess:
        dbsess.violation_score=s["score"]; dbsess.tab_switches=s["tabs"]
        dbsess.minimizes=s["mins"]; dbsess.face_missing=s["faces"]
        dbsess.multi_faces=s["mfaces"]; dbsess.phone_detected=s["phone"]
        dbsess.head_turns=s["head"]
    db.commit()

    result = {"student_id":sid,"student_name":s["name"],"event":etype,
              "new_violations":new_v,"total_score":s["score"],
              "verdict":get_verdict(s["score"]),"tab_switches":s["tabs"],
              "minimizes":s["mins"],"face_missing":s["faces"],
              "phone_detected":s["phone"],"head_turns":s["head"]}

    dead = []                                       # Step 8: Broadcast
    for aws in admin_ws_list:
        try: await aws.send_json(result)
        except: dead.append(aws)
    for d in dead: admin_ws_list.remove(d)
    return result

def finalize(sid, db):
    s = sessions.get(sid)
    if not s: return {}
    score = s["score"]; verdict = get_verdict(score)
    dbsess = db.query(ExamSession).filter(ExamSession.id==s["session_id"]).first()
    if dbsess:
        dbsess.violation_score=score; dbsess.verdict=verdict
        dbsess.ended_at=datetime.utcnow(); dbsess.is_active=False
        db.commit()
    vheap.push(sid, score, s["name"])
    bgraph.update_score(sid, score)
    s["active"] = False
    return {"student_id":sid,"name":s["name"],"score":score,"verdict":verdict,
            "tabs":s["tabs"],"mins":s["mins"],"faces":s["faces"],
            "mfaces":s["mfaces"],"phone":s["phone"],"head":s["head"]}

def build_report(session_id, db):
    sess = db.query(ExamSession).filter(ExamSession.id==session_id).first()
    if not sess: return {"error":"Not found"}
    stu  = db.query(Student).filter(Student.id==sess.student_id).first()
    exam = db.query(Exam).filter(Exam.id==sess.exam_id).first()
    viols= db.query(Violation).filter(Violation.session_id==session_id).all()
    score = sess.violation_score or 0
    sess.verdict = get_verdict(score); db.commit()
    dur = "N/A"
    if sess.started_at and sess.ended_at:
        sec=int((sess.ended_at-sess.started_at).total_seconds())
        dur=f"{sec//60}m {sec%60}s"
    return {
        "session_id":session_id,
        "student_name":stu.name if stu else "?",
        "student_code":stu.student_code if stu else "?",
        "college":stu.college if stu else "",
        "branch":stu.branch if stu else "",
        "exam_title":exam.title if exam else "?",
        "exam_category":exam.category if exam else "?",
        "exam_score":sess.exam_score or 0,
        "total_marks":exam.total_marks if exam else 100,
        "pass_marks":exam.pass_marks if exam else 40,
        "started_at":sess.started_at.strftime("%Y-%m-%d %H:%M:%S") if sess.started_at else "N/A",
        "ended_at":sess.ended_at.strftime("%Y-%m-%d %H:%M:%S") if sess.ended_at else "N/A",
        "duration":dur,
        "tab_switches":sess.tab_switches or 0,
        "minimizes":sess.minimizes or 0,
        "face_missing":sess.face_missing or 0,
        "multiple_faces":sess.multi_faces or 0,
        "phone_detected":sess.phone_detected or 0,
        "head_turns":sess.head_turns or 0,
        "violation_log":[{"type":v.event_type,
                          "timestamp":v.timestamp.strftime("%H:%M:%S"),
                          "severity":v.severity,"details":v.details} for v in viols],
        "total_score":score,
        "verdict":get_verdict(score),
        "is_cheater":get_verdict(score)=="CHEATER",
    }

def build_exam_summary(exam_id, db):
    all_s = db.query(ExamSession).filter(ExamSession.exam_id==exam_id).all()
    exam  = db.query(Exam).filter(Exam.id==exam_id).first()
    reports  = [build_report(s.id, db) for s in all_s]
    cheaters = [r for r in reports if r.get("is_cheater")]
    return {
        "exam_id":exam_id,"exam_title":exam.title if exam else "?",
        "exam_category":exam.category if exam else "?",
        "total_students":len(reports),"cheaters_count":len(cheaters),
        "clean_count":len(reports)-len(cheaters),
        "reports":sorted(reports,key=lambda r:r.get("total_score",0),reverse=True),
    }

# ═══════════════════════════════════════════════════════════════════════
# SECTION 11 — EXAM QUESTION BANK
# ═══════════════════════════════════════════════════════════════════════
QUESTION_BANK = {
    "General Aptitude": [
        {"id":1,"q":"If a train travels 360 km in 4 hours, what is its speed?",
         "opts":["80 km/h","90 km/h","100 km/h","120 km/h"],"ans":1,"marks":4},
        {"id":2,"q":"What comes next in the series: 2, 6, 12, 20, 30, ?",
         "opts":["40","42","44","46"],"ans":1,"marks":4},
        {"id":3,"q":"A shopkeeper sells an article at 20% profit. If CP is ₹500, find SP.",
         "opts":["₹580","₹590","₹600","₹620"],"ans":2,"marks":4},
        {"id":4,"q":"Find the odd one out: Cat, Dog, Tiger, Rose",
         "opts":["Cat","Dog","Tiger","Rose"],"ans":3,"marks":4},
        {"id":5,"q":"If APPLE = 50, then MANGO = ?",
         "opts":["55","60","65","70"],"ans":1,"marks":4},
        {"id":6,"q":"A pipe fills a tank in 6 hours. Another empties it in 12 hours. Together?",
         "opts":["10 hours","11 hours","12 hours","14 hours"],"ans":2,"marks":4},
        {"id":7,"q":"What is 15% of 240?",
         "opts":["32","34","36","38"],"ans":2,"marks":4},
        {"id":8,"q":"If 6 workers complete a job in 8 days, how many days for 4 workers?",
         "opts":["10","11","12","14"],"ans":2,"marks":4},
        {"id":9,"q":"Which number is divisible by both 8 and 12?",
         "opts":["48","56","60","72"],"ans":0,"marks":4},
        {"id":10,"q":"Average of 5 numbers is 30. If one number is removed, average becomes 28. Find the removed number.",
         "opts":["36","38","40","42"],"ans":1,"marks":4},
    ],
    "DSA & Algorithms": [
        {"id":1,"q":"Time complexity of Binary Search on a sorted array of n elements?",
         "opts":["O(n)","O(log n)","O(n log n)","O(1)"],"ans":1,"marks":5},
        {"id":2,"q":"Which data structure uses LIFO (Last In First Out)?",
         "opts":["Queue","Stack","Linked List","Tree"],"ans":1,"marks":5},
        {"id":3,"q":"What is the worst-case time complexity of QuickSort?",
         "opts":["O(n log n)","O(n)","O(n²)","O(log n)"],"ans":2,"marks":5},
        {"id":4,"q":"In a Trie, inserting a word of length k has what complexity?",
         "opts":["O(1)","O(k)","O(n)","O(k²)"],"ans":1,"marks":5},
        {"id":5,"q":"Which traversal of a BST gives elements in sorted order?",
         "opts":["Preorder","Postorder","Inorder","Level order"],"ans":2,"marks":5},
        {"id":6,"q":"Dijkstra's algorithm is used for?",
         "opts":["Minimum Spanning Tree","Shortest Path","Sorting","Hashing"],"ans":1,"marks":5},
        {"id":7,"q":"Time complexity of Heap Sort?",
         "opts":["O(n)","O(n log n)","O(n²)","O(log n)"],"ans":1,"marks":5},
        {"id":8,"q":"Which data structure is best for implementing a priority queue?",
         "opts":["Array","Linked List","Heap","Stack"],"ans":2,"marks":5},
        {"id":9,"q":"BFS uses which data structure internally?",
         "opts":["Stack","Queue","Heap","Tree"],"ans":1,"marks":5},
        {"id":10,"q":"What is the space complexity of Merge Sort?",
         "opts":["O(1)","O(log n)","O(n)","O(n²)"],"ans":2,"marks":5},
    ],
    "Python Coding": [
        {"id":1,"q":"What is the output of: print(type([]))?",
         "opts":["<class 'list'>","<class 'array'>","list","[]"],"ans":0,"marks":5},
        {"id":2,"q":"Which keyword is used to define a function in Python?",
         "opts":["function","define","def","func"],"ans":2,"marks":5},
        {"id":3,"q":"What does len('Hello') return?",
         "opts":["4","5","6","Error"],"ans":1,"marks":5},
        {"id":4,"q":"What is the output of: print(2**10)?",
         "opts":["20","100","1024","512"],"ans":2,"marks":5},
        {"id":5,"q":"Which of these is a Python dictionary?",
         "opts":["[1,2,3]","(1,2,3)","{'a':1}","{1,2,3}"],"ans":2,"marks":5},
        {"id":6,"q":"What does 'append' do to a Python list?",
         "opts":["Removes last item","Adds item to start","Adds item to end","Sorts list"],"ans":2,"marks":5},
        {"id":7,"q":"How do you open a file for reading in Python?",
         "opts":["open('f','w')","open('f','r')","open('f','a')","open('f','x')"],"ans":1,"marks":5},
        {"id":8,"q":"What is the output of: print('Python'[1:4])?",
         "opts":["Pyt","yth","ytho","Pyth"],"ans":1,"marks":5},
        {"id":9,"q":"Which module is used for regular expressions in Python?",
         "opts":["regex","re","regexp","string"],"ans":1,"marks":5},
        {"id":10,"q":"What does isinstance(5, int) return?",
         "opts":["False","True","None","Error"],"ans":1,"marks":5},
    ],
    "Mathematics": [
        {"id":1,"q":"What is the value of sin(90°)?",
         "opts":["0","0.5","1","√2"],"ans":2,"marks":4},
        {"id":2,"q":"Derivative of x³ is?",
         "opts":["x²","2x","3x²","3x"],"ans":2,"marks":4},
        {"id":3,"q":"What is the sum of angles in a triangle?",
         "opts":["90°","180°","270°","360°"],"ans":1,"marks":4},
        {"id":4,"q":"√144 = ?",
         "opts":["11","12","13","14"],"ans":1,"marks":4},
        {"id":5,"q":"What is the probability of getting heads in a fair coin toss?",
         "opts":["1/4","1/3","1/2","2/3"],"ans":2,"marks":4},
        {"id":6,"q":"Integral of 2x dx is?",
         "opts":["2","x²","x² + C","2x²"],"ans":2,"marks":4},
        {"id":7,"q":"What is log₁₀(1000)?",
         "opts":["2","3","4","10"],"ans":1,"marks":4},
        {"id":8,"q":"What is the LCM of 12 and 18?",
         "opts":["24","30","36","48"],"ans":2,"marks":4},
        {"id":9,"q":"Area of circle with radius 7? (π=22/7)",
         "opts":["144","154","164","174"],"ans":1,"marks":4},
        {"id":10,"q":"HCF of 36 and 48?",
         "opts":["6","8","10","12"],"ans":3,"marks":4},
    ],
    "Computer Science": [
        {"id":1,"q":"Which layer of OSI model handles routing?",
         "opts":["Physical","Data Link","Network","Transport"],"ans":2,"marks":5},
        {"id":2,"q":"RAM stands for?",
         "opts":["Read Access Memory","Random Access Memory","Read And Memory","Random And Memory"],"ans":1,"marks":5},
        {"id":3,"q":"Which protocol is used for secure web browsing?",
         "opts":["HTTP","FTP","HTTPS","SMTP"],"ans":2,"marks":5},
        {"id":4,"q":"What is the base of hexadecimal number system?",
         "opts":["8","10","16","32"],"ans":2,"marks":5},
        {"id":5,"q":"Which of these is NOT an operating system?",
         "opts":["Ubuntu","Windows","Oracle","macOS"],"ans":2,"marks":5},
        {"id":6,"q":"What does CPU stand for?",
         "opts":["Central Process Unit","Central Processing Unit","Control Processing Unit","Core Processing Unit"],"ans":1,"marks":5},
        {"id":7,"q":"Which data type stores True/False in Python?",
         "opts":["int","str","bool","float"],"ans":2,"marks":5},
        {"id":8,"q":"What is the full form of SQL?",
         "opts":["Structured Query Language","Simple Query Language","System Query Language","Secure Query Language"],"ans":0,"marks":5},
        {"id":9,"q":"Which sorting algorithm has the best average case: O(n log n)?",
         "opts":["Bubble Sort","Selection Sort","Merge Sort","Insertion Sort"],"ans":2,"marks":5},
        {"id":10,"q":"In OOP, 'hiding internal details' is called?",
         "opts":["Inheritance","Polymorphism","Encapsulation","Abstraction"],"ans":2,"marks":5},
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# SECTION 12 — FASTAPI APP + LIFESPAN
# ═══════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app):
    # Startup
    create_tables()
    db = next(get_db())
    if not db.query(AdminUser).filter(AdminUser.username=="admin").first():
        db.add(AdminUser(id=gen_id(),username="admin",hashed_password=hash_password("admin123")))
        db.commit()
    # Create 5 exam types if not exist
    if not db.query(Exam).first():
        exams_to_add = [
            ("General Aptitude Test",  "General Aptitude", "Logical reasoning and aptitude questions",  60, 40, 16),
            ("DSA & Algorithms",       "DSA & Algorithms", "Data structures and algorithm questions",   90, 50, 20),
            ("Python Coding Test",     "Python Coding",    "Python programming and coding questions",   60, 50, 20),
            ("Mathematics Test",       "Mathematics",      "Algebra, calculus and statistics",          60, 40, 16),
            ("Computer Science Test",  "Computer Science", "OS, networking and CS fundamentals",        60, 50, 20),
        ]
        for title, cat, desc, dur, pm, tm in exams_to_add:
            db.add(Exam(id=gen_id(),title=title,category=cat,description=desc,
                        duration_min=dur,total_marks=tm*5,pass_marks=pm,is_active=True))
        db.commit()
    print("\n" + "="*60)
    print("  ✅  AURA AI v2.0 started!")
    print("  🌐  Home            : http://localhost:8000/")
    print("  🎓  Student Portal  : http://localhost:8000/student")
    print("  🛡️   Admin Dashboard : http://localhost:8000/admin")
    print("  📖  API Docs        : http://localhost:8000/docs")
    print("  🔑  Admin Login     : admin / admin123")
    print("  📚  Exams Available : 5 exam types loaded")
    print("="*60 + "\n")
    yield
    # Shutdown (nothing needed)

app = FastAPI(title="Aura AI v2.0", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

# ── Schemas ────────────────────────────────────────────────────
class SignupReq(BaseModel):
    name:str; email:str; student_code:str; password:str
    college:Optional[str]=""; branch:Optional[str]=""; semester:Optional[str]=""

class LoginReq(BaseModel):
    email:str; password:str

class AdminLoginReq(BaseModel):
    username:str; password:str

class ExamStartReq(BaseModel):
    exam_id:str

class FrameReq(BaseModel):
    frame_b64:str; student_id:str; session_id:str

class SubmitAnswersReq(BaseModel):
    answers: dict   # {question_id: selected_option_index}
    exam_id: str

class CreateExamReq(BaseModel):
    title:str; category:Optional[str]="General"
    description:Optional[str]=""; duration_min:Optional[int]=60
    total_marks:Optional[int]=100; pass_marks:Optional[int]=40

# ── Auth ────────────────────────────────────────────────────────
@app.post("/auth/signup")
async def signup(req:SignupReq, db:Session=Depends(get_db)):
    if db.query(Student).filter(Student.email==req.email).first():
        raise HTTPException(400,"Email already registered")
    if db.query(Student).filter(Student.student_code==req.student_code).first():
        raise HTTPException(400,"Student ID already exists")
    s = Student(id=gen_id(),name=req.name,email=req.email,
                student_code=req.student_code,hashed_password=hash_password(req.password),
                college=req.college,branch=req.branch,semester=req.semester)
    db.add(s); db.commit()
    return {"message":"Account created!","student_id":s.id}

@app.post("/auth/login")
async def login(req:LoginReq, db:Session=Depends(get_db)):
    s = db.query(Student).filter(Student.email==req.email).first()
    if not s or not verify_password(req.password, s.hashed_password):
        raise HTTPException(401,"Invalid email or password")
    token = create_token({"sub":s.id,"name":s.name})
    return {"access_token":token,"token_type":"bearer",
            "student_id":s.id,"student_name":s.name,"student_code":s.student_code}

@app.post("/auth/admin/login")
async def admin_login(req:AdminLoginReq, db:Session=Depends(get_db)):
    a = db.query(AdminUser).filter(AdminUser.username==req.username).first()
    if not a or not verify_password(req.password, a.hashed_password):
        raise HTTPException(401,"Invalid admin credentials")
    return {"access_token":create_token({"sub":req.username,"role":"admin"}),"token_type":"bearer"}

# ── Exam ────────────────────────────────────────────────────────
@app.get("/exams")
async def list_exams(db:Session=Depends(get_db)):
    exams = db.query(Exam).filter(Exam.is_active==True).all()
    return [{"id":e.id,"title":e.title,"category":e.category,
             "duration_min":e.duration_min,"total_marks":e.total_marks,
             "description":e.description} for e in exams]

@app.get("/exam/questions/{category}")
async def get_questions(category:str):
    qs = QUESTION_BANK.get(category, QUESTION_BANK["General Aptitude"])
    return [{"id":q["id"],"q":q["q"],"opts":q["opts"],"marks":q["marks"]} for q in qs]

@app.post("/exam/start")
async def start_exam(req:ExamStartReq, db:Session=Depends(get_db),
                     sid:str=Depends(get_current_user_id)):
    stu  = db.query(Student).filter(Student.id==sid).first()
    if not stu: raise HTTPException(404,"Student not found")
    exam = db.query(Exam).filter(Exam.id==req.exam_id).first()
    if not exam: raise HTTPException(404,"Exam not found")
    active = db.query(ExamSession).filter(
        ExamSession.student_id==sid, ExamSession.is_active==True).first()
    if active:
        return {"session_id":active.id,"exam_title":exam.title,
                "exam_category":exam.category,"duration_min":exam.duration_min,
                "student_name":stu.name,"total_marks":exam.total_marks}
    sess_id = gen_id()
    db.add(ExamSession(id=sess_id,student_id=sid,exam_id=req.exam_id,is_active=True))
    db.commit()
    init_session(sid, sess_id, stu.name, req.exam_id)
    bgraph.add_student(sid, 0, stu.name)
    for o in db.query(ExamSession).filter(ExamSession.exam_id==req.exam_id,
                ExamSession.is_active==True, ExamSession.id!=sess_id).all():
        bgraph.add_edge(sid, o.student_id)
    return {"session_id":sess_id,"exam_title":exam.title,"exam_category":exam.category,
            "duration_min":exam.duration_min,"student_name":stu.name,
            "total_marks":exam.total_marks,"message":"Exam started! Good luck."}

@app.post("/exam/submit")
async def submit_exam(req:SubmitAnswersReq, db:Session=Depends(get_db),
                      sid:str=Depends(get_current_user_id)):
    # Calculate exam score
    qs      = QUESTION_BANK.get(req.exam_id, [])
    # Try category match
    exam    = db.query(Exam).filter(Exam.id==req.exam_id).first()
    if exam:
        qs = QUESTION_BANK.get(exam.category, [])
    exam_score = 0
    for q in qs:
        ans = req.answers.get(str(q["id"]))
        if ans is not None and int(ans) == q["ans"]:
            exam_score += q["marks"]

    dbsess = db.query(ExamSession).filter(
        ExamSession.student_id==sid, ExamSession.is_active==True).first()
    if dbsess:
        dbsess.exam_score = exam_score
        dbsess.answers    = json.dumps(req.answers)
        db.commit()

    result = finalize(sid, db)
    if not result: raise HTTPException(404,"No active session")
    bgraph.update_score(sid, result.get("score",0))
    return {**result,"exam_score":exam_score,"clusters":bgraph.all_clusters(),
            "message":"Exam submitted successfully!"}

@app.post("/analyze/frame")
async def analyze_webcam(req:FrameReq, db:Session=Depends(get_db)):
    det = analyze_frame(req.frame_b64)
    for ev in det.get("events",[]):
        if ev != "face_ok":
            await pipeline(req.student_id, ev, f"Frame:{ev}", time.time(), db)
    return det

# ── Admin ────────────────────────────────────────────────────────
@app.get("/admin/live")
async def live():
    return [{"student_id":sid,"student_name":s["name"],"score":s["score"],
             "tab_switches":s["tabs"],"minimizes":s["mins"],"face_missing":s["faces"],
             "phone_det":s["phone"],"head_turns":s["head"],
             "verdict":"⚠️ SUSPICIOUS" if s["score"]>=10 else "✅ CLEAN"}
            for sid,s in sessions.items() if s.get("active")]

@app.get("/admin/report/{exam_id}")
async def exam_report(exam_id:str, db:Session=Depends(get_db)):
    return build_exam_summary(exam_id, db)

@app.get("/admin/leaderboard")
async def leaderboard(): return vheap.get_ranked()

@app.get("/admin/clusters")
async def clusters(): return bgraph.all_clusters()

@app.post("/admin/exam/create")
async def create_exam(req:CreateExamReq, db:Session=Depends(get_db)):
    e = Exam(id=gen_id(),title=req.title,category=req.category,
             description=req.description,duration_min=req.duration_min,
             total_marks=req.total_marks,pass_marks=req.pass_marks,is_active=True)
    db.add(e); db.commit()
    return {"message":"Exam created","exam_id":e.id}

@app.get("/admin/students")
async def all_students(db:Session=Depends(get_db)):
    students = db.query(Student).all()
    result = []
    for s in students:
        latest = db.query(ExamSession).filter(ExamSession.student_id==s.id).order_by(
            ExamSession.started_at.desc()).first()
        result.append({"id":s.id,"name":s.name,"email":s.email,
                        "student_code":s.student_code,"college":s.college,
                        "branch":s.branch,"total_exams":
                        db.query(ExamSession).filter(ExamSession.student_id==s.id).count(),
                        "last_verdict":latest.verdict if latest else "N/A"})
    return result

# ── WebSocket ────────────────────────────────────────────────────
@app.websocket("/ws/{student_id}")
async def student_ws(websocket:WebSocket, student_id:str):
    await websocket.accept()
    student_ws_map[student_id] = websocket
    try:
        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)
            db   = next(get_db())
            res  = await pipeline(student_id, data.get("event","unknown"),
                                  data.get("details",""), data.get("timestamp",time.time()), db)
            await websocket.send_json({"status":"ok","score":res.get("total_score",0)})
    except WebSocketDisconnect:
        student_ws_map.pop(student_id, None)

@app.websocket("/ws/admin/live")
async def admin_ws(websocket:WebSocket):
    await websocket.accept()
    admin_ws_list.append(websocket)
    try:
        await websocket.send_json({"type":"connected","msg":"Admin live connected"})
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in admin_ws_list: admin_ws_list.remove(websocket)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 13 — STUDENT HTML
# ═══════════════════════════════════════════════════════════════════════
_UI_DIR = Path(__file__).resolve().parent / "ui"
_ui_cache: dict[str, tuple[float, str]] = {}


def load_ui_page(filename: str) -> str:
    """
    Loads `ui/<filename>` as UTF-8 HTML.
    Uses a tiny mtime-based cache to avoid disk reads on every request.
    """
    path = _UI_DIR / filename
    stat = path.stat()
    mtime = stat.st_mtime

    cached = _ui_cache.get(filename)
    if cached and cached[0] == mtime:
        return cached[1]

    html = path.read_text(encoding="utf-8")
    _ui_cache[filename] = (mtime, html)
    return html


STUDENT_HTML = None  # legacy (moved to ui/student.html)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 14 — ADMIN HTML
# ═══════════════════════════════════════════════════════════════════════
ADMIN_HTML = None  # legacy (moved to ui/admin.html)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 15 — SERVE PAGES + RUN
# ═══════════════════════════════════════════════════════════════════════
@app.get("/student", response_class=HTMLResponse)
async def student_page(): return load_ui_page("student.html")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(): return load_ui_page("admin.html")

@app.get("/", response_class=HTMLResponse)
async def root():
    return load_ui_page("index.html")


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=_env_int("PORT", 8000),
        reload=os.getenv("RELOAD", "true").lower() in ("1", "true", "yes", "y", "on"),
    )
