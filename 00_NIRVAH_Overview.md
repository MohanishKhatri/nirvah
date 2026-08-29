# NIRVAH — Project Overview & Team Coordination

**Read this first. Everyone.** Then read your own module doc.

---

## What we're building

A student types what they need in plain English. NIRVAH reads the institution's policy PDFs, asks follow-up questions if information is missing, generates the exact approval chain required by policy, and emails each approver a one-click approve/reject link. Every approval step is traceable back to the policy clause that created it.

There are **no pre-built workflows**. The workflow is generated fresh for each request based on what the policies say.

---

## Design decisions (locked — don't relitigate these mid-build)

| Area | Decision |
|---|---|
| Request flow | Chat-style. NIRVAH asks one missing question at a time. |
| Student login | Google SSO, restricted to institutional email domain |
| Admin login | Separate `/admin` page, single hardcoded password |
| Approver flow | Email link → minimal standalone page → Approve, or Reject with a reason |
| Approver identity | Fixed role→email map in DB, managed in admin panel. No approver accounts. |
| Rejection | Goes back to applicant with the reason. They can fix and resubmit. |
| Bottleneck handling | Auto reminder email after 24h. Student's tracking page shows where it's stuck. |
| Tracking view | Visual DAG. Click a node → see why it exists. |
| Policy change | Admin reviews the diff and clicks publish. Nothing auto-applies. |
| Scope | Student requests only. Faculty/staff is future scope. |

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind | Fast to build, good defaults |
| Graph rendering | React Flow + dagre | Renders DAGs, handles auto-layout |
| Backend | FastAPI (Python) | Async, clean, good for AI pipelines |
| Database | PostgreSQL 16 + pgvector | Needs vector search for policy retrieval |
| LLM + embeddings | Google Gemini 1.5 Flash | Free, no card, generous limits |
| Email | Resend | Free tier 3000/month, simple API |
| Student auth | NextAuth + Google provider | 30 min setup |

---

## The four independent workstreams

The whole point of this split is that **nobody blocks anybody**. Each person builds against a fixed contract.

```
┌─────────────────────────────────────────────────────────────┐
│  A — AI / Policy Engine                                     │
│  Pure Python functions. No web framework. No database.      │
│  Input: text and dicts. Output: dicts.                      │
│  Testable standalone with a script.                         │
└─────────────────────────────────────────────────────────────┘
                          ↓ provides functions to
┌─────────────────────────────────────────────────────────────┐
│  B — API / Database / Email                                 │
│  DB schema, all endpoints, email sending, workflow state.   │
│  Imports A's functions. Mocks them until A is ready.        │
└─────────────────────────────────────────────────────────────┘
                          ↓ provides JSON to
┌─────────────────────────────────────────────────────────────┐
│  C — Frontend                                               │
│  All pages and components. Builds against mock JSON until   │
│  B's endpoints exist. Never blocked.                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  D — Demo Content / Integration / Deploy                    │
│  Policy PDFs, seed script, end-to-end testing, deployment.  │
│  Starts immediately — A needs the PDFs to test.             │
└─────────────────────────────────────────────────────────────┘
```

---

## The contracts — this is what makes independence work

These are the **only** things the four workstreams need to agree on. Once these are fixed, everyone builds in isolation.

### Contract 1 — Structured Request Object

Produced by A, stored by B, displayed by C.

```
{
  category:          string   // student_event | procurement | course_action |
                              // travel | facility_booking | other
  purpose:           string   // one-line summary
  budget:            number | null
  attendees:         number | null
  external_speakers: number | null
  venue:             string | null
  club_name:         string | null
  duration_days:     number | null
  item_description:  string | null
  missing_fields:    string[]  // field names still needed
}
```

### Contract 2 — Compiled Workflow Object

Produced by A, stored as DB rows by B, rendered as a graph by C.

```
{
  approvals: [
    {
      role:            string        // dean | hod | security | venue |
                                     // finance | registrar | faculty_advisor
      label:           string        // "Dean of Student Affairs"
      reason:          string        // "Budget ₹35,000 exceeds ₹25,000 threshold"
      source_doc:      string        // "Finance Policy"
      source_section:  string | null // "§8.2"
      parallel_group:  string | null // nodes sharing this run simultaneously
      order:           number        // lower = earlier. same = parallel.
    }
  ],
  missing_docs:     string[],   // documents applicant must upload
  immediate_blocks: string[]    // policy violations that kill the request
}
```

### Contract 3 — API Endpoints

Full request/response shapes are in `02_Backend_API.md`. C builds against these. B implements them.

```
POST   /api/requests/                  Submit request text
POST   /api/requests/{id}/answer       Answer a follow-up question
GET    /api/requests/{id}/workflow     Get full DAG + status
GET    /api/requests/                  List my requests

GET    /api/approvals/action           Email link lands here (token in query)
POST   /api/approvals/reject           Submit rejection with reason

POST   /api/policies/upload            Upload + ingest a policy PDF
GET    /api/policies/                  List policies
POST   /api/policies/diff              Compare two policy versions
POST   /api/policies/{id}/publish      Make a version live
GET    /api/policies/contacts          List role→email map
POST   /api/policies/contacts          Add/update a role→email
```

### Contract 4 — Node Status Values

```
blocked   — not reached yet in the chain
active    — waiting on this approver right now
approved  — this approver said yes
rejected  — this approver said no
```

### Contract 5 — Request Status Values

```
draft          — just created
awaiting_info  — NIRVAH is asking follow-up questions
compiling      — running policy retrieval + workflow generation
pending        — workflow live, waiting on approvals
approved       — all nodes approved
rejected       — an approver rejected it
```

---

## Repository setup — do this together, once, at the start

```bash
mkdir nirvah && cd nirvah
git init

mkdir -p backend/app/{routers,services} frontend seed/policies
touch backend/app/__init__.py

# docker-compose.yml for the database
# (contents in 02_Backend_API.md)

docker-compose up -d

cd backend && python -m venv .venv && source .venv/bin/activate
# install deps — list in 02_Backend_API.md
cd ..

npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir --eslint

cat > .gitignore << 'GIT'
.env
.env.local
.venv
node_modules
__pycache__
*.pyc
.next
uploads/
GIT

git add . && git commit -m "chore: init repo structure"
```

**Branch strategy:** Everyone works on `feature/<their-area>`. Merge to `main` at least twice a day so integration problems surface early, not at hour 20.

```
feature/ai-engine       → Person A
feature/api             → Person B
feature/frontend        → Person C
feature/demo-content    → Person D
```

---

## API keys needed — get these in the first 15 minutes

| Service | For | Where | Cost |
|---|---|---|---|
| Google Gemini | LLM + embeddings | aistudio.google.com | Free, no card |
| Resend | Approval emails | resend.com | Free, 3000/mo |
| Google OAuth | Student login | console.cloud.google.com | Free |

Person D should get all three and share them in a pinned message. Don't have four people each making their own keys.

---

## Build sequence

**Hour 0-1 — Everyone together**
- Repo created, structure committed, everyone can clone and run
- API keys obtained and shared
- Everyone reads the contracts above and confirms understanding
- Split confirmed, branches created

**Hour 1-8 — Parallel independent work**
- A: builds and tests the AI functions standalone
- B: DB schema + endpoints with A's functions mocked
- C: all pages built against hardcoded mock JSON
- D: creates demo policy PDFs, writes seed script

**Hour 8-12 — First integration**
- A hands real functions to B, B removes mocks
- B deploys API locally, C points frontend at it, removes mocks
- Full flow tested: submit request → workflow appears

**Hour 12-18 — Email + policy change**
- B wires up Resend, approval emails send
- C builds the approve page
- A builds the policy diff function
- Test approving from an actual email

**Hour 18-22 — Demo prep**
- D seeds both demo scenarios
- Full run-through 5 times
- Fix whatever breaks
- Broken/unfinished routes hidden

**Hour 22-24 — Buffer**
Do not schedule work here. This is for the things that will inevitably go wrong.

---

## The two demo scenarios — these must be flawless

**Scenario 1 — Robotics Club Workshop**

Input: *"Our Robotics Club wants a two-day drone workshop for 120 students, ₹35,000 funding and 3 external speakers in Seminar Hall 2."*

Expected workflow: `Faculty Advisor → HOD → [Security + Venue in parallel] → Finance → Dean`

The moment that lands: judge clicks the Dean node and sees *"Budget ₹35,000 exceeds ₹25,000 threshold — Finance Policy §8.2"*

**Scenario 2 — Live policy change**

Admin uploads a circular saying purchases above ₹50,000 now need Registrar approval. The existing ₹68,000 GPU procurement workflow gains a Registrar node.

The moment that lands: before/after workflows shown side by side, new node highlighted.

**Pre-seed both.** Scenario 1 should already be mid-flight (Faculty Advisor approved, HOD active) when you start the demo. Running the full flow live from zero during judging is asking for trouble.

---

## What judges actually care about

1. The DAG appears and the approval chain makes sense
2. Clicking a node shows exactly why it's there, with the policy citation
3. Uploading a new circular visibly changes an existing workflow
4. The Dean approves in one click from an email without any login

Everything else is secondary. If you're running out of time, cut features — not these four.

---

## Things that will go wrong (plan for them)

| Problem | Mitigation |
|---|---|
| Gemini returns malformed JSON | A wraps every call in try/except with a safe fallback |
| Vector search returns irrelevant chunks | D writes clearly-worded policy PDFs; A tunes chunk size |
| LLM takes 5+ seconds | Cache demo scenario results in DB ahead of time |
| Email links don't work on localhost | Use ngrok to expose the backend, or demo via the DB directly |
| React Flow layout looks bad | C uses dagre auto-layout, doesn't manually position |
| Integration breaks at hour 20 | Merge to main twice daily from hour 1 |
