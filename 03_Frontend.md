# Workstream C — Frontend

**Owner:** Person C
**Branch:** `feature/frontend`
**Depends on:** the API spec in `02_Backend_API.md` — not on B's implementation
**Blocks:** nobody

---

## What you're building

Five pages and four components. Build the entire thing against mock JSON first, then flip to the real API by changing one env var.

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                       ← home
│   ├── api/auth/[...nextauth]/route.ts
│   ├── request/page.tsx               ← chat submission
│   ├── track/[id]/page.tsx            ← DAG tracking
│   ├── approve/[token]/page.tsx       ← approver page (no login)
│   └── admin/page.tsx
├── components/
│   ├── Providers.tsx
│   ├── WorkflowDAG.tsx
│   ├── PolicyProofPanel.tsx
│   └── StatusBadge.tsx
├── lib/
│   ├── api.ts
│   ├── auth.ts
│   └── mockData.ts                    ← delete once integrated
└── types/index.ts
```

---

## Setup

```bash
npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir --eslint
cd frontend
npm install reactflow dagre @dagrejs/dagre next-auth
npm install -D @types/dagre
```

**.env.local:**
```
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<openssl rand -base64 32>
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_ALLOWED_DOMAIN=college.edu
NEXT_PUBLIC_USE_MOCKS=true          ← flip to false when B is ready
```

---

## Visual direction

Match the pitch deck so the demo feels cohesive.

```
Background       #07080C   near-black
Card surface     #111318
Card border      #252A36
Accent (amber)   #F0C040   primary actions, active states
Accent (orange)  #E05C30   warnings, parallel indicators
Success green    #3EC97A   approved states
Body text        #E8EAF0
Muted text       #6B7280
```

Rounded corners (`rounded-xl`), generous padding, no gradients, no shadows. Clean and dark.

---

## Google OAuth setup (do this first, 10 minutes)

1. console.cloud.google.com → new project
2. APIs & Services → OAuth consent screen → External → fill in name
3. Credentials → Create OAuth Client ID → Web application
4. Authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
5. Copy client ID + secret into `.env.local`

**In your NextAuth config**, two things matter:
- The `signIn` callback must return `false` if the email doesn't end with your allowed domain — this is the institutional restriction
- The `jwt` and `session` callbacks must pass `account.id_token` through into the session, because that's the token you send to the backend as `Authorization: Bearer <token>`

---

## `lib/api.ts` — the API layer

One file, all fetch calls. Every student-facing call takes an `idToken` param and sets `Authorization: Bearer ${idToken}`.

Admin calls read the password from `sessionStorage` and send it as `x-admin-password`.

Wrap everything so a non-2xx response throws with the backend's `detail` message.

Functions you need:
```
submitRequest(text, idToken)
answerQuestion(requestId, field, value, idToken)
getWorkflow(requestId, idToken)
getMyRequests(idToken)
handleApprovalAction(token, action)       // no auth
submitRejection(token, reason)            // no auth
uploadPolicy(file, name)                  // admin, multipart
getPolicies() / getContacts() / upsertContact(...)  // admin
```

**Mock mode:** at the top of each function, if `NEXT_PUBLIC_USE_MOCKS === "true"`, return the corresponding fixture from `mockData.ts` after a fake 500ms delay. This is what unblocks you.

---

## Page 1 — Home (`app/page.tsx`)

**Logged out:** NIRVAH wordmark, one-line description, "Sign in with Google" button, small "Admin panel" link at the bottom.

**Logged in:** header with email + sign out, a large "New Request" button, and below it a list of the student's past requests. Each row shows the purpose, date, and a status badge. Clicking a row goes to `/track/{id}`.

Status badge colours: approved→green, rejected→red, pending→amber, awaiting_info→blue.

---

## Page 2 — Request submission (`app/request/page.tsx`)

**The chat interface.** This is the most important UX in the app.

State you need:
```
messages       — array of {role: "user"|"assistant", text}
input          — current textarea value
loading        — showing "Thinking..."
requestId      — null on first message, set after
askingFor      — which field the current question is asking about
```

**Flow:**
1. Start with one assistant message: *"What do you need help with? Describe your request in plain language."*
2. On first send → call `submitRequest(text)` → store the returned `request_id`
3. On subsequent sends → call `answerQuestion(requestId, askingFor, text)`
4. If response has `status: "awaiting_info"` → append the `question` as an assistant message, store `asking_for`
5. If response has `immediate_blocks` → show them as an assistant message explaining the request can't proceed
6. If `workflow_compiled: true` → show a success message, then `router.push('/track/{id}')` after ~1.5s

**Visual:** user messages right-aligned in amber, assistant messages left-aligned in dark cards. Auto-scroll to bottom on new message. Enter to send.

---

## Page 3 — Tracking (`app/track/[id]/page.tsx`)

Calls `getWorkflow(id)` on mount and **polls every 15 seconds** so approvals appearing in real time are picked up.

Layout top to bottom:
1. Back link
2. Purpose as the page title + request ID + status chip
3. Summary card — grid of budget / attendees / venue / category (only render fields that exist)
4. **Bottleneck banner** — if status is `pending` and there's an `active` node, show an amber banner: *"Waiting on: {label}"* plus a note that a reminder goes out after 24h
5. The DAG (see component below)

---

## Component — `WorkflowDAG.tsx`

**This is the demo centrepiece.** Budget real time for it.

Takes `nodes: WorkflowNode[]`, renders a React Flow graph.

**Building the graph:**

Nodes are laid out with dagre — never position manually.

```
const g = new dagre.graphlib.Graph()
g.setGraph({ rankdir: "TB", ranksep: 60, nodesep: 40 })
```

**Edge derivation** — this is the bit that needs thought. Your nodes have `order_index`, not explicit edges. Build edges by:
1. Get the sorted unique list of `order_index` values
2. For each consecutive pair of tiers, connect every node in tier N to every node in tier N+1

So if tier 3 has Security and Venue (parallel) and tier 4 has Finance, you get two edges converging on Finance. That's exactly the visual you want.

**Node colours by status:**
```
approved  bg #14532d  border #4ade80  text #4ade80
active    bg #1a1200  border #F0C040  text #F0C040
rejected  bg #450a0a  border #ef4444  text #ef4444
blocked   bg #151920  border #2E3545  text #6B7280
```

**On node click** → set selected node → render `PolicyProofPanel` below the graph.

Add `<Background color="#252A36" gap={24} />` and `<Controls />`. Set `fitView`. Add a small hint below: *"Click any node to see why it is required"*.

---

## Component — `PolicyProofPanel.tsx`

Appears below the graph when a node is clicked. This is the moment judges care about.

Shows as labelled rows:
- **Status** — with a symbol: ✓ Approved / ⏳ Awaiting Response / ○ Not yet reached / ✗ Rejected
- **Why** — the node's `reason`
- **Source** — `{source_doc} {source_section}` — render this in amber, it's the payoff
- **Runs in parallel with** — only if `parallel_group` is set
- **Activated / Completed** — timestamps if present

Close button in the corner.

---

## Page 4 — Approver page (`app/approve/[token]/page.tsx`)

**No login. No NextAuth. Completely standalone.** A Dean opens this from their phone and it must just work.

Reads `token` from the route and `action` from the query string.

**States:**
```
loading         → "Processing..."
done            → big ✓ or ✗, the message from the API, "You may close this tab"
error           → "The link may be invalid or expired"
confirm_reject  → the rejection form
```

**On mount:**
- If `action=approve` → call `handleApprovalAction(token, "approve")` → show the result. One click, done, no confirmation step.
- If `action=reject` → call `handleApprovalAction(token, "reject")` → the API returns `requires_reason: true` plus the label and purpose → show the rejection form

**Rejection form:** shows the request purpose and their role, a textarea for the reason, and a "Confirm Rejection" button that's disabled until they type something. On submit call `submitRejection(token, reason)`.

Keep this page visually simple — one centred card. It should look trustworthy to someone who's never seen NIRVAH before.

---

## Page 5 — Admin (`app/admin/page.tsx`)

Password gate first — a single input, store it in `sessionStorage` on submit, then load data. If the API returns 401, show "Invalid password".

Two tabs.

**Policies tab:**
- Upload form: policy name text input + file picker (accept `.pdf`) + Upload button
- Show "Uploading & ingesting..." while in flight — this takes 10-30s for a real PDF, so the loading state matters
- Below: list of active policies with name and upload date

**Contacts tab:**
- Form with three inputs: role key, display name, email
- Save button that upserts
- Below: list of existing contacts showing `{label}` and `{role} → {email}`

---

## Mock data

Build `lib/mockData.ts` with fixtures for the Robotics Club scenario. You need:

1. **A workflow response** with all 6 nodes — Faculty Advisor (approved), HOD (approved), Security + Venue (both order 3, one active one blocked), Finance (blocked), Dean (blocked). This lets you verify parallel rendering and every status colour.
2. **A follow-up question response** so you can test the chat flow
3. **A completed response** with `workflow_compiled: true`
4. **A policy list** and **contacts list** for the admin page

Getting the mock workflow right matters — if your DAG renders correctly from it, it'll render correctly from the real API.

---

## Your definition of done

- [ ] Google sign-in works, non-institutional emails are rejected
- [ ] Chat flow handles the full loop: submit → question → answer → question → answer → redirect
- [ ] DAG renders with correct edges, including parallel nodes converging
- [ ] All four node status colours visibly distinct
- [ ] Clicking a node shows the policy proof panel with the source citation
- [ ] Tracking page polls and picks up status changes without a manual refresh
- [ ] Approve page works with no login, both approve and reject paths
- [ ] Admin page uploads a file and lists policies
- [ ] Everything readable on a laptop screen at demo resolution
- [ ] `NEXT_PUBLIC_USE_MOCKS=false` works against the real API

---

## Integration checklist

When B says the API is up:
1. Set `NEXT_PUBLIC_USE_MOCKS=false`
2. Walk every page and check the shapes match
3. Any mismatch → message B with the endpoint and what you got vs expected. Do not patch around it in the frontend, or you'll be debugging two problems later.
