# Workstream B — API / Database / Email

**Owner:** Person B
**Branch:** `feature/api`
**Depends on:** Person A's function signatures (mock them until real ones land)
**Blocks:** nobody — Person C builds against the API spec below, not your implementation

---

## What you're building

The database schema, every HTTP endpoint, the workflow state machine, and email sending. You import Person A's functions but **do not wait for them** — write mock versions returning hardcoded dicts matching the contracts, and swap them out later.

Files you own:

```
backend/
├── app/
│   ├── main.py
│   ├── db.py
│   ├── models.py
│   ├── dependencies.py
│   ├── routers/
│   │   ├── policies.py
│   │   ├── requests.py
│   │   └── approvals.py
│   └── services/
│       ├── workflow.py     ← workflow state machine (yours)
│       └── email.py        ← Resend integration (yours)
└── alembic/
```

---

## Setup

```bash
pip install fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg \
            alembic python-dotenv resend python-multipart \
            google-auth httpx pgvector
```

**docker-compose.yml** (repo root):

```yaml
version: '3.8'
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: nirvah
      POSTGRES_USER: nirvah
      POSTGRES_PASSWORD: nirvah
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
volumes:
  pgdata:
```

**.env:**
```
DATABASE_URL=postgresql+asyncpg://nirvah:nirvah@localhost:5432/nirvah
GEMINI_API_KEY=...
RESEND_API_KEY=...
FRONTEND_URL=http://localhost:3000
ADMIN_PASSWORD=nirvah_admin_2024
GOOGLE_CLIENT_ID=...
ALLOWED_EMAIL_DOMAIN=nitk.edu.in
REMINDER_AFTER_HOURS=24
```

Enable pgvector on startup: `CREATE EXTENSION IF NOT EXISTS vector`

---

## Database schema

Seven tables. Field notes explain the non-obvious ones.

### `policies`
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | string | "Finance Policy" |
| file_path | string | where the PDF sits on disk |
| uploaded_at | datetime | |
| is_active | bool | false until published |
| version | int | increments on re-upload of same policy |

### `policy_chunks`
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| policy_id | FK | |
| chunk_text | text | the actual excerpt |
| embedding | Vector(768) | pgvector column, Gemini embedding-001 dim |
| page_number | int | for citations |
| source_section | string, nullable | "§8.2" if detectable |

### `approver_contacts`
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| role | string, unique | "dean" — matches the `role` A's LLM returns |
| label | string | "Dean of Student Affairs" |
| email | string | where approval emails go |

### `requests`
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| raw_text | text | what the student originally typed |
| structured_fields | JSON | Contract 1 object |
| conversation | JSON | array of `{role, text, asking_for?, answered_field?}` |
| status | string | see Contract 5 |
| submitted_by | string | student's email from Google token |
| created_at / updated_at | datetime | |

### `workflow_nodes`
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| request_id | FK | |
| role | string | matches `approver_contacts.role` |
| label | string | display name |
| status | string | see Contract 4 |
| reason | text | why this node exists |
| source_doc | string | policy name |
| source_section | string, nullable | "§8.2" |
| parallel_group | string, nullable | same value = runs together |
| order_index | int | lower = earlier. same = parallel. |
| approval_token | string, unique | UUID. This is the auth for email links. |
| activated_at | datetime, nullable | when it became active — used for reminders |
| completed_at | datetime, nullable | |
| reminder_sent_at | datetime, nullable | prevents duplicate reminders |

### `events`
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| request_id | FK, nullable | null for policy-level events |
| event_type | string | see list below |
| payload | JSON | |
| created_at | datetime | |

Event types: `REQUEST_CREATED`, `QUESTION_ASKED`, `ANSWER_GIVEN`, `WORKFLOW_COMPILED`, `NODE_ACTIVATED`, `NODE_APPROVED`, `NODE_REJECTED`, `REMINDER_SENT`, `REQUEST_APPROVED`, `REQUEST_REJECTED`, `POLICY_UPLOADED`, `POLICY_PUBLISHED`

---

## Auth

Two separate mechanisms.

**Students:** frontend sends the Google ID token in `Authorization: Bearer <token>`. Verify it with `google.oauth2.id_token.verify_oauth2_token()`, check the email ends with your allowed domain, return the email. That email is the user identity — no user table needed.

**Admin:** frontend sends `x-admin-password` header. Compare against the env var. That's it.

**Approvers:** no auth. The UUID token in the URL is the credential.

---

## The workflow state machine — `services/workflow.py`

This is the core logic you own. Two functions.

### `compile_and_store_workflow(db, request, retrieved_chunks)`

1. Call A's `compile_workflow()` with the request's structured fields and the chunks
2. If `immediate_blocks` is non-empty → set request status to `rejected`, store the reason, return early
3. Otherwise, create one `workflow_nodes` row per approval, all with status `blocked`, each with a fresh UUID token
4. Set request status to `pending`
5. Log a `WORKFLOW_COMPILED` event
6. Call `activate_next_nodes()`

### `activate_next_nodes(db, request_id)`

This runs after every approval. Logic:

1. Load all nodes for the request
2. Find the lowest `order_index` among nodes still `blocked`
3. If there are none → all approvals are done → set request status to `approved`, log event, email the applicant, return
4. Otherwise, for every blocked node at that lowest order_index: set status to `active`, set `activated_at`, log `NODE_ACTIVATED`, and send an approval email

**This is how parallelism works.** Nodes sharing an `order_index` all activate together. The next tier only activates once every node in the current tier is approved — which falls out naturally because "lowest blocked order" doesn't advance until the current tier clears.

---

## Email — `services/email.py`

Resend. Four functions.

### `send_approval_email(to_email, token, label, brief, request)`

The important one. HTML email containing:
- NIRVAH header
- "Action required: {label}"
- The approval brief paragraph from A's `generate_approval_brief()`
- A summary box: purpose, budget, attendees
- Two big buttons:
  - Approve → `{FRONTEND_URL}/approve/{token}?action=approve`
  - Reject → `{FRONTEND_URL}/approve/{token}?action=reject`
- Small footer noting the link is unique and no login is needed

Keep it simple HTML with inline styles. Email clients don't do CSS classes.

### `send_reminder_email(...)`
Same as above but with reminder framing in the brief position.

### `send_rejection_notification(to_email, purpose, rejected_by, reason)`
Goes to the student. States who rejected, why, and that they can revise and resubmit.

### `send_approval_notification(to_email, purpose)`
Goes to the student when all nodes clear.

---

## API Endpoints — full spec

**This section is the contract with Person C.** Get it right, then don't change it without telling them.

---

### `POST /api/requests/`

Submit a new request.

**Auth:** student Bearer token
**Body:** `{ "text": "Our Robotics Club wants..." }`

**Flow:** call A's `extract_intent()` → create request row → if `missing_fields` is non-empty, call A's `generate_followup_question()` for the first one and return it. Otherwise run vector search + compile workflow immediately.

**Response — needs more info:**
```json
{
  "request_id": 12,
  "status": "awaiting_info",
  "question": "What is the name of your club?",
  "asking_for": "club_name",
  "fields_extracted": { "budget": 35000, "attendees": 120 }
}
```

**Response — complete, workflow made:**
```json
{
  "request_id": 12,
  "status": "pending",
  "workflow_compiled": true,
  "immediate_blocks": []
}
```

**Response — blocked by policy:**
```json
{
  "request_id": 12,
  "status": "rejected",
  "workflow_compiled": false,
  "immediate_blocks": ["Seminar Hall 2 capacity is 500; requested 2500 attendees"]
}
```

---

### `POST /api/requests/{id}/answer`

Answer a follow-up question.

**Auth:** student Bearer token (must match `submitted_by`)
**Body:** `{ "field": "club_name", "value": "Robotics Club" }`

**Flow:** merge the answer into `structured_fields` (try casting to int/float first, fall back to string) → remove that field from `missing_fields` → append to `conversation` → if more fields remain, generate the next question and return it. Otherwise run vector search + compile workflow.

**Response:** same shapes as `POST /api/requests/`.

---

### `GET /api/requests/{id}/workflow`

The main data source for the tracking page.

**Auth:** student Bearer token (must match `submitted_by`)

**Response:**
```json
{
  "request_id": 12,
  "status": "pending",
  "structured_fields": {
    "category": "student_event",
    "purpose": "Two-day drone workshop",
    "budget": 35000,
    "attendees": 120,
    "venue": "Seminar Hall 2"
  },
  "conversation": [
    { "role": "user", "text": "Our Robotics Club wants..." },
    { "role": "assistant", "text": "What is the name of your club?", "asking_for": "club_name" }
  ],
  "nodes": [
    {
      "id": 45,
      "role": "faculty_advisor",
      "label": "Faculty Advisor",
      "status": "approved",
      "reason": "All club events require Faculty Advisor approval",
      "source_doc": "Student Activity Policy",
      "source_section": "§3",
      "parallel_group": null,
      "order_index": 1,
      "activated_at": "2026-08-29T10:00:00",
      "completed_at": "2026-08-29T11:30:00"
    },
    {
      "id": 47,
      "role": "security",
      "label": "Security Office",
      "status": "active",
      "reason": "3 external speakers require security clearance",
      "source_doc": "Security Guidelines",
      "source_section": "§4.1",
      "parallel_group": "clearances",
      "order_index": 3,
      "activated_at": "2026-08-29T11:30:00",
      "completed_at": null
    }
  ]
}
```

---

### `GET /api/requests/`

List the logged-in student's requests.

**Response:**
```json
[
  { "id": 12, "purpose": "Two-day drone workshop", "status": "pending", "created_at": "2026-08-29T10:00:00" }
]
```

---

### `GET /api/approvals/action?token=<uuid>&action=approve|reject`

**This is what the email link hits.** No auth.

**If `action=approve`:** mark node approved, set `completed_at`, log event, call `activate_next_nodes()`.
```json
{ "message": "Approved successfully. Thank you." }
```

**If `action=reject`:** don't reject yet — return the info the frontend needs to show a reason form.
```json
{
  "requires_reason": true,
  "token": "abc-123",
  "label": "Dean of Student Affairs",
  "purpose": "Two-day drone workshop"
}
```

**If the token is invalid or already used:**
```json
{ "message": "This request has already been approved" }
```
(or 404 if the token doesn't exist at all)

---

### `POST /api/approvals/reject?token=<uuid>`

**Body:** `{ "reason": "Budget breakdown not provided" }`

Mark node rejected, mark the whole request rejected, log the event, email the applicant with the reason.

```json
{ "message": "Rejection recorded. Applicant has been notified." }
```

---

### `POST /api/policies/upload`

**Auth:** `x-admin-password` header
**Body:** multipart — `file` (PDF) + `name` (string)

Save the file, create a `policies` row, then call A's `ingest_policy()`.

```json
{ "id": 3, "name": "Finance Policy", "message": "Policy ingested successfully" }
```

---

### `GET /api/policies/`
**Auth:** admin
```json
[{ "id": 3, "name": "Finance Policy", "uploaded_at": "2026-08-29T09:00:00" }]
```

---

### `POST /api/policies/diff?old_policy_id=1&new_policy_id=4`
**Auth:** admin

Load chunks for both, call A's `detect_policy_diff()`, return it as-is.

---

### `POST /api/policies/{id}/publish`
**Auth:** admin

Set `is_active = true`, log `POLICY_PUBLISHED`.

---

### `GET /api/policies/contacts` / `POST /api/policies/contacts`
**Auth:** admin

GET returns the role→email list. POST body: `{ role, label, email }` — upsert by role.

---

## Reminder job

A function that finds nodes where `status = active` AND `activated_at < now - 24h` AND `reminder_sent_at IS NULL`, sends a reminder to each, and sets `reminder_sent_at`.

For the hackathon, expose it as a `POST /api/admin/send-reminders` endpoint you can hit manually, or run it with FastAPI's `BackgroundTasks` on a loop. Don't bother with Celery.

---

## Mocking Person A

Until A hands over real functions, create `services/llm_mock.py` with functions matching the same signatures that return hardcoded dicts for the Robotics Club scenario. Import from the mock, then change one import line when A is ready.

This is what lets you finish the entire API before the AI engine exists.

---

## How to test without the frontend

Use the auto-generated docs at `http://localhost:8000/docs`. FastAPI gives you a full interactive UI for free.

For endpoints needing a Google token, temporarily make `get_current_user` return a hardcoded email while developing. Remember to switch it back.

---

## Your definition of done

- [ ] All 7 tables created via Alembic migration
- [ ] pgvector extension enabled
- [ ] Every endpoint above returns the exact documented shape
- [ ] Google token verification works and blocks non-institutional emails
- [ ] Admin password check works
- [ ] `activate_next_nodes` correctly handles parallel nodes (test with 2 nodes at the same order_index)
- [ ] Approval emails actually arrive in an inbox
- [ ] Approving via the email link advances the workflow
- [ ] Rejecting notifies the applicant
- [ ] Seed script loads the 7 approver contacts
