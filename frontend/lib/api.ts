/**
 * Single place every network call lives.
 * Flip NEXT_PUBLIC_USE_MOCKS to "false" to hit the real backend.
 */
import type {
  ApprovalActionResponse,
  ApproverContact,
  Policy,
  PolicyDiff,
  RequestSummary,
  SubmitResponse,
  WorkflowNode,
  WorkflowResponse,
} from "@/types";
import * as mock from "./mockData";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
/** When on, the mocked workflow advances every few polls so the tracking page visibly updates. */
const MOCK_LIVE = process.env.NEXT_PUBLIC_MOCK_LIVE === "true";

export const ADMIN_PASSWORD_KEY = "nirvah_admin_password";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const delay = (ms = 500) => new Promise((resolve) => setTimeout(resolve, ms));

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("Could not reach the NIRVAH server. Is the backend running?", 0);
  }

  const raw = await res.text();
  let body: unknown = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }
  }

  if (!res.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : typeof body === "string" && body
          ? body
          : `Request failed (${res.status})`;
    throw new ApiError(detail, res.status);
  }

  return body as T;
}

function studentHeaders(idToken: string, json = true): HeadersInit {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    Authorization: `Bearer ${idToken}`,
  };
}

function adminPassword(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(ADMIN_PASSWORD_KEY) ?? "";
}

function adminHeaders(json = true): HeadersInit {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    "x-admin-password": adminPassword(),
  };
}

/* ------------------------------------------------------------------ requests */

export async function submitRequest(text: string, idToken: string): Promise<SubmitResponse> {
  if (USE_MOCKS) {
    await delay();
    return { ...mock.mockFirstResponse };
  }
  return request<SubmitResponse>("/api/requests/", {
    method: "POST",
    headers: studentHeaders(idToken),
    body: JSON.stringify({ text }),
  });
}

export async function answerQuestion(
  requestId: number,
  field: string,
  value: string,
  idToken: string,
): Promise<SubmitResponse> {
  if (USE_MOCKS) {
    await delay();
    const index = mock.mockQuestionSequence.findIndex((q) => q.field === field);
    const next = mock.mockQuestionSequence[index + 1];
    if (next) {
      return {
        request_id: mock.MOCK_REQUEST_ID,
        status: "awaiting_info",
        question: next.question,
        asking_for: next.field,
      };
    }
    return { ...mock.mockCompletedResponse };
  }
  return request<SubmitResponse>(`/api/requests/${requestId}/answer`, {
    method: "POST",
    headers: studentHeaders(idToken),
    body: JSON.stringify({ field, value }),
  });
}

let mockPollCount = 0;

/** Mock-only: walks the demo workflow forward so polling has something to pick up. */
function advanceMockWorkflow(): WorkflowResponse {
  const steps = Math.floor(mockPollCount / 3);
  const nodes: WorkflowNode[] = mock.mockWorkflow.nodes.map((n) => ({ ...n }));
  const tiers = Array.from(new Set(nodes.map((n) => n.order_index))).sort((a, b) => a - b);

  for (let i = 0; i < steps; i++) {
    const activeTier = tiers.find((t) =>
      nodes.some((n) => n.order_index === t && n.status === "active"),
    );
    if (activeTier === undefined) break;

    nodes.forEach((n) => {
      if (n.order_index === activeTier && n.status === "active") {
        n.status = "approved";
        n.completed_at = new Date().toISOString();
      }
    });

    const nextTier = tiers.find((t) => t > activeTier);
    if (nextTier !== undefined) {
      nodes.forEach((n) => {
        if (n.order_index === nextTier && n.status === "blocked") {
          n.status = "active";
          n.activated_at = new Date().toISOString();
        }
      });
    }
  }

  const allApproved = nodes.every((n) => n.status === "approved");
  return { ...mock.mockWorkflow, status: allApproved ? "approved" : "pending", nodes };
}

export async function getWorkflow(requestId: number, idToken: string): Promise<WorkflowResponse> {
  if (USE_MOCKS) {
    await delay(300);
    if (!MOCK_LIVE) return mock.mockWorkflow;
    mockPollCount += 1;
    return advanceMockWorkflow();
  }
  return request<WorkflowResponse>(`/api/requests/${requestId}/workflow`, {
    headers: studentHeaders(idToken, false),
  });
}

export async function getMyRequests(idToken: string): Promise<RequestSummary[]> {
  if (USE_MOCKS) {
    await delay(400);
    return mock.mockRequests;
  }
  return request<RequestSummary[]>("/api/requests/", {
    headers: studentHeaders(idToken, false),
  });
}

/* ----------------------------------------------------------------- approvals */

export async function handleApprovalAction(
  token: string,
  action: "approve" | "reject",
): Promise<ApprovalActionResponse> {
  if (USE_MOCKS) {
    await delay();
    return action === "approve" ? mock.mockApproveResult : mock.mockRejectPrompt;
  }
  return request<ApprovalActionResponse>(
    `/api/approvals/action?token=${encodeURIComponent(token)}&action=${action}`,
  );
}

export async function submitRejection(
  token: string,
  reason: string,
): Promise<ApprovalActionResponse> {
  if (USE_MOCKS) {
    await delay();
    return mock.mockRejectResult;
  }
  return request<ApprovalActionResponse>(
    `/api/approvals/reject?token=${encodeURIComponent(token)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    },
  );
}

/* ------------------------------------------------------------------ policies */

export async function uploadPolicy(
  file: File,
  name: string,
): Promise<{ id: number; name: string; message: string }> {
  if (USE_MOCKS) {
    await delay(1500);
    return { id: 99, name, message: "Policy ingested successfully" };
  }
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  return request("/api/policies/upload", {
    method: "POST",
    headers: adminHeaders(false),
    body: form,
  });
}

export async function getPolicies(): Promise<Policy[]> {
  if (USE_MOCKS) {
    await delay(400);
    return mock.mockPolicies;
  }
  return request<Policy[]>("/api/policies/", { headers: adminHeaders(false) });
}

export async function publishPolicy(id: number): Promise<{ message: string }> {
  if (USE_MOCKS) {
    await delay(600);
    return { message: "Policy published" };
  }
  return request(`/api/policies/${id}/publish`, {
    method: "POST",
    headers: adminHeaders(false),
  });
}

export async function diffPolicies(oldPolicyId: number, newPolicyId: number): Promise<PolicyDiff> {
  if (USE_MOCKS) {
    await delay(1200);
    return mock.mockDiff;
  }
  return request<PolicyDiff>(
    `/api/policies/diff?old_policy_id=${oldPolicyId}&new_policy_id=${newPolicyId}`,
    { method: "POST", headers: adminHeaders(false) },
  );
}

export async function recompilePending(): Promise<{
  recompiled: number;
  changed: { request_id: number; purpose: string; added: string[]; removed: string[] }[];
}> {
  if (USE_MOCKS) {
    await delay(1200);
    return {
      recompiled: 2,
      changed: [
        {
          request_id: 9,
          purpose: "GPU procurement for the vision lab (₹68,000)",
          added: ["registrar"],
          removed: [],
        },
      ],
    };
  }
  return request("/api/admin/recompile-pending", {
    method: "POST",
    headers: adminHeaders(false),
  });
}

export async function getContacts(): Promise<ApproverContact[]> {
  if (USE_MOCKS) {
    await delay(400);
    return mock.mockContacts;
  }
  return request<ApproverContact[]>("/api/policies/contacts", {
    headers: adminHeaders(false),
  });
}

export async function upsertContact(contact: ApproverContact): Promise<ApproverContact> {
  if (USE_MOCKS) {
    await delay(500);
    return contact;
  }
  return request<ApproverContact>("/api/policies/contacts", {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify(contact),
  });
}
