# NIRVAH

A student describes what they need in plain English. NIRVAH reads the institution's policy
documents, asks for whatever is missing, generates the exact approval chain those policies
require, and emails each approver a one-click approve/reject link. Every step traces back to the
clause that created it.

There are no pre-built workflows. Each one is compiled per request from the policy text.

```
frontend/   Next.js 14 + Tailwind + React Flow   — pages, DAG, admin panel
backend/    FastAPI + SQLAlchemy                 — API, workflow state machine, email
  app/services/llm.py         Gemini calls, each with a safe fallback
  app/services/embeddings.py  PDF parsing, chunking, embedding, retrieval
  app/services/workflow.py    tier activation, approval, rejection, recompile
seed/       policy documents, PDF renderer, seed + demo scenario scripts
```

## Quick start

Two terminals.

```bash
# backend — http://localhost:8000
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
# frontend — http://localhost:3000
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Then seed the demo data (repo root, backend venv active):

```bash
python seed/make_pdfs.py
python seed/seed.py --reset
python seed/demo_scenarios.py --reset
```

Set `NEXT_PUBLIC_USE_MOCKS=false` in `frontend/.env.local` to run against the live API. With it
left at `true` the frontend serves fixtures from `lib/mockData.ts` and needs no backend at all.

Neither a Gemini key nor a Resend key is required to run the whole product: the policy engine
falls back to a deterministic rule compiler that mirrors the seeded policies, and emails are
logged with their approval links instead of being sent.

## What the demo shows

1. **Chat submission** — type the Robotics Club sentence, answer the follow-up questions.
2. **The DAG** — `Faculty Advisor → HOD → [Security ∥ Venue] → Finance → Dean`, laid out with dagre.
3. **Policy proof** — click the Dean node: *"Budget ₹35,000 exceeds the ₹25,000 threshold — Finance Policy §8.2"*.
4. **One-click approval** — the emailed link opens `/approve/<token>`; no login, and the node turns green.
5. **Live policy change** — upload `Finance Circular 14/2026` in the admin panel, run the diff, then
   *Recompile pending workflows*: the ₹68,000 GPU request gains a Registrar node.

Both scenarios are pre-seeded by `seed/demo_scenarios.py`, so the demo starts from a workflow that
already looks alive rather than from an empty screen.

## Contracts

The frontend, API and policy engine agree on four shapes — the structured request object, the
compiled workflow object, node status (`blocked` / `active` / `approved` / `rejected`) and request
status (`draft` / `awaiting_info` / `compiling` / `pending` / `approved` / `rejected`). They are
documented in `00_NIRVAH_Overview.md`, mirrored in `frontend/types/index.ts` and enforced by
`backend/app/schemas.py`.

Per-area detail: [`frontend/README.md`](frontend/README.md) and [`backend/README.md`](backend/README.md).
