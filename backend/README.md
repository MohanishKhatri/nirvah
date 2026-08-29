# NIRVAH — Backend

FastAPI + SQLAlchemy (async). Runs on SQLite out of the box; point `DATABASE_URL` at Postgres
when the container is up.

## Run

```bash
python -m venv .venv && .venv/Scripts/activate      # bash: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs · health: http://localhost:8000/health

Tables are created on startup — no migration step needed to get going.

## Seeding

```bash
python seed/make_pdfs.py             # renders the policy markdown to PDFs (needs fpdf2)
python seed/seed.py --reset          # approver contacts + ingest the 4 policies
python seed/demo_scenarios.py --reset # both demo scenarios, mid-flight
```

Run these from the repo root. `seed/policies/finance_circular_14_2026.pdf` is deliberately not
ingested — it is uploaded live during the demo.

## Env switches

| Var | Effect |
|---|---|
| `USE_LLM_MOCK` | `true` uses the deterministic rule engine in `services/llm_mock.py`; `false` + a `GEMINI_API_KEY` calls Gemini 1.5 Flash |
| `DEV_AUTH_BYPASS` | `true` accepts any bearer token as `demo.student@<domain>`; set `false` to verify real Google ID tokens |
| `RESEND_API_KEY` | empty logs emails (with the approval links) instead of sending |
| `ADMIN_PASSWORD` | value the `x-admin-password` header must match |
| `DATABASE_URL` | sqlite by default; a relative sqlite path always resolves inside `backend/` |

Every Gemini call falls back to the mock rather than raising, so a bad key or a malformed
response degrades quietly instead of 500-ing the API.

## Endpoints

```
POST   /api/requests/                   submit request text
POST   /api/requests/{id}/answer        answer a follow-up question
GET    /api/requests/                   list my requests
GET    /api/requests/{id}/workflow      full DAG + status

GET    /api/approvals/action            email link lands here (?token=&action=)
POST   /api/approvals/reject            submit rejection with a reason (?token=)

POST   /api/policies/upload             multipart: file + name (admin)
GET    /api/policies/                   list policies (admin)
POST   /api/policies/diff               ?old_policy_id=&new_policy_id= (admin)
POST   /api/policies/{id}/publish       make a version live (admin)
GET    /api/policies/contacts           role -> email map (admin)
POST   /api/policies/contacts           upsert by role (admin)

POST   /api/admin/send-reminders        nudge approvers past the 24h window (admin)
POST   /api/admin/recompile-pending     re-run the compiler over live requests (admin)
```

`recompile-pending` is what makes an uploaded circular change workflows that already exist:
approvals already given are kept, newly justified approvers are appended, and nodes the new
policy no longer justifies are dropped only while still blocked.

## Notes on retrieval

Chunks are embedded with Gemini `embedding-001` when a key is present, and with a hashed
bag-of-words vector otherwise, so retrieval works with no key at all. Vectors are stored as JSON
and compared in Python — at a few hundred chunks that is instant and keeps one code path across
SQLite and Postgres. Swap `search_relevant_chunks` for a pgvector `<=>` query if the corpus grows.
