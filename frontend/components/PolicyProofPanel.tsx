"use client";

import type { NodeStatus, WorkflowNode } from "@/types";

const STATUS_TEXT: Record<NodeStatus, { label: string; color: string }> = {
  approved: { label: "✓ Approved", color: "#3EC97A" },
  active: { label: "⏳ Awaiting response", color: "#F0C040" },
  rejected: { label: "✗ Rejected", color: "#EF4444" },
  blocked: { label: "○ Not yet reached", color: "#6B7280" },
};

function formatTime(iso: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-4 border-t border-line py-3 text-sm first:border-t-0">
      <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
      <span className="text-body">{children}</span>
    </div>
  );
}

export default function PolicyProofPanel({
  node,
  onClose,
}: {
  node: WorkflowNode;
  onClose: () => void;
}) {
  const status = STATUS_TEXT[node.status] ?? STATUS_TEXT.blocked;
  const activated = formatTime(node.activated_at);
  const completed = formatTime(node.completed_at);

  return (
    <section className="card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-medium text-body">{node.label}</h3>
          <p className="mt-0.5 text-xs uppercase tracking-wider text-muted">Policy proof</p>
        </div>
        <button
          onClick={onClose}
          aria-label="Close policy proof"
          className="rounded-lg border border-line px-2 py-1 text-xs text-muted hover:border-line2 hover:text-body"
        >
          ✕
        </button>
      </div>

      <div className="mt-4">
        <Row label="Status">
          <span style={{ color: status.color }}>{status.label}</span>
        </Row>

        <Row label="Why">{node.reason}</Row>

        <Row label="Source">
          <span className="font-medium text-amber">
            {node.source_doc}
            {node.source_section ? ` ${node.source_section}` : ""}
          </span>
        </Row>

        {node.parallel_group && (
          <Row label="Runs with">
            <span className="text-orange">
              Other approvals in the “{node.parallel_group}” group — these run simultaneously.
            </span>
          </Row>
        )}

        {activated && <Row label="Activated">{activated}</Row>}
        {completed && <Row label="Completed">{completed}</Row>}
      </div>
    </section>
  );
}
