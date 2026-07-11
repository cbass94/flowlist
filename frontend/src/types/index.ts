// FlowList — shared TypeScript types (mirrors backend Pydantic schemas)

export type TaskType = "work" | "personal";

export type TaskStatus =
  | "backlog"
  | "scheduled"
  | "tentatively_done"
  | "done"
  | "delegated";

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
  blocks: TaskBlock[];                     // all active calendar chunks, ordered by start_at
  actual_duration_minutes: number | null;
  is_off_hours_allowed: boolean;
  is_workday_allowed: boolean;
  no_weekends: boolean;
  part_of_task_id: number | null;
  procrastination_flag: boolean;
  created_at: string;
  completed_at: string | null;
  updated_at: string;
  description: string | null;
  // Linked Google Calendar event (manually associated)
  linked_calendar_event_id: string | null;
  linked_calendar_event_title: string | null;
  linked_calendar_event_start: string | null;
  // Cached AI Assistant response
  ai_assistant_cache: AssistantCachedData | null;
  ai_assistant_cached_at: string | null;
}

export interface TaskBlock {
  id: number;
  start_at: string;  // ISO datetime
  end_at: string;    // ISO datetime
}

export interface MoreWorkSuggestion {
  suggested_additional_minutes: number;
  original_estimate_minutes: number | null;
  scheduled_past_minutes: number;
  scheduled_future_minutes: number;
  ai_available: boolean;
}

export interface AssistantCachedData {
  summary: string;
  suggestions: AssistantSuggestionItem[];
  recommended_workflow: string;
}

export interface AISuggestion {
  title: string;
  type: TaskType;
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

export interface AssistantSuggestionItem {
  tool_or_approach: string;
  description: string;
  time_saved: string;
}

export interface AssistantResponse {
  summary: string;
  suggestions: AssistantSuggestionItem[];
  recommended_workflow: string;
  ai_available: boolean;
}

export interface AssistantRequest {
  task_id?: number;
  title: string;
  type: TaskType;
  estimated_duration_minutes?: number;
  description?: string;
  optional_deadline?: string;
  is_off_hours_allowed?: boolean;
  is_workday_allowed?: boolean;
  no_weekends?: boolean;
  linked_calendar_event_title?: string;
  linked_calendar_event_start?: string;
}

export interface FeedbackRequest {
  task_id?: number;
  task_title: string;
  task_type: TaskType;
  is_positive: boolean;
  comment?: string;
  ai_summary: string;
  ai_suggestions: string;
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
  no_weekends?: boolean;
  description?: string;
  part_of_task_id?: number;
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
  no_weekends?: boolean;
  description?: string;
  procrastination_flag?: boolean;
  linked_calendar_event_id?: string | null;
  linked_calendar_event_title?: string | null;
  linked_calendar_event_start?: string | null;
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
  allow_work_on_weekends: boolean;
  allow_personal_on_weekends: boolean;
  work_saturday_start_time: string | null;
  work_saturday_end_time: string | null;
  work_sunday_start_time: string | null;
  work_sunday_end_time: string | null;
  personal_saturday_start_time: string | null;
  personal_saturday_end_time: string | null;
  personal_sunday_start_time: string | null;
  personal_sunday_end_time: string | null;
  synthesis_enabled: boolean;
  synthesis_duration_minutes: number;
  synthesis_self_emails: string | null;
  colorize_enabled: boolean;
  color_purposeful: string;
  color_necessary: string;
  color_distracting: string;
  color_unnecessary: string;
}

export interface CalendarItem {
  id: string;
  summary: string;
  primary: boolean;
}

export interface CalendarEvent {
  id: string;
  summary: string;
  start: string;
  end: string;
  is_flowlist: boolean;
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

export interface RescheduleAllOverdueResponse {
  rescheduled_task_ids: number[];
  task_count: number;
}

export interface BlockDoneRequest {
  confirmed_remaining_minutes: number;
}
