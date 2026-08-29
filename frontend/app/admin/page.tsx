"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ADMIN_PASSWORD_KEY,
  diffPolicies,
  getContacts,
  getPolicies,
  publishPolicy,
  recompilePending,
  uploadPolicy,
  upsertContact,
} from "@/lib/api";
import type { ApproverContact, Policy, PolicyDiff } from "@/types";

function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function AdminPage() {
  const [unlocked, setUnlocked] = useState(false);
  const [password, setPassword] = useState("");
  const [gateError, setGateError] = useState<string | null>(null);
  const [tab, setTab] = useState<"policies" | "contacts">("policies");

  useEffect(() => {
    if (sessionStorage.getItem(ADMIN_PASSWORD_KEY)) setUnlocked(true);
  }, []);

  async function unlock() {
    sessionStorage.setItem(ADMIN_PASSWORD_KEY, password);
    try {
      await getPolicies();
      setGateError(null);
      setUnlocked(true);
    } catch (e) {
      sessionStorage.removeItem(ADMIN_PASSWORD_KEY);
      const status = (e as { status?: number }).status;
      setGateError(status === 401 || status === 403 ? "Invalid password" : (e as Error).message);
    }
  }

  function lock() {
    sessionStorage.removeItem(ADMIN_PASSWORD_KEY);
    setUnlocked(false);
    setPassword("");
  }

  if (!unlocked) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="w-full max-w-sm">
          <h1 className="text-center text-sm font-semibold tracking-[0.25em] text-muted">
            NIRVAH ADMIN
          </h1>
          <div className="card mt-6">
            <label className="label" htmlFor="admin-password">
              Password
            </label>
            <input
              id="admin-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void unlock()}
              className="input"
              placeholder="••••••••"
            />
            {gateError && <p className="mt-3 text-xs text-danger">{gateError}</p>}
            <button
              onClick={() => void unlock()}
              disabled={password.length === 0}
              className="btn-primary mt-4 w-full"
            >
              Unlock
            </button>
          </div>
          <Link href="/" className="mt-6 block text-center text-xs text-muted hover:text-body">
            ← Back to NIRVAH
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-6 py-8">
      <header className="flex items-center justify-between">
        <Link href="/" className="text-xs text-muted hover:text-body">
          ← Back
        </Link>
        <span className="text-sm font-semibold tracking-[0.2em]">NIRVAH ADMIN</span>
        <button onClick={lock} className="text-xs text-muted hover:text-body">
          Lock
        </button>
      </header>

      <nav className="mt-8 flex gap-2">
        {(["policies", "contacts"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              tab === t
                ? "rounded-xl border border-amber bg-[#1A120066] px-4 py-2 text-sm capitalize text-amber"
                : "rounded-xl border border-line px-4 py-2 text-sm capitalize text-muted hover:text-body"
            }
          >
            {t}
          </button>
        ))}
      </nav>

      <div className="mt-6">{tab === "policies" ? <PoliciesTab /> : <ContactsTab />}</div>
    </main>
  );
}

function PoliciesTab() {
  const [policies, setPolicies] = useState<Policy[] | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [oldId, setOldId] = useState<string>("");
  const [newId, setNewId] = useState<string>("");
  const [diff, setDiff] = useState<PolicyDiff | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);

  const [applyBusy, setApplyBusy] = useState(false);
  const [applied, setApplied] = useState<
    { request_id: number; purpose: string; added: string[]; removed: string[] }[] | null
  >(null);

  const refresh = useCallback(async () => {
    try {
      setPolicies(await getPolicies());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function upload() {
    if (!file || !name.trim()) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await uploadPolicy(file, name.trim());
      setNotice(res.message ?? "Policy ingested successfully");
      setName("");
      setFile(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runDiff() {
    if (!oldId || !newId) return;
    setDiffBusy(true);
    setError(null);
    try {
      setDiff(await diffPolicies(Number(oldId), Number(newId)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDiffBusy(false);
    }
  }

  async function applyToLiveWorkflows() {
    setApplyBusy(true);
    setError(null);
    try {
      const res = await recompilePending();
      setApplied(res.changed);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApplyBusy(false);
    }
  }

  async function publish(id: number) {
    try {
      await publishPolicy(id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <section className="card">
        <h2 className="label">Upload a policy</h2>
        <div className="mt-2 space-y-3">
          <input
            className="input"
            placeholder="Policy name — e.g. Finance Circular 14/2026"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-muted file:mr-4 file:rounded-xl file:border file:border-line file:bg-surface2 file:px-4 file:py-2 file:text-sm file:text-body hover:file:border-line2"
          />
          <button
            onClick={() => void upload()}
            disabled={busy || !file || name.trim().length === 0}
            className="btn-primary"
          >
            {busy ? "Uploading & ingesting…" : "Upload"}
          </button>
          {busy && (
            <p className="text-xs text-muted">
              Parsing, chunking and embedding the document. This can take 10–30 seconds.
            </p>
          )}
          {notice && <p className="text-xs text-success">{notice}</p>}
          {error && <p className="text-xs text-danger">{error}</p>}
        </div>
      </section>

      <section className="card">
        <h2 className="label">Policies</h2>
        {!policies && <p className="mt-2 text-sm text-muted">Loading…</p>}
        {policies?.length === 0 && <p className="mt-2 text-sm text-muted">No policies yet.</p>}
        <ul className="mt-2 divide-y divide-line">
          {policies?.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-4 py-3">
              <span>
                <span className="block text-sm text-body">{p.name}</span>
                <span className="mt-0.5 block text-xs text-muted">
                  #{p.id} · uploaded {formatDate(p.uploaded_at)}
                  {p.version ? ` · v${p.version}` : ""}
                </span>
              </span>
              {p.is_active === false ? (
                <button onClick={() => void publish(p.id)} className="btn-ghost px-3 py-1.5 text-xs">
                  Publish
                </button>
              ) : (
                <span className="text-xs text-success">live</span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2 className="label">Compare versions</h2>
        <p className="mt-1 text-xs text-muted">
          Detect what a new circular changes before it goes live.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <select className="input max-w-[220px]" value={oldId} onChange={(e) => setOldId(e.target.value)}>
            <option value="">Current policy…</option>
            {policies?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted">vs</span>
          <select className="input max-w-[220px]" value={newId} onChange={(e) => setNewId(e.target.value)}>
            <option value="">New policy…</option>
            {policies?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button onClick={() => void runDiff()} disabled={diffBusy || !oldId || !newId} className="btn-ghost">
            {diffBusy ? "Analysing…" : "Show diff"}
          </button>
        </div>

        {diff && (
          <div className="mt-4 space-y-3">
            {diff.added.map((d, i) => (
              <DiffCard key={`a${i}`} tone="#3EC97A" tag="Added" title={d.description} body={d.text} impact={d.impact} />
            ))}
            {diff.changed.map((d, i) => (
              <DiffCard
                key={`c${i}`}
                tone="#F0C040"
                tag="Changed"
                title={d.description}
                body={`Was: ${d.old_text}\nNow: ${d.new_text}`}
                impact={d.impact}
              />
            ))}
            {diff.removed.map((d, i) => (
              <DiffCard key={`r${i}`} tone="#EF4444" tag="Removed" title={d.description} body={d.text} impact={d.impact} />
            ))}
            {diff.added.length + diff.changed.length + diff.removed.length === 0 && (
              <p className="text-sm text-muted">No workflow-affecting changes detected.</p>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="label">Apply to live workflows</h2>
        <p className="mt-1 text-xs text-muted">
          Recompiles every pending request against the published policies. Approvals already given
          are kept.
        </p>
        <button
          onClick={() => void applyToLiveWorkflows()}
          disabled={applyBusy}
          className="btn-primary mt-3"
        >
          {applyBusy ? "Recompiling…" : "Recompile pending workflows"}
        </button>

        {applied && applied.length === 0 && (
          <p className="mt-3 text-sm text-muted">No live workflow changed.</p>
        )}

        {applied && applied.length > 0 && (
          <ul className="mt-3 space-y-2">
            {applied.map((row) => (
              <li key={row.request_id} className="rounded-xl border border-amber bg-[#1A120066] p-4">
                <Link href={`/track/${row.request_id}`} className="text-sm text-body hover:underline">
                  {row.purpose}
                </Link>
                <p className="mt-1 text-xs text-amber">
                  {row.added.length > 0 && `+ ${row.added.join(", ")}`}
                  {row.added.length > 0 && row.removed.length > 0 && " · "}
                  {row.removed.length > 0 && `− ${row.removed.join(", ")}`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function DiffCard({
  tone,
  tag,
  title,
  body,
  impact,
}: {
  tone: string;
  tag: string;
  title: string;
  body: string;
  impact: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface2 p-4">
      <span
        className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
        style={{ borderColor: tone, color: tone }}
      >
        {tag}
      </span>
      <p className="mt-2 text-sm text-body">{title}</p>
      <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{body}</p>
      <p className="mt-2 text-xs" style={{ color: tone }}>
        Impact: {impact}
      </p>
    </div>
  );
}

function ContactsTab() {
  const [contacts, setContacts] = useState<ApproverContact[] | null>(null);
  const [form, setForm] = useState<ApproverContact>({ role: "", label: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setContacts(await getContacts());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await upsertContact({
        role: form.role.trim(),
        label: form.label.trim(),
        email: form.email.trim(),
      });
      setForm({ role: "", label: "", email: "" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const complete = form.role.trim() && form.label.trim() && form.email.trim();

  return (
    <div className="space-y-6">
      <section className="card">
        <h2 className="label">Add or update an approver</h2>
        <p className="mt-1 text-xs text-muted">
          The role key must match what the policy engine emits — <code>dean</code>, not{" "}
          <code>dean_student_affairs</code>.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <input
            className="input"
            placeholder="role key — dean"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
          <input
            className="input"
            placeholder="Display name"
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
          />
          <input
            className="input"
            type="email"
            placeholder="email@nitk.edu.in"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <button onClick={() => void save()} disabled={busy || !complete} className="btn-primary mt-3">
          {busy ? "Saving…" : "Save"}
        </button>
        {error && <p className="mt-3 text-xs text-danger">{error}</p>}
      </section>

      <section className="card">
        <h2 className="label">Approver contacts</h2>
        {!contacts && <p className="mt-2 text-sm text-muted">Loading…</p>}
        <ul className="mt-2 divide-y divide-line">
          {contacts?.map((c) => (
            <li key={c.role} className="flex items-center justify-between gap-4 py-3">
              <span className="text-sm text-body">{c.label}</span>
              <span className="text-xs text-muted">
                <code className="text-body">{c.role}</code> → {c.email}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
