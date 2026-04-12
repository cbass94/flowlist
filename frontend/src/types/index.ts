// FlowList — shared TypeScript types (mirrors backend Pydantic schemas)

export type TaskType = "work" | "personal";

export type TaskStatus =
  | "backlog"
  | "scheduled"
  | "tentatively_done"
  | "done"
  | "delegated";

export type PriorityLevel = "top" | "high" | "medium" | "low";
export type ConfidenceLevel = "high" | "medium" | "low";

export interface Task {
  id: number;
  title: string;
  type: TaskType;
  priority: number;
  status: TaskStatus;
  estimated_duration_minutes: number | null;
  optional_user_estimate: string | null;
  optional_deadline: string | null;        // ISO date string YYYY-MM-DD
  scheduled_blocks: string[];
  next_scheduled_start: string | null;     // ISO datetime or null
  actual_duration_minutes: number | null;
  is_off_hours_allowed: boolean;
  is_workday_allowed: boolean;
  part_of_task_id: number | null;
  procrastination_flag: boolean;
  created_at: string;
  completed_at: string | null;
  updated_at: string;
  notes: string | null;
}

export interface AISuggestion {
  title: string;
  type: TaskType;
  suggested_priority: PriorityLevel;
  estimated_duration_minutes: number;
  reasoning: string;
  optional_deadline_detected: string | null;  // ISO date YYYY-MM-DD or null
  confidence: ConfidenceLevel;
  keywords: string[];
}

export interface ParseRequest {
  raw_text: string;
  optional_user_estimate?: string;
}

export interface ParseResponse {
  suggestion: AISuggestion;
  ai_available: boolean;
}

export interface TaskCreate {
  title: string;
  type: TaskType;
  priority?: number;
  estimated_duration_minutes?: number;
  optional_user_estimate?: string;
  optional_deadline?: string;
  is_off_hours_allowed?: boolean;
  is_workday_allowed?: boolean;
  notes?: string;
  part_of_task_id?: number;
  ai_suggested_priority?: PriorityLevel;
  ai_confidence?: ConfidenceLevel;
  ai_keywords?: string[];
}

export interface TaskUpdate {
  title?: string;
  type?: TaskType;
  priority?: number;
  status?: TaskStatus;
  estimated_duration_minutes?: number;
  optional_user_estimate?: string;
  optional_deadline?: string;
  is_off_hours_allowed?: boolean;
  is_workday_allowed?: boolean;
  notes?: string;
  procrastination_flag?: boolean;
}

export interface ReorderRequest {
  ordered_task_ids: number[];
}

export interface CompleteRequest {
  actual_duration_minutes?: number;
}

export interface User {
  id: number;
  email: string;
  display_name: string | null;
  personal_account_connected: boolean;
  is_admin: boolean;
}

export interface AuthStatus {
  authenticated: boolean;
  user: User | null;
}

export interface UserSettings {
  timezone: string;
  display_name: string | null;
  personal_account_connected: boolean;
  work_start_hour: number;
  work_end_hour: number;
  hard_start_hour: number;
  hard_end_hour: number;
  buffer_minutes: number;
  work_calendar_id: string | null;
  personal_calendar_id: string | null;
}

export interface CalendarItem {
  id: string;
  summary: string;
  primary: boolean;
}

export type InviteStatus = "pending" | "accepted" | "expired";

export interface Invite {
  id: number;
  email: string;
  token: string;
  created_at: string;
  accepted_at: string | null;
  expires_at: string | null;
  status: InviteStatus;
}
