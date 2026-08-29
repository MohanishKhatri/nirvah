# Workstream A — AI / Policy Engine

**Owner:** Person A
**Branch:** `feature/ai-engine`
**Depends on:** demo policy PDFs from Person D (for testing)
**Blocks:** nobody — Person B mocks your functions until you're done

---

## What you're building

Pure Python functions. No FastAPI, no database sessions, no HTTP. Just functions that take text/dicts and return dicts. This means you can test everything with a plain script and `print()`.

You own two files:

```
backend/app/services/
├── llm.py           ← all Gemini calls
└── embeddings.py    ← PDF parsing, chunking, vector search
```

---

## Setup

```bash
pip install google-generativeai pdfplumber pgvector sqlalchemy asyncpg
```

Get your Gemini key from **aistudio.google.com** → "Get API Key". Free, no card.

```python
import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")
```

---

## Part 1 — `llm.py`

You need five functions. All of them must **never crash** — wrap everything in try/except with a sensible fallback, because a malformed LLM response should degrade gracefully, not 500 the API.

### Shared helper: JSON parsing

Gemini often wraps JSON in markdown fences even when told not to. Write one helper that strips ` ```json ` and ` ``` ` before calling `json.loads()`. Every function uses it.

---

### Function 1: `extract_intent(request_text) → dict`

Takes the student's raw sentence. Returns the Structured Request Object (Contract 1 in the overview doc).

**Prompt design:**
- Tell it to return ONLY JSON, no markdown, no explanation
- Give it the exact key names and allowed values for `category`
- Ask it to populate `missing_fields` with anything a request of that category would normally need but that isn't stated

**Key judgement call:** the `missing_fields` logic is what drives the whole chat flow. Be thoughtful — for a `student_event`, missing `club_name` matters; for a `procurement`, it doesn't. Let the LLM decide based on category rather than hardcoding.

**Fallback on failure:** return `{category: "other", purpose: <first 200 chars>, missing_fields: ["purpose", "budget"]}`. This keeps the chat flow alive.

---

### Function 2: `generate_followup_question(request_text, missing_field) → str`

Takes the original request and one field name. Returns a single natural-sounding question.

Should feel like a person asking, not a form label. `"What's the name of your club?"` not `"Enter club_name:"`.

**Fallback:** `f"Could you provide your {missing_field.replace('_', ' ')}?"`

---

### Function 3: `compile_workflow(structured_fields, retrieved_chunks) → dict`

**This is the most important function in the project.** Takes the completed request fields plus the policy excerpts your vector search found, returns the Compiled Workflow Object (Contract 2).

**Prompt design:**
- Give it the structured request as formatted JSON
- Give it the retrieved policy chunks, each prefixed with its source document name and section
- Tell it to only create approvals that are actually justified by the provided policy text — no inventing approvers
- Explain `parallel_group`: two approvals that don't depend on each other should share a group name and the same `order` value
- Explain `immediate_blocks`: if the policy says something outright isn't allowed (hall capacity is 500 but they asked for 2500), that goes here and the workflow doesn't get created

**Critical requirement:** every approval must have a `reason`, `source_doc`, and ideally `source_section`. This is the Policy Proof that the demo hinges on. If the LLM returns approvals without citations, tighten the prompt until it does.

**Fallback:** return empty approvals with an `immediate_blocks` entry explaining compilation failed. B will handle this gracefully.

---

### Function 4: `generate_approval_brief(...) → str`

Takes the approver's label, the request fields, the list of already-completed approvals, and this node's reason/source. Returns a 4-6 sentence plain-text paragraph.

This goes in the approval email. It should tell the Dean: what's being asked for, who has already signed off, and precisely why it's now on their desk.

**Fallback:** a generic sentence citing the source policy.

---

### Function 5: `detect_policy_diff(old_chunks, new_chunks) → dict`

Takes two lists of policy text chunks. Returns:

```
{
  changed: [{description, old_text, new_text, impact}],
  added:   [{description, text, impact}],
  removed: [{description, text, impact}]
}
```

Focus the prompt on rules that affect workflows — thresholds, required approvers, conditions. Ignore formatting changes and wording tweaks.

Cap the chunks you send (first 20 of each) so you don't blow the context window.

---

## Part 2 — `embeddings.py`

### Function 1: `extract_text_from_pdf(file_path) → list[{text, page}]`

Use `pdfplumber`. Loop over pages, extract text, skip empty pages. Keep the page number — it's useful for citations later.

### Function 2: `chunk_text(pages, chunk_size=500, overlap=60) → list[{text, page}]`

Split each page's text into overlapping word-count chunks. Overlap matters — a rule that spans a chunk boundary gets lost otherwise.

**Tune this.** Start at 500/60. If retrieval brings back fragments that don't contain complete rules, go bigger. If it brings back too much irrelevant text, go smaller.

### Function 3: `embed_text(text) → list[float]`

```python
genai.embed_content(
    model="models/embedding-001",
    content=text,
    task_type="retrieval_document"   # for storing
)
```

Returns a 768-dimensional vector.

### Function 4: `embed_query(text) → list[float]`

Same, but `task_type="retrieval_query"`. Gemini optimises differently for queries vs documents — using the right one measurably improves retrieval quality.

### Function 5: `ingest_policy(db, policy_id, file_path) → None`

The full pipeline: extract → chunk → embed each chunk → store rows in `policy_chunks`.

Embed calls can fail on weird text. Catch per-chunk and skip rather than aborting the whole ingestion.

### Function 6: `search_relevant_chunks(db, query_text, top_k=8) → list[dict]`

Embed the query, then run a pgvector similarity search:

```sql
SELECT pc.chunk_text, pc.source_section, pc.page_number, p.name as policy_name,
       1 - (pc.embedding <=> :embedding::vector) as similarity
FROM policy_chunks pc
JOIN policies p ON p.id = pc.policy_id
WHERE p.is_active = true
ORDER BY pc.embedding <=> :embedding::vector
LIMIT :top_k
```

`<=>` is pgvector's cosine distance operator. Lower distance = more similar, so `ORDER BY` ascending gives you the best matches.

Return dicts with `chunk_text`, `policy_name`, `source_section`, `similarity`.

---

## How to test without the rest of the app

Write `backend/test_ai.py`:

```
1. Point it at a demo policy PDF
2. Run extract_text_from_pdf → print page count and first 200 chars
3. Run chunk_text → print chunk count and one sample chunk
4. Run embed_text on one chunk → print vector length (should be 768)
5. Run extract_intent on the Robotics Club sentence → print the dict
6. Manually paste 3-4 relevant policy paragraphs into a list
7. Run compile_workflow with those → print the approvals
```

If step 7 produces a sensible approval chain with policy citations, your engine works. Everything after that is plumbing.

---

## Your definition of done

- [ ] All 5 llm.py functions return correct-shaped dicts
- [ ] Every function has a fallback that doesn't crash
- [ ] PDF ingestion works on all 4 demo policies
- [ ] `search_relevant_chunks` on the Robotics Club text returns the finance/security/venue policy chunks (verify by eye)
- [ ] `compile_workflow` produces the expected 6-node chain for Scenario 1
- [ ] Every approval in that chain has a non-null `source_doc`
- [ ] Handed off to Person B with a short note on how to call each function

---

## Tuning notes

**If retrieval returns garbage:** the problem is usually chunking, not embedding. Print what's coming back and check whether the chunks contain complete, coherent rules.

**If the LLM invents approvers:** add to the prompt — *"Only create approvals explicitly supported by the provided policy text. If no policy justifies an approval, do not create it."*

**If citations are missing:** make `source_doc` and `source_section` required in the prompt's JSON schema description, and add an example showing them filled in.

**If it's too slow:** `gemini-1.5-flash` should respond in 1-3s. If it's slower, your prompt is probably too long — trim the retrieved chunks to top 5 instead of 8.
