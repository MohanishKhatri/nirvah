"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import StatusBadge from "@/components/StatusBadge";
import { getMyRequests } from "@/lib/api";
import { useIdentity } from "@/lib/useIdentity";
import type { RequestSummary } from "@/types";

const ALLOWED_DOMAIN = process.env.NEXT_PUBLIC_ALLOWED_DOMAIN ?? "nitk.edu.in";

function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function HomePage() {
  const { ready, authed, email, idToken, isDemo, mocksEnabled, signInGoogle, signOutAll, enterDemo } =
    useIdentity();
  const [requests, setRequests] = useState<RequestSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authed) return;
    let cancelled = false;
    getMyRequests(idToken)
      .then((rows) => {
        if (!cancelled) setRequests(rows);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [authed, idToken]);

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted">Loading…</p>
      </main>
    );
  }

  if (!authed) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-6">
        <div className="w-full max-w-md text-center">
          <h1 className="text-5xl font-semibold tracking-[0.2em] text-body">NIRVAH</h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            Describe what you need in plain language. NIRVAH reads your institution&apos;s policies
            and builds the exact approval chain they require — with the clause behind every step.
          </p>

          <button onClick={() => signInGoogle()} className="btn-primary mt-8 w-full">
            Sign in with Google
          </button>
          <p className="mt-3 text-xs text-muted">
            Restricted to <span className="text-body">@{ALLOWED_DOMAIN}</span> accounts.
          </p>

          {mocksEnabled && (
            <button onClick={enterDemo} className="btn-ghost mt-4 w-full">
              Continue as demo student
            </button>
          )}

          <Link href="/admin" className="mt-10 inline-block text-xs text-muted hover:text-body">
            Admin panel →
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-6 py-10">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold tracking-[0.2em]">NIRVAH</span>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted">{email}</span>
          {isDemo && (
            <span className="rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted">
              demo
            </span>
          )}
          <button onClick={signOutAll} className="text-muted hover:text-body">
            Sign out
          </button>
        </div>
      </header>

      <Link href="/request" className="btn-primary mt-10 w-full py-4 text-base">
        New request
      </Link>

      <section className="mt-10">
        <h2 className="label">Your requests</h2>

        {error && <p className="card mt-3 text-sm text-danger">{error}</p>}

        {!requests && !error && <p className="mt-3 text-sm text-muted">Loading requests…</p>}

        {requests?.length === 0 && (
          <p className="card mt-3 text-sm text-muted">
            Nothing yet. Start with a new request above.
          </p>
        )}

        <ul className="mt-3 space-y-2">
          {requests?.map((r) => (
            <li key={r.id}>
              <Link
                href={`/track/${r.id}`}
                className="flex items-center justify-between gap-4 rounded-xl border border-line bg-surface px-5 py-4 transition-colors hover:border-line2"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm text-body">{r.purpose}</span>
                  <span className="mt-1 block text-xs text-muted">
                    #{r.id} · {formatDate(r.created_at)}
                  </span>
                </span>
                <StatusBadge status={r.status} />
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <Link href="/admin" className="mt-12 inline-block text-xs text-muted hover:text-body">
        Admin panel →
      </Link>
    </main>
  );
}
