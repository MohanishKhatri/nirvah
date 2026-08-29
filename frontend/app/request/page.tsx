"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { answerQuestion, submitRequest } from "@/lib/api";
import { useIdentity } from "@/lib/useIdentity";
import type { SubmitResponse } from "@/types";

interface Message {
  role: "user" | "assistant";
  text: string;
  tone?: "normal" | "success" | "blocked";
}

const OPENING: Message = {
  role: "assistant",
  text: "What do you need help with? Describe your request in plain language.",
};

export default function RequestPage() {
  const router = useRouter();
  const { ready, authed, idToken } = useIdentity();

  const [messages, setMessages] = useState<Message[]>([OPENING]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [requestId, setRequestId] = useState<number | null>(null);
  const [askingFor, setAskingFor] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const push = (m: Message) => setMessages((prev) => [...prev, m]);

  function handleResponse(res: SubmitResponse) {
    setRequestId(res.request_id);

    if (res.immediate_blocks && res.immediate_blocks.length > 0) {
      push({
        role: "assistant",
        tone: "blocked",
        text:
          "This request can't proceed as described:\n\n" +
          res.immediate_blocks.map((b) => `• ${b}`).join("\n"),
      });
      setFinished(true);
      setAskingFor(null);
      return;
    }

    if (res.status === "awaiting_info" && res.question) {
      push({ role: "assistant", text: res.question });
      setAskingFor(res.asking_for ?? null);
      return;
    }

    if (res.workflow_compiled || res.status === "pending") {
      push({
        role: "assistant",
        tone: "success",
        text: "Got everything I need. I've compiled your approval chain from the policies — opening your tracking page…",
      });
      setFinished(true);
      setAskingFor(null);
      setTimeout(() => router.push(`/track/${res.request_id}`), 1500);
      return;
    }

    push({ role: "assistant", text: "Request recorded." });
    setFinished(true);
  }

  async function send() {
    const text = input.trim();
    if (!text || loading || finished) return;

    push({ role: "user", text });
    setInput("");
    setLoading(true);

    try {
      const res =
        requestId === null || askingFor === null
          ? await submitRequest(text, idToken)
          : await answerQuestion(requestId, askingFor, text, idToken);
      handleResponse(res);
    } catch (e) {
      push({
        role: "assistant",
        tone: "blocked",
        text: e instanceof Error ? e.message : "Something went wrong. Please try again.",
      });
    } finally {
      setLoading(false);
    }
  }

  if (ready && !authed) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6">
        <p className="text-sm text-muted">You need to sign in before making a request.</p>
        <Link href="/" className="btn-primary">
          Go to sign in
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto flex h-screen w-full max-w-3xl flex-col px-6 py-6">
      <header className="flex items-center justify-between pb-4">
        <Link href="/" className="text-xs text-muted hover:text-body">
          ← Back
        </Link>
        <span className="text-sm font-semibold tracking-[0.2em]">NIRVAH</span>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto pb-4 pr-1">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[80%] whitespace-pre-wrap rounded-xl bg-amber px-4 py-3 text-sm text-[#07080C]"
                  : `max-w-[85%] whitespace-pre-wrap rounded-xl border px-4 py-3 text-sm ${
                      m.tone === "success"
                        ? "border-success bg-[#14532D22] text-success"
                        : m.tone === "blocked"
                          ? "border-danger bg-[#450A0A44] text-[#FCA5A5]"
                          : "border-line bg-surface text-body"
                    }`
              }
            >
              {m.text}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-muted">
              Thinking…
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t border-line pt-4">
        <div className="flex items-end gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            disabled={finished}
            placeholder={
              finished ? "This conversation is complete." : "Describe your request…"
            }
            className="input resize-none"
          />
          <button
            onClick={() => void send()}
            disabled={loading || finished || input.trim().length === 0}
            className="btn-primary h-[46px] px-6"
          >
            Send
          </button>
        </div>
        <p className="mt-2 text-xs text-muted">
          Enter to send · Shift + Enter for a new line
          {askingFor && (
            <>
              {" "}
              · answering <span className="text-body">{askingFor.replace(/_/g, " ")}</span>
            </>
          )}
        </p>
      </div>
    </main>
  );
}
