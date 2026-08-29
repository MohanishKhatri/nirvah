export type RequestStatus =
  | "draft"
  | "awaiting_info"
  | "compiling"
  | "pending"
  | "approved"
  | "rejected";

export type NodeStatus = "blocked" | "active" | "approved" | "rejected";

export interface StructuredFields {
  category?: string;
  purpose?: string;
  budget?: number | null;
  attendees?: number | null;
  external_speakers?: number | null;
  venue?: string | null;
  club_name?: string | null;
  duration_days?: number | null;
  item_description?: string | null;
  missing_fields?: string[];
  [key: string]: unknown;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  text: string;
  asking_for?: string;
  answered_field?: string;
}

export interface WorkflowNode {
  id: number;
  role: string;
  label: string;
  status: NodeStatus;
  reason: string;
  source_doc: string;
  source_section: string | null;
  parallel_group: string | null;
  order_index: number;
  activated_at: string | null;
  completed_at: string | null;
}

export interface WorkflowResponse {
  request_id: number;
  status: RequestStatus;
  structured_fields: StructuredFields;
  conversation: ConversationTurn[];
  nodes: WorkflowNode[];
}

/** Response shape shared by POST /api/requests/ and POST /api/requests/{id}/answer */
export interface SubmitResponse {
  request_id: number;
  status: RequestStatus;
  question?: string;
  asking_for?: string;
  fields_extracted?: StructuredFields;
  workflow_compiled?: boolean;
  immediate_blocks?: string[];
}

export interface RequestSummary {
  id: number;
  purpose: string;
  status: RequestStatus;
  created_at: string;
}

export interface ApprovalActionResponse {
  message?: string;
  requires_reason?: boolean;
  token?: string;
  label?: string;
  purpose?: string;
}

export interface Policy {
  id: number;
  name: string;
  uploaded_at: string;
  is_active?: boolean;
  version?: number;
}

export interface ApproverContact {
  id?: number;
  role: string;
  label: string;
  email: string;
}

export interface PolicyDiff {
  changed: { description: string; old_text: string; new_text: string; impact: string }[];
  added: { description: string; text: string; impact: string }[];
  removed: { description: string; text: string; impact: string }[];
}
