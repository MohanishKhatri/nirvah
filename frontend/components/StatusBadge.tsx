import type { NodeStatus, RequestStatus } from "@/types";

type Status = RequestStatus | NodeStatus;

const STYLES: Record<string, { bg: string; border: string; text: string; label: string }> = {
  approved: { bg: "#14532D33", border: "#3EC97A", text: "#3EC97A", label: "Approved" },
  rejected: { bg: "#450A0A66", border: "#EF4444", text: "#EF4444", label: "Rejected" },
  pending: { bg: "#1A120066", border: "#F0C040", text: "#F0C040", label: "Pending" },
  active: { bg: "#1A120066", border: "#F0C040", text: "#F0C040", label: "Awaiting response" },
  awaiting_info: { bg: "#0B1E3A66", border: "#5B9DF9", text: "#5B9DF9", label: "Awaiting info" },
  compiling: { bg: "#0B1E3A66", border: "#5B9DF9", text: "#5B9DF9", label: "Compiling" },
  draft: { bg: "#151920", border: "#2E3545", text: "#6B7280", label: "Draft" },
  blocked: { bg: "#151920", border: "#2E3545", text: "#6B7280", label: "Not yet reached" },
};

export default function StatusBadge({
  status,
  className = "",
}: {
  status: Status | string;
  className?: string;
}) {
  const style = STYLES[status] ?? STYLES.draft;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${className}`}
      style={{ background: style.bg, borderColor: style.border, color: style.text }}
    >
      {style.label}
    </span>
  );
}
