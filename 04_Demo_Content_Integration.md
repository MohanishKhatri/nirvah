# Workstream D — Demo Content, Integration & Deployment

**Owner:** Person D
**Branch:** `feature/demo-content`
**Depends on:** nothing — start immediately
**Blocks:** Person A needs your policy PDFs to test ingestion, so **do these first**

You have the least glamorous job and the one most likely to save the demo.

---

## Priority 1 — Policy PDFs (do this in the first 2 hours)

Person A cannot test anything until these exist. Four documents.

**Write them yourself.** Don't hunt for real NITK policies — real institutional documents are badly formatted, full of irrelevant sections, and will make your retrieval look worse than it is. Write clean documents that read like real policy but are structured for good chunking.

### What makes a good demo policy document

- Numbered sections with clear headings (`§8.2 Expenditure Approval Thresholds`)
- One rule per paragraph — don't bury three thresholds in one block of text
- Explicit numbers, not vague language: *"exceeding ₹25,000"* not *"substantial expenditure"*
- Name the approving authority explicitly: *"requires approval from the Dean of Student Affairs"*
- 3-5 pages each. Long enough to be credible, short enough to ingest fast.

### The four documents

**1. Student Activity Policy**
- §3 — All student club events require Faculty Advisor approval, followed by HOD approval
- §4 — Clubs must have a registered faculty advisor on record
- §5 — Events running more than one day require additional documentation

**2. Finance Policy**
- §5.1 — All requests involving expenditure route through the Finance Office
- §8.2 — Student activity expenditure exceeding ₹25,000 requires Dean of Student Affairs approval
- §8.3 — Procurement exceeding ₹25,000 requires Dean approval
- §9.1 — Three vendor quotations required for purchases above ₹50,000

**3. Security Guidelines**
- §4.1 — Events with external speakers or guests require Security Office clearance
- §4.2 — External guest identity details must be recorded and retained
- §5.1 — Events exceeding 500 attendees require additional security deployment

**4. Venue Policy**
- §2.3 — Events with more than 100 attendees require Venue Office approval
- §2.4 — Seminar Hall 2 has a maximum capacity of 200
- §3.1 — Venue bookings must be made at least seven days in advance

### Plus one circular (for the policy-change demo)

**Finance Circular 14/2026**
One page. §3.1 — *"Effective immediately, purchases exceeding ₹50,000 shall additionally require approval from the Registrar."*

Keep this one separate. You upload it live during the demo.

### How to produce them

Write in Google Docs or Word → export to PDF. Real text, not scanned images — `pdfplumber` can't read scans.

Put them in `seed/policies/` and commit them. **Tell Person A the moment they're ready.**

---

## Priority 2 — Seed script

`seed/seed.py`. Needs to load the approver contacts:

```
faculty_advisor  Faculty Advisor              faculty@college.edu
hod              Head of Department           hod@college.edu
dean             Dean of Student Affairs      dean@college.edu
security         Security Office              security@college.edu
venue            Venue Office                 venues@college.edu
finance          Finance Office               finance@college.edu
registrar        Registrar                    registrar@college.edu
```

**Important:** use email addresses your team actually controls for the demo. Set them all to variations of a team member's Gmail (`yourname+dean@gmail.com`, `yourname+hod@gmail.com` — Gmail routes all `+suffix` addresses to the same inbox). This way you can actually show the approval email arriving and click it live.

The `role` keys must exactly match what Person A's LLM returns in the workflow object. Coordinate with A on this list — if the LLM invents `dean_student_affairs` and your contacts table says `dean`, emails silently fail to send.

---

## Priority 3 — API keys

Get all three, put them in a pinned team message. Don't have four people each creating their own.

| Service | URL | What you get |
|---|---|---|
| Gemini | aistudio.google.com | `GEMINI_API_KEY` |
| Resend | resend.com | `RESEND_API_KEY` |
| Google OAuth | console.cloud.google.com | `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` |

**Resend note:** on the free tier without a verified domain you can only send to your own verified email address. For the demo this is fine — that's exactly what the `+suffix` trick above is for. If you want to send to arbitrary addresses you'd need to verify a domain, which isn't worth the time.

---

## Priority 4 — Integration testing

Once A, B and C have merged, you're the one who runs the whole thing end to end and finds what's broken.

**The full path:**
```
1. Admin uploads all 4 policy PDFs                    → chunks appear in DB?
2. Student signs in with institutional Google account  → non-institutional blocked?
3. Student submits the Robotics Club sentence          → correct fields extracted?
4. NIRVAH asks for missing info                        → questions sensible?
5. Student answers                                     → workflow compiles?
6. Tracking page shows the DAG                         → 6 nodes, parallel pair correct?
7. Click Dean node                                     → shows Finance Policy §8.2?
8. Check inbox                                         → Faculty Advisor email arrived?
9. Click Approve in the email                          → node turns green?
10. Tracking page updates                              → HOD now active?
11. Click Reject on a later node                       → reason form appears?
12. Submit rejection                                   → applicant gets notified?
13. Admin uploads Finance Circular 14/2026             → diff detected?
14. Diff shows the new Registrar rule                  → correct?
```

Run this list. Write down every failure with the step number. Give the list to whoever owns that piece.

**Run it again after every fix.** Things that worked at hour 12 break at hour 18.

---

## Priority 5 — Demo seeding

The night before judging, get the database into the exact state you want to start the demo from.

**Scenario 1 — pre-seeded, mid-flight**
The Robotics Club request should already exist with Faculty Advisor and HOD approved, Security and Venue active. You start the demo by showing the tracking page — it already looks alive.

**Scenario 2 — pre-seeded, ready to change**
A ₹68,000 GPU procurement request with workflow `HOD → Finance → Dean`, currently pending. This is what the circular upload will modify.

Write a `seed/demo_scenarios.py` that creates both states directly in the DB. Don't create them by running the live flow — you want deterministic state you can reset to.

**Add a reset command.** You will need to re-run the demo. Make it one command to wipe and re-seed.

---

## Priority 6 — Deployment (optional, only if time permits)

If everything works locally by hour 18, deploying takes about an hour and makes the demo more credible.

| Piece | Where | Notes |
|---|---|---|
| Frontend | Vercel | Connect the repo, set env vars, done |
| Backend | Railway or Render | Both have free tiers, deploy from repo |
| Database | Railway PostgreSQL | Needs the pgvector extension — Railway supports it |

Update `NEXTAUTH_URL`, `FRONTEND_URL`, and the Google OAuth redirect URI to the deployed domains.

**If you don't deploy:** use `ngrok http 8000` during the demo so the email approval links actually resolve. Test this beforehand — ngrok URLs change every restart, so you'll need to update `FRONTEND_URL` and restart the backend.

---

## Priority 7 — Demo run-through

Do this at least 5 times before judging. Time it. You likely have 5-8 minutes.

**Suggested flow (6 minutes):**

| Time | What |
|---|---|
| 0:00 | Show 4 policy PDFs. *"How does a student know which parts of these apply to one request?"* |
| 0:45 | Open NIRVAH, type the Robotics Club sentence |
| 1:15 | NIRVAH asks the follow-up questions, you answer |
| 1:45 | Workflow appears — walk through the chain |
| 2:15 | **Click the Dean node** — show the policy proof. Pause here. This is the moment. |
| 2:45 | Show the approval email on a phone. Click Approve. Show the node turning green. |
| 3:30 | Switch to admin. Upload Finance Circular 14/2026. |
| 4:00 | Show the diff — new Registrar rule detected |
| 4:30 | Show the ₹68,000 workflow gaining a Registrar node |
| 5:00 | Close: *"When policy changes, NIRVAH recompiles the workflow."* |
| 5:30 | Questions |

**Assign who says what.** Don't figure this out live.

---

## Your definition of done

- [ ] 4 policy PDFs written, exported, committed to `seed/policies/`
- [ ] Person A confirmed they can ingest them successfully
- [ ] Finance Circular 14/2026 written and held back for the live demo
- [ ] All 3 API keys obtained and shared with the team
- [ ] Approver contacts seeded with email addresses you control
- [ ] Full 14-step integration checklist passes
- [ ] Both demo scenarios seeded and resettable with one command
- [ ] Demo run-through completed 5 times, under time
- [ ] Speaking parts assigned

---

## The thing to remember

Everyone else is building features. You're the only person whose job is *making sure it actually works when it matters*. If A, B and C each have something 90% working, the demo fails — and you're the one who'll find that out at hour 20 if you're not testing continuously from hour 8.

Start integration testing early and repeatedly. Don't wait for things to be finished.
