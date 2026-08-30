/**
 * Fixtures for the Robotics Club demo scenario.
 * Used whenever NEXT_PUBLIC_USE_MOCKS === "true". Delete once the API is wired.
 */
import type {
  ApproverContact,
  Policy,
  PolicyDiff,
  RequestSummary,
  SubmitResponse,
  WorkflowResponse,
} from "@/types";

export const MOCK_REQUEST_ID = 12;

/** The follow-up questions the mock chat walks through, in order. */
export const mockQuestionSequence: { field: string; question: string }[] = [
  { field: "club_name", question: "Which club or society is organising this?" },
  {
    field: "venue",
    question: "Where would you like to hold it? Give me the venue or hall name.",
  },
];

export const mockFirstResponse: SubmitResponse = {
  request_id: MOCK_REQUEST_ID,
  status: "awaiting_info",
  question: mockQuestionSequence[0].question,
  asking_for: mockQuestionSequence[0].field,
  fields_extracted: {
    category: "student_event",
    purpose: "Two-day drone workshop",
    budget: 35000,
    attendees: 120,
    external_speakers: 3,
    duration_days: 2,
  },
};

export const mockCompletedResponse: SubmitResponse = {
  request_id: MOCK_REQUEST_ID,
  status: "pending",
  workflow_compiled: true,
  immediate_blocks: [],
};

export const mockBlockedResponse: SubmitResponse = {
  request_id: 13,
  status: "rejected",
  workflow_compiled: false,
  immediate_blocks: ["Seminar Hall 2 capacity is 200; requested 2500 attendees — Venue Policy §2.4"],
};

export const mockWorkflow: WorkflowResponse = {
  request_id: MOCK_REQUEST_ID,
  status: "pending",
  structured_fields: {
    category: "student_event",
    purpose: "Two-day drone workshop for 120 students",
    budget: 35000,
    attendees: 120,
    external_speakers: 3,
    venue: "Seminar Hall 2",
    club_name: "Robotics Club",
    duration_days: 2,
  },
  conversation: [
    {
      role: "user",
      text: "Our Robotics Club wants a two-day drone workshop for 120 students, ₹35,000 funding and 3 external speakers in Seminar Hall 2.",
    },
    {
      role: "assistant",
      text: "Which club or society is organising this?",
      asking_for: "club_name",
    },
    { role: "user", text: "Robotics Club", answered_field: "club_name" },
  ],
  nodes: [
    {
      id: 45,
      role: "faculty_advisor",
      label: "Faculty Advisor",
      status: "approved",
      reason: "All student club events require Faculty Advisor approval before escalation.",
      source_doc: "Student Activity Policy",
      source_section: "§3",
      parallel_group: null,
      order_index: 1,
      activated_at: "2026-08-29T10:00:00",
      completed_at: "2026-08-29T11:30:00",
    },
    {
      id: 46,
      role: "hod",
      label: "Head of Department",
      status: "approved",
      reason: "Faculty Advisor approval is followed by Head of Department approval.",
      source_doc: "Student Activity Policy",
      source_section: "§3",
      parallel_group: null,
      order_index: 2,
      activated_at: "2026-08-29T11:30:00",
      completed_at: "2026-08-29T13:05:00",
    },
    {
      id: 47,
      role: "security",
      label: "Security Office",
      status: "active",
      reason: "3 external speakers attending — events with external guests require Security Office clearance.",
      source_doc: "Security Guidelines",
      source_section: "§4.1",
      parallel_group: "clearances",
      order_index: 3,
      activated_at: "2026-08-29T13:05:00",
      completed_at: null,
    },
    {
      id: 48,
      role: "venue",
      label: "Venue Office",
      status: "active",
      reason: "120 attendees exceeds the 100-attendee threshold for Venue Office approval.",
      source_doc: "Venue Policy",
      source_section: "§2.3",
      parallel_group: "clearances",
      order_index: 3,
      activated_at: "2026-08-29T13:05:00",
      completed_at: null,
    },
    {
      id: 49,
      role: "finance",
      label: "Finance Office",
      status: "blocked",
      reason: "Request involves expenditure of ₹35,000 and must route through the Finance Office.",
      source_doc: "Finance Policy",
      source_section: "§5.1",
      parallel_group: null,
      order_index: 4,
      activated_at: null,
      completed_at: null,
    },
    {
      id: 50,
      role: "dean",
      label: "Dean of Student Affairs",
      status: "blocked",
      reason: "Budget ₹35,000 exceeds the ₹25,000 threshold for student activity expenditure.",
      source_doc: "Finance Policy",
      source_section: "§8.2",
      parallel_group: null,
      order_index: 5,
      activated_at: null,
      completed_at: null,
    },
  ],
};

export const mockRequests: RequestSummary[] = [
  {
    id: MOCK_REQUEST_ID,
    purpose: "Two-day drone workshop for 120 students",
    status: "pending",
    created_at: "2026-08-29T10:00:00",
  },
  {
    id: 9,
    purpose: "GPU procurement for the vision lab (₹68,000)",
    status: "pending",
    created_at: "2026-08-27T09:12:00",
  },
  {
    id: 7,
    purpose: "Inter-college hackathon sponsorship approval",
    status: "approved",
    created_at: "2026-08-21T15:40:00",
  },
  {
    id: 5,
    purpose: "Industrial visit to Bengaluru — 45 students",
    status: "rejected",
    created_at: "2026-08-18T11:02:00",
  },
];

export const mockPolicies: Policy[] = [
  { id: 1, name: "Student Activity Policy", uploaded_at: "2026-08-25T09:00:00", is_active: true, version: 1 },
  { id: 2, name: "Finance Policy", uploaded_at: "2026-08-25T09:04:00", is_active: true, version: 1 },
  { id: 3, name: "Security Guidelines", uploaded_at: "2026-08-25T09:07:00", is_active: true, version: 1 },
  { id: 4, name: "Venue Policy", uploaded_at: "2026-08-25T09:11:00", is_active: true, version: 1 },
];

export const mockContacts: ApproverContact[] = [
  { id: 1, role: "faculty_advisor", label: "Faculty Advisor", email: "faculty@nitk.edu.in" },
  { id: 2, role: "hod", label: "Head of Department", email: "hod@nitk.edu.in" },
  { id: 3, role: "dean", label: "Dean of Student Affairs", email: "dean@nitk.edu.in" },
  { id: 4, role: "security", label: "Security Office", email: "security@nitk.edu.in" },
  { id: 5, role: "venue", label: "Venue Office", email: "venues@nitk.edu.in" },
  { id: 6, role: "finance", label: "Finance Office", email: "finance@nitk.edu.in" },
  { id: 7, role: "registrar", label: "Registrar", email: "registrar@nitk.edu.in" },
];

export const mockDiff: PolicyDiff = {
  changed: [
    {
      description: "Procurement approval threshold now escalates to the Registrar",
      old_text: "Procurement exceeding ₹25,000 requires Dean approval.",
      new_text:
        "Purchases exceeding ₹50,000 shall additionally require approval from the Registrar.",
      impact: "Any pending procurement above ₹50,000 gains a Registrar approval node.",
    },
  ],
  added: [
    {
      description: "New Registrar approval rule",
      text: "§3.1 — Effective immediately, purchases exceeding ₹50,000 shall additionally require approval from the Registrar.",
      impact: "Adds one node at the end of affected procurement workflows.",
    },
  ],
  removed: [],
};

export const mockApprovePrompt = {
  requires_confirmation: true,
  token: "mock-token",
  label: "Faculty Advisor",
  purpose: "Two-day drone workshop for 120 students",
};

export const mockApproveResult = {
  message: "Approved successfully. Thank you.",
};

export const mockRejectPrompt = {
  requires_reason: true,
  token: "mock-token",
  label: "Dean of Student Affairs",
  purpose: "Two-day drone workshop for 120 students",
};

export const mockRejectResult = {
  message: "Rejection recorded. Applicant has been notified.",
};
