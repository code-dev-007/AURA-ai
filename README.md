# AURA AI v2.0 — Exam Proctoring System (FastAPI)

**AI-powered exam proctoring** app with a built-in **Student Portal** + **Admin Dashboard**, real-time WebSocket events, and a SQLite database.


# User Interface(UI)
image.png

## Quick start

### Prerequisites
- **Python 3.10+**
- A working webcam (for proctoring signals)

## Project structure (updated)

```text
Aura AI Proctor Exam/
├─ app.py                      # FastAPI app + core logic (DB, auth helpers, DSA, pipeline, UI loader)
├─ routes/
│  ├─ __init__.py               # register_routes(app, deps)
│  ├─ deps.py                   # RouteDeps container (injects app.py funcs/state into routers)
│  ├─ schemas.py                # Pydantic request schemas (moved from app.py)
│  ├─ auth.py                   # /auth/* endpoints
│  ├─ exam.py                   # /exams, /exam/*, /analyze/frame endpoints
│  ├─ admin.py                  # /admin/* endpoints
│  ├─ ws.py                     # WebSocket endpoints (/ws/*)
│  └─ pages.py                  # HTML page routes: /, /student, /admin
└─ ui/
   ├─ index.html
   ├─ student.html
   └─ admin.html
```

### Install

```bash
pip install fastapi uvicorn sqlalchemy "python-jose[cryptography]" "passlib[bcrypt]" opencv-python numpy
```

### Run

```bash
python app.py
```

Then open:
- **Home**: `http://localhost:8000/`
- **Student Portal**: `http://localhost:8000/student`
- **Admin Dashboard**: `http://localhost:8000/admin`
- **API docs (Swagger)**: `http://localhost:8000/docs`

**Default admin login**: `admin / admin123`

## What the app includes (as implemented in `app.py`)

### Built-in UI
- **Student portal** (`/student`): signup/login, choose exam, start exam session, submit answers, live proctoring signals.
- **Admin dashboard** (`/admin`): live monitoring, exam reports, leaderboard, coordinated-cluster detection, create exams, list students.

### Data stored (SQLite)
- Local database file: **`aura_v2.db`** (auto-created)
- Tables (SQLAlchemy ORM): `students`, `exams`, `exam_sessions`, `violations`, `admin_users`

On first start, the app auto-seeds:
- **Admin** user: `admin / admin123`
- **5 exam types** (General Aptitude, DSA & Algorithms, Python Coding, Mathematics, Computer Science)

## Proctoring + DSA (as used in code)

The proctoring pipeline tracks events like tab switching, minimizing, face missing, multiple faces, phone detection, and head turns.

DSA concepts implemented (see `app.py` header):
- **Deque**: O(1) per-student rolling event buffer
- **Trie**: O(k) cheat-sequence pattern detection
- **Graph + BFS**: coordinated cheating cluster detection
- **Max-Heap**: violation-based ranking / leaderboard
- **Sliding Window**: burst detection (e.g., tab-switch spikes)
- **Hash Map**: O(1) session/event lookup
- **Weighted scoring**: aggregate violation scoring

## API overview

### Auth
- `POST /auth/signup`
- `POST /auth/login` (returns bearer token)
- `POST /auth/admin/login`

### Exams
- `GET /exams`
- `GET /exam/questions/{category}`
- `POST /exam/start` (requires student bearer token)
- `POST /exam/submit` (requires student bearer token)

### Proctoring (webcam frames)
- `POST /analyze/frame` (base64-encoded frame, generates events)

### Admin
- `GET /admin/live`
- `GET /admin/report/{exam_id}`
- `GET /admin/leaderboard`
- `GET /admin/clusters`
- `POST /admin/exam/create`
- `GET /admin/students`

## WebSockets (real-time events)
- **Student events**: `ws://localhost:8000/ws/{student_id}`
  - Client sends JSON like: `{"event":"tab_switch","details":"...","timestamp":<unix_seconds>}`
- **Admin live channel**: `ws://localhost:8000/ws/admin/live`


## ⚙️ Configuration

This project uses environment variables for configuration.

Create a `.env` file in the root directory and add the following:

```env
# ═══════════════════════════════════════════════════════
# AURA AI PROCTOR EXAM CONFIGURATION (DO NOT USE REAL VALUES)
# ═══════════════════════════════════════════════════════

# Database
DATABASE_URL=sqlite:///aura_v2.db

# JWT Authentication
SECRET_KEY=your_secret_key_here
ALGORITHM=
TOKEN_HOURS=

# API
API_URL=http://localhost:8000

# Server
HOST=0.0.0.0
PORT=8000
RELOAD=true


## Notes
- The server runs on **port 8000** and uses Uvicorn with `reload=True` when started via `python app.py`.
- Proctoring webcam analysis is implemented with **OpenCV Haar cascades** (face) plus lightweight heuristics (e.g., phone-like rectangle detection).
#
