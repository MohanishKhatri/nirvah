"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { handleApprovalAction, submitRejection } from "@/lib/api";

type Phase = "loading" | "done" | "error" | "confirm_reject";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-10">
      <div className="w-full max-w-md rounded-xl border border-line bg-surface p-8">
        <p className="text-center text-sm font-semibold tracking-[0.25em] text-muted">NIRVAH</p>
        <div className="mt-6">{children}</div>
      </div>
    </main>
  );
}

function ApprovePageInner() {
  const params = useParams<{ token: string }>();
  const search = useSearchParams();
  const token = params.token;
  const action = search.get("action") === "reject" ? "reject" : "approve";

  const [phase, setPhase] = useState<Phase>("loading");
  const [message, setMessage] = useState("");
  const [label, setLabel] = useState("");
  const [purpose, setPurpose] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [outcome, setOutcome] = useState<"approved" | "rejected">("approved");

  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    handleApprovalAction(token, action)
      .then((res) => {
        if (res.requires_reason) {
          setLabel(res.label ?? "");
          setPurpose(res.purpose ?? "");
          setPhase("confirm_reject");
          return;
        }
        setOutcome(action === "reject" ? "rejected" : "approved");
        setMessage(res.message ?? "Done.");
        setPhase("done");
      })
      .catch((e: Error) => {
        setMessage(e.message);
        setPhase("error");
      });
  }, [token, action]);

  async function confirmRejection() {
    setSubmitting(true);
    try {
      const res = await submitRejection(token, reason.trim());
      setOutcome("rejected");
      setMessage(res.message ?? "Rejection recorded.");
      setPhase("done");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not record the rejection.");
      setPhase("error");
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "loading") {
    return (
      <Shell>
        <p className="text-center text-sm text-muted">Processing…</p>
      </Shell>
    );
  }

  if (phase === "error") {
    return (
      <Shell>
        <p className="text-center text-4xl text-danger">✗</p>
        <p className="mt-4 text-center text-sm text-body">{message}</p>
        <p className="mt-2 text-center text-xs text-muted">
          The link may be invalid or expired. If you believe this is a mistake, contact the
          applicant.
        </p>
      </Shell>
    );
  }

  if (phase === "done") {
    const approved = outcome === "approved";
    return (
      <Shell>
        <p
          className="text-center text-5xl"
          style={{ color: approved ? "#3EC97A" : "#EF4444" }}
        >
          {approved ? "✓" : "✗"}
        </p>
        <p className="mt-4 text-center text-sm text-body">{message}</p>
        <p className="mt-2 text-center text-xs text-muted">You may close this tab.</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="text-lg font-medium text-body">Reject this request?</h1>
      {purpose && <p className="mt-2 text-sm text-muted">{purpose}</p>}
      {label && (
        <p className="mt-1 text-xs uppercase tracking-wider text-muted">Acting as {label}</p>
      )}

      <label className="label mt-6" htmlFor="reason">
        Reason for rejection
      </label>
      <textarea
        id="reason"
        rows={4}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="The applicant will see this and can revise their request."
        className="input resize-none"
      />

      <button
        onClick={() => void confirmRejection()}
        disabled={submitting || reason.trim().length === 0}
        className="btn-danger mt-4 w-full"
      >
        {submitting ? "Recording…" : "Confirm rejection"}
      </button>
      <p className="mt-3 text-center text-xs text-muted">
        This link is unique to you. No login is required.
      </p>
    </Shell>
  );
}

export default function ApprovePage() {
  return (
    <Suspense
      fallback={
        <Shell>
          <p className="text-center text-sm text-muted">Loading…</p>
        </Shell>
      }
    >
      <ApprovePageInner />
    </Suspense>
  );
}
