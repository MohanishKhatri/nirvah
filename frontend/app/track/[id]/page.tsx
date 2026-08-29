"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import StatusBadge from "@/components/StatusBadge";
import { getWorkflow } from "@/lib/api";
import { useIdentity } from "@/lib/useIdentity";
import type { StructuredFields, WorkflowResponse } from "@/types";

const WorkflowDAG = dynamic(() => import("@/components/WorkflowDAG"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[520px] items-center justify-center rounded-xl border border-line bg-surface text-sm text-muted">
      Rendering approval chain…
    </div>
  ),
});

const POLL_MS = 15000;

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (key === "budget" && typeof value === "number") return `₹${value.toLocaleString("en-IN")}`;
  if (key === "duration_days") return `${value} day${Number(value) === 1 ? "" : "s"}`;
  if (typeof value === "string") return value.replace(/_/g, " ");
  return String(value);
}

const SUMMARY_KEYS: { key: keyof StructuredFields; label: string }[] = [
  { key: "category", label: "Category" },
  { key: "budget", label: "Budget" },
  { key: "attendees", label: "Attendees" },
  { key: "external_speakers", label: "External speakers" },
  { key: "venue", label: "Venue" },
  { key: "club_name", label: "Club" },
  { key: "duration_days", label: "Duration" },
  { key: "item_description", label: "Item" },
];

export default function TrackPage() {
  const params = useParams<{ id: string }>();
  const requestId = Number(params.id);
  const { ready, authed, idToken } = useIdentity();

  const [data, setData] = useState<WorkflowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await getWorkflow(requestId, idToken);
      setData(res);
      setLastUpdated(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this request.");
    }
  }, [requestId, idToken]);

  useEffect(() => {
    if (!ready || !authed) return;
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [ready, authed, load]);

  if (ready && !authed) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6">
        <p className="text-sm text-muted">Sign in to view this request.</p>
        <Link href="/" className="btn-primary">
          Go to sign in
        </Link>
      </main>
    );
  }

  const activeNodes = data?.nodes.filter((n) => n.status === "active") ?? [];
  const rejectedNode = data?.nodes.find((n) => n.status === "rejected");
  const summary = SUMMARY_KEYS.filter(({ key }) => {
    const v = data?.structured_fields?.[key];
    return v !== null && v !== undefined && v !== "";
  });

  return (
    <main className="mx-auto min-h-screen w-full max-w-4xl px-6 py-8">
      <div className="flex items-center justify-between">
        <Link href="/" className="text-xs text-muted hover:text-body">
          ← All requests
        </Link>
        <span className="text-sm font-semibold tracking-[0.2em]">NIRVAH</span>
      </div>

      {error && <p className="card mt-6 text-sm text-danger">{error}</p>}

      {!data && !error && <p className="mt-8 text-sm text-muted">Loading request…</p>}

      {data && (
        <>
          <header className="mt-6 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold leading-tight text-body">
                {data.structured_fields?.purpose ?? `Request #${data.request_id}`}
              </h1>
              <p className="mt-1 text-xs text-muted">
                Request #{data.request_id}
                {lastUpdated && ` · updated ${lastUpdated.toLocaleTimeString()}`}
              </p>
            </div>
            <StatusBadge status={data.status} />
          </header>

          {summary.length > 0 && (
            <section className="card mt-6">
              <h2 className="label">Request summary</h2>
              <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
                {summary.map(({ key, label }) => (
                  <div key={String(key)}>
                    <dt className="text-[11px] uppercase tracking-wider text-muted">{label}</dt>
                    <dd className="mt-1 text-sm capitalize text-body">
                      {formatValue(String(key), data.structured_fields[key])}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          {data.status === "pending" && activeNodes.length > 0 && (
            <div className="mt-6 rounded-xl border border-amber bg-[#1A120066] px-5 py-4">
              <p className="text-sm font-medium text-amber">
                Waiting on: {activeNodes.map((n) => n.label).join(" and ")}
              </p>
              <p className="mt-1 text-xs text-muted">
                {activeNodes.length > 1
                  ? "These approvals run in parallel — the chain advances once both respond. "
                  : ""}
                A reminder email goes out automatically if there is no response within 24 hours.
              </p>
            </div>
          )}

          {rejectedNode && (
            <div className="mt-6 rounded-xl border border-danger bg-[#450A0A44] px-5 py-4">
              <p className="text-sm font-medium text-danger">
                Rejected by {rejectedNode.label}
              </p>
              <p className="mt-1 text-xs text-muted">
                You can revise the request and submit it again.
              </p>
            </div>
          )}

          {data.status === "approved" && (
            <div className="mt-6 rounded-xl border border-success bg-[#14532D33] px-5 py-4">
              <p className="text-sm font-medium text-success">
                Fully approved — every required approver has signed off.
              </p>
            </div>
          )}

          <section className="mt-8">
            <h2 className="label">Approval chain</h2>
            <div className="mt-2">
              <WorkflowDAG nodes={data.nodes} />
            </div>
          </section>
        </>
      )}
    </main>
  );
}
