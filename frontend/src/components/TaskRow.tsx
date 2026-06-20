/**
 * TaskRow — single row in the backlog list.
 *
 * Supports:
 *  - Drag-and-drop via dnd-kit (drag handle on left)
 *  - Click anywhere on the row body to expand inline details / edit
 *  - Inline edit: all task fields editable in place
 *  - Inline actions: Complete, Delegate, Delete
 *  - Procrastination flag indicator
 *  - Linked Google Calendar event (paste event ID, fetch details, confirm)
 */

import { useEffect, useMemo, useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO, isToday, isTomorrow, differenceInCalendarDays } from "date-fns";
import clsx from "clsx";
import { tasksApi } from "../services/tasks";
import { aiApi } from "../services/ai";
import api from "../services/api";
import type {
  Task,
  TaskBlock,
  TaskUpdate,
  CalendarEvent,
  AssistantResponse,
  AssistantCachedData,
  MoreWorkSuggestion,
} from "../types";

// ── Type badge ────────────────────────────────────────────────────────────────

function TypeBadge({ type }: { type: Task["type"] }) {
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium",
        type === "work"
          ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
          : "bg-violet-50 dark:bg-violet-950 text-violet-600 dark:text-violet-400"
      )}
    >
      {type === "work" ? "Work" : "Personal"}
    </span>
  );
}

// ── Status display ────────────────────────────────────────────────────────────

function formatBlockDate(iso: string): string {
  const d = parseISO(iso);
  const today = new Date();
  const diff = differenceInCalendarDays(d, today);
  if (isToday(d)) return "Today";
  if (isTomorrow(d)) return "Tomorrow";
  if (diff > -7 && diff < 0) return format(d, "EEE");
  if (diff < 7) return format(d, "EEE");
  return format(d, "MMM d");
}

function ScheduledLabel({ iso, overdue }: { iso: string; overdue?: boolean }) {
  try {
    const d = parseISO(iso);
    const dateStr = formatBlockDate(iso);
    const timeStr = format(d, "h:mm a");
    if (overdue) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800 px-2 py-0.5 text-xs font-semibold text-orange-700 dark:text-orange-300">
          <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.75" />
            <path d="M8 4.5V8l2 1.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Started {dateStr} at {timeStr} — needs action
        </span>
      );
    }
    return (
      <span className="text-xs text-green-600 dark:text-green-400 font-medium">
        {dateStr} at {timeStr}
      </span>
    );
  } catch {
    return null;
  }
}

interface ChunkInfo {
  blocks: TaskBlock[];                  // sorted by start_at
  current: TaskBlock | null;            // latest started (start_at <= now); null if none started
  next: TaskBlock | null;               // earliest future (start_at > now)
  displayed: TaskBlock | null;          // current ?? next
  displayedIndex: number | null;        // 1-based index of `displayed` in `blocks`
  total: number;
  hasOverdueAction: boolean;            // current exists and task is in scheduled-like status
}

function computeChunkInfo(task: Task): ChunkInfo {
  const blocks = (task.blocks ?? [])
    .slice()
    .sort((a, b) => parseISO(a.start_at).getTime() - parseISO(b.start_at).getTime());
  const now = new Date();
  let current: TaskBlock | null = null;
  let next: TaskBlock | null = null;
  for (const b of blocks) {
    const start = parseISO(b.start_at);
    if (start <= now) current = b;
    else if (next === null) next = b;
  }
  const displayed = current ?? next;
  const displayedIndex = displayed
    ? blocks.findIndex((b) => b.start_at === displayed.start_at && b.end_at === displayed.end_at) + 1
    : null;
  const hasOverdueAction =
    current !== null &&
    (task.status === "scheduled" || task.status === "tentatively_done");
  return {
    blocks,
    current,
    next,
    displayed,
    displayedIndex,
    total: blocks.length,
    hasOverdueAction,
  };
}

function ChunkBadge({ index, total, blocks }: { index: number; total: number; blocks: TaskBlock[] }) {
  const [open, setOpen] = useState(false);
  // Only render for multi-chunk tasks
  if (total <= 1) return null;
  const now = new Date();

  return (
    <span className="relative inline-flex">
      <span
        className="inline-flex items-center rounded-md bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 dark:text-gray-400 cursor-help"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
      >
        chunk {index} of {total}
      </span>
      {open && (
        <div
          className="absolute left-0 top-full mt-1 z-20 rounded-lg bg-gray-900 dark:bg-gray-700 text-white shadow-lg
                     px-3 py-2 whitespace-nowrap pointer-events-none"
          role="tooltip"
        >
          {blocks.map((b, i) => {
            const start = parseISO(b.start_at);
            const end = parseISO(b.end_at);
            const isPast = end <= now;
            const isCurrent = start <= now && end > now;
            const dateStr = formatBlockDate(b.start_at);
            const timeStr = format(start, "h:mm a");
            const endStr = format(end, "h:mm a");
            return (
              <div
                key={`${b.start_at}-${b.end_at}`}
                className={clsx(
                  "text-[11px] leading-tight py-0.5",
                  isPast && "text-gray-300",
                  isCurrent && "text-orange-300 font-semibold",
                  !isPast && !isCurrent && "text-white",
                )}
              >
                {i + 1}. {dateStr} {timeStr}–{endStr}
                {isCurrent && <span className="ml-1 text-[10px] text-orange-200 no-underline">(now)</span>}
                {isPast && <span className="ml-1 text-[10px] text-gray-400 no-underline">(past)</span>}
              </div>
            );
          })}
        </div>
      )}
    </span>
  );
}

function StatusIndicator({ task }: { task: Task }) {
  if (task.status === "delegated") {
    return (
      <span className="inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
        Delegated
      </span>
    );
  }
  return null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDuration(mins: number | null) {
  if (!mins) return null;
  if (mins < 60) return `${mins}m`;
  const h = mins / 60;
  return `${h === Math.floor(h) ? h : h.toFixed(1)}h`;
}

function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label className={clsx("flex items-center gap-2 cursor-pointer select-none", disabled && "opacity-50")}>
      <div
        className={clsx(
          "relative w-8 h-4 rounded-full transition-colors",
          checked ? "bg-gray-900 dark:bg-gray-100" : "bg-gray-200 dark:bg-gray-700",
          disabled && "pointer-events-none"
        )}
        onClick={() => !disabled && onChange(!checked)}
        role="switch"
        aria-checked={checked}
      >
        <div
          className={clsx(
            "absolute top-0.5 left-0.5 w-3 h-3 bg-white dark:bg-gray-900 rounded-full shadow transition-transform",
            checked && "translate-x-4"
          )}
        />
      </div>
      <span className="text-xs text-gray-600 dark:text-gray-300">{label}</span>
    </label>
  );
}

// ── Linked calendar event section ─────────────────────────────────────────────

function LinkedEventSection({
  task,
  onLink,
  onUnlink,
}: {
  task: Task;
  onLink: (id: string, title: string, start: string) => void;
  onUnlink: () => void;
}) {
  const [eventInput, setEventInput] = useState("");
  const [lookupId, setLookupId] = useState<string | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const { data: event, isLoading: isLooking, isError } = useQuery<CalendarEvent>({
    queryKey: ["calendar-event", lookupId],
    queryFn: () =>
      api.get<CalendarEvent>(`/calendar/event/${lookupId}`).then((r) => r.data),
    enabled: lookupId !== null,
    retry: false,
  });

  function handleLookup() {
    setLookupError(null);
    const id = parseEventId(eventInput.trim());
    if (!id) {
      setLookupError("Enter a valid Google Calendar event ID or URL.");
      return;
    }
    setLookupId(id);
  }

  function handleConfirm(ev: CalendarEvent) {
    onLink(ev.id, ev.summary, ev.start);
    setEventInput("");
    setLookupId(null);
  }

  function handleCancel() {
    setEventInput("");
    setLookupId(null);
    setLookupError(null);
  }

  if (task.linked_calendar_event_id) {
    return (
      <div className="flex items-center gap-2 bg-green-50 dark:bg-green-950 border border-green-100 dark:border-green-900 rounded-lg px-3 py-2">
        <svg className="w-3.5 h-3.5 text-green-600 dark:text-green-400 shrink-0" fill="none" viewBox="0 0 16 16">
          <path d="M3 8l3 3 7-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-green-800 dark:text-green-200 font-medium truncate">
            {task.linked_calendar_event_title || task.linked_calendar_event_id}
          </p>
          {task.linked_calendar_event_start && (
            <p className="text-xs text-green-600 dark:text-green-400">
              {formatLinkedEventStart(task.linked_calendar_event_start)}
            </p>
          )}
        </div>
        <button
          onClick={onUnlink}
          className="text-xs text-green-500 dark:text-green-400 hover:text-red-500 dark:hover:text-red-400 transition-colors shrink-0"
        >
          Unlink
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {lookupId && event ? (
        <div className="flex items-start gap-2 bg-blue-50 dark:bg-blue-950 border border-blue-100 dark:border-blue-900 rounded-lg px-3 py-2">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-blue-800 dark:text-blue-200 font-medium">{event.summary}</p>
            <p className="text-xs text-blue-600 dark:text-blue-400">{formatLinkedEventStart(event.start)}</p>
          </div>
          <div className="flex gap-1.5 shrink-0">
            <button
              onClick={() => handleConfirm(event)}
              className="text-xs text-white bg-blue-600 hover:bg-blue-700 px-2 py-0.5 rounded transition-colors"
            >
              Link
            </button>
            <button onClick={handleCancel} className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="text"
            value={eventInput}
            onChange={(e) => setEventInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLookup()}
            placeholder="Paste Google Calendar event ID"
            className="flex-1 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-2.5 py-1.5
                       focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-blue-500/20
                       placeholder-gray-300 dark:placeholder-gray-600 transition-colors"
          />
          <button
            onClick={handleLookup}
            disabled={!eventInput.trim() || isLooking}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300
                       hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors shrink-0"
          >
            {isLooking ? "…" : "Look up"}
          </button>
        </div>
      )}
      {(lookupError || isError) && (
        <p className="text-xs text-red-500 dark:text-red-400">{lookupError || "Event not found."}</p>
      )}
    </div>
  );
}

function parseEventId(input: string): string | null {
  if (!input) return null;
  // If it's a URL, try to extract eid param
  try {
    const url = new URL(input);
    const eid = url.searchParams.get("eid");
    if (eid) {
      // eid is base64url — decode to get event ID
      try {
        const decoded = atob(eid.replace(/-/g, "+").replace(/_/g, "/"));
        // Format is "eventId calendarId" — take first part
        return decoded.split(" ")[0] || input;
      } catch {
        return eid;
      }
    }
  } catch {
    // Not a URL — treat as raw event ID
  }
  return input;
}

function formatLinkedEventStart(iso: string): string {
  try {
    const d = parseISO(iso);
    return format(d, "MMM d, yyyy 'at' h:mm a");
  } catch {
    return iso;
  }
}

// ── AI Assistant panel ───────────────────────────────────────────────────────

function formatCacheAge(iso: string): string {
  try {
    const d = parseISO(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return "";
  }
}

function AIAssistantButton({ task }: { task: Task }) {
  const queryClient = useQueryClient();
  const hasCached = !!task.ai_assistant_cache;
  const [show, setShow] = useState(false);
  const [liveResult, setLiveResult] = useState<AssistantResponse | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [feedbackVote, setFeedbackVote] = useState<boolean | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");

  const displayData: AssistantCachedData | null = liveResult ?? task.ai_assistant_cache;
  const cachedAt = liveResult ? null : task.ai_assistant_cached_at;

  const mutation = useMutation({
    mutationFn: () =>
      aiApi.getTaskAssistance({
        task_id: task.id,
        title: task.title,
        type: task.type,
        estimated_duration_minutes: task.estimated_duration_minutes ?? undefined,
        description: task.description ?? undefined,
        optional_deadline: task.optional_deadline ?? undefined,
        is_off_hours_allowed: task.is_off_hours_allowed,
        is_workday_allowed: task.is_workday_allowed,
        no_weekends: task.no_weekends,
        linked_calendar_event_title: task.linked_calendar_event_title ?? undefined,
        linked_calendar_event_start: task.linked_calendar_event_start ?? undefined,
      }),
    onSuccess: (data) => {
      setLiveResult(data);
      setShow(true);
      setFeedbackSent(false);
      setFeedbackVote(null);
      setFeedbackComment("");
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const feedbackMutation = useMutation({
    mutationFn: (isPositive: boolean) => {
      const suggestionsText = displayData?.suggestions
        .map((s) => `${s.tool_or_approach}: ${s.description}`)
        .join("; ") ?? "";
      return aiApi.submitFeedback({
        task_id: task.id,
        task_title: task.title,
        task_type: task.type,
        is_positive: isPositive,
        comment: feedbackComment.trim() || undefined,
        ai_summary: displayData?.summary ?? "",
        ai_suggestions: suggestionsText,
      });
    },
    onSuccess: () => setFeedbackSent(true),
  });

  function handleOpen() {
    if (hasCached) {
      setShow(true);
    } else {
      mutation.mutate();
    }
  }

  function handleRefresh() {
    setFeedbackSent(false);
    setFeedbackVote(null);
    setFeedbackComment("");
    mutation.mutate();
  }

  function handleClose() {
    setShow(false);
    setLiveResult(null);
    setFeedbackSent(false);
    setFeedbackVote(null);
    setFeedbackComment("");
  }

  return (
    <div className="space-y-2">
      {!show && (
        <button
          onClick={handleOpen}
          disabled={mutation.isPending}
          className={clsx(
            "flex items-center gap-2 w-full rounded-lg border px-3 py-2 text-xs",
            "transition-all duration-150",
            !mutation.isPending
              ? "border-violet-200 dark:border-violet-800 bg-violet-50/60 dark:bg-violet-950/60 text-violet-700 dark:text-violet-300 hover:bg-violet-100/80 dark:hover:bg-violet-900/80 hover:border-violet-300 dark:hover:border-violet-700"
              : "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed"
          )}
        >
          <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" />
            <circle cx="8" cy="8" r="2.5" />
          </svg>
          <span className="flex-1 text-left">
            {mutation.isPending ? "Thinking..." : "AI Assistant"}
          </span>
          {hasCached && task.ai_assistant_cached_at && (
            <span className="text-[10px] text-violet-400 dark:text-violet-500 shrink-0">
              {formatCacheAge(task.ai_assistant_cached_at)}
            </span>
          )}
        </button>
      )}

      {mutation.isPending && (
        <div className="space-y-1.5">
          <div className="animate-pulse rounded bg-gray-200 dark:bg-gray-700 h-3 w-full" />
          <div className="animate-pulse rounded bg-gray-200 dark:bg-gray-700 h-3 w-3/4" />
          <div className="animate-pulse rounded bg-gray-200 dark:bg-gray-700 h-3 w-5/6" />
        </div>
      )}

      {show && displayData && (
        <div className="rounded-lg border border-violet-200 dark:border-violet-800 bg-violet-50/40 dark:bg-violet-950/40 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-violet-100 dark:border-violet-900 bg-violet-50/60 dark:bg-violet-950/60">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-violet-700 dark:text-violet-300">AI Assistant</span>
              {cachedAt && (
                <span className="text-[10px] text-violet-400 dark:text-violet-500">
                  {formatCacheAge(cachedAt)}
                </span>
              )}
              {liveResult && (
                <span className="text-[10px] text-emerald-500 dark:text-emerald-400">just generated</span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleRefresh}
                disabled={mutation.isPending}
                className="text-violet-400 dark:text-violet-500 hover:text-violet-600 dark:hover:text-violet-300 transition-colors p-0.5 disabled:opacity-50"
                aria-label="Refresh suggestions"
                title="Re-run AI Assistant with latest data"
              >
                <svg className={clsx("w-3.5 h-3.5", mutation.isPending && "animate-spin")} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 8a6 6 0 0 1 10.3-4.2" />
                  <path d="M14 8a6 6 0 0 1-10.3 4.2" />
                  <path d="M12.3 1v2.8h-2.8" />
                  <path d="M3.7 15v-2.8h2.8" />
                </svg>
              </button>
              <button
                onClick={handleClose}
                className="text-violet-400 dark:text-violet-500 hover:text-violet-600 dark:hover:text-violet-300 transition-colors p-0.5"
                aria-label="Close assistant"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M4.22 4.22a.75.75 0 0 1 1.06 0L8 6.94l2.72-2.72a.75.75 0 1 1 1.06 1.06L9.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L8 9.06l-2.72 2.72a.75.75 0 0 1-1.06-1.06L6.94 8 4.22 5.28a.75.75 0 0 1 0-1.06Z" />
                </svg>
              </button>
            </div>
          </div>
          <div className="p-3 space-y-3">
            <p className="text-xs text-violet-800 dark:text-violet-200 font-medium">{displayData.summary}</p>
            <div className="space-y-2">
              {displayData.suggestions.map((s, i) => (
                <div key={i} className="rounded-md bg-white/80 dark:bg-gray-800/80 border border-violet-100 dark:border-violet-900 p-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-semibold text-gray-800 dark:text-gray-100">{s.tool_or_approach}</span>
                    <span className="shrink-0 rounded-full bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 px-1.5 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-300">
                      {s.time_saved}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-300 mt-1 leading-relaxed">{s.description}</p>
                </div>
              ))}
            </div>
            {displayData.recommended_workflow && (
              <div className="border-t border-violet-100 dark:border-violet-900 pt-2">
                <span className="text-xs font-semibold text-violet-700 dark:text-violet-300 block mb-1">Recommended workflow</span>
                <p className="text-xs text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-line">{displayData.recommended_workflow}</p>
              </div>
            )}

            {/* Feedback section */}
            <div className="border-t border-violet-100 dark:border-violet-900 pt-2.5">
              {feedbackSent ? (
                <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Thanks for your feedback!</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Was this helpful?</span>
                    <button
                      onClick={() => setFeedbackVote(true)}
                      className={clsx(
                        "rounded-md border px-2 py-1 text-xs transition-all duration-150",
                        feedbackVote === true
                          ? "border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300"
                          : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:border-emerald-200 dark:hover:border-emerald-800 hover:text-emerald-600 dark:hover:text-emerald-400"
                      )}
                    >
                      <span className="flex items-center gap-1">
                        <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M5 9V14H3C2.45 14 2 13.55 2 13V10C2 9.45 2.45 9 3 9H5ZM5 9L7.5 3C7.5 3 8 2 9 2C10 2 10 3 10 3V6H13C13.55 6 14 6.45 14 7L12.5 13C12.3 13.6 11.75 14 11.1 14H7C6.45 14 6 13.55 5.5 13" />
                        </svg>
                        Yes
                      </span>
                    </button>
                    <button
                      onClick={() => setFeedbackVote(false)}
                      className={clsx(
                        "rounded-md border px-2 py-1 text-xs transition-all duration-150",
                        feedbackVote === false
                          ? "border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300"
                          : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:border-red-200 dark:hover:border-red-800 hover:text-red-600 dark:hover:text-red-400"
                      )}
                    >
                      <span className="flex items-center gap-1">
                        <svg className="w-3 h-3 rotate-180" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M5 9V14H3C2.45 14 2 13.55 2 13V10C2 9.45 2.45 9 3 9H5ZM5 9L7.5 3C7.5 3 8 2 9 2C10 2 10 3 10 3V6H13C13.55 6 14 6.45 14 7L12.5 13C12.3 13.6 11.75 14 11.1 14H7C6.45 14 6 13.55 5.5 13" />
                        </svg>
                        No
                      </span>
                    </button>
                  </div>
                  {feedbackVote !== null && (
                    <div className="space-y-1.5">
                      <textarea
                        value={feedbackComment}
                        onChange={(e) => setFeedbackComment(e.target.value)}
                        rows={2}
                        className="w-full text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-2.5 py-1.5
                                   focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                                   focus-visible:ring-2 focus-visible:ring-blue-500/20
                                   placeholder-gray-300 dark:placeholder-gray-600 transition-colors resize-none"
                        placeholder={feedbackVote ? "What was most useful? (optional)" : "What could be better? (optional)"}
                      />
                      <button
                        onClick={() => feedbackMutation.mutate(feedbackVote!)}
                        disabled={feedbackMutation.isPending}
                        className="rounded-md bg-gray-900 dark:bg-gray-100 px-3 py-1 text-xs font-medium text-white dark:text-gray-900
                                   hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97] disabled:opacity-50
                                   transition-all duration-150"
                      >
                        {feedbackMutation.isPending ? "Sending..." : "Submit feedback"}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {show && liveResult && !liveResult.ai_available && (
        <p className="rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-100 dark:border-amber-900 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          AI Assistant is temporarily unavailable. Try again in a moment.
        </p>
      )}

      {mutation.isError && !mutation.isPending && (
        <p className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-100 dark:border-red-900 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          Failed to get AI suggestions. Please try again.
        </p>
      )}
    </div>
  );
}

// ── Inline edit panel ─────────────────────────────────────────────────────────

interface EditFormState {
  title: string;
  type: Task["type"];
  estimated_duration_minutes: string;
  optional_deadline: string;
  description: string;
  is_off_hours_allowed: boolean;
  is_workday_allowed: boolean;
  no_weekends: boolean;
}

function initEditForm(task: Task): EditFormState {
  return {
    title: task.title,
    type: task.type,
    estimated_duration_minutes: task.estimated_duration_minutes?.toString() ?? "",
    optional_deadline: task.optional_deadline ?? "",
    description: task.description ?? "",
    is_off_hours_allowed: task.is_off_hours_allowed,
    is_workday_allowed: task.is_workday_allowed,
    no_weekends: task.no_weekends,
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  task: Task;
  isDraggable?: boolean;
  position?: number;
}

const inputCls = "w-full text-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-2 focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20 transition-colors";

export function TaskRow({ task, isDraggable = true, position }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<EditFormState>(() => initEditForm(task));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [moreWorkOpen, setMoreWorkOpen] = useState(false);
  const [moreWorkMinutes, setMoreWorkMinutes] = useState<string>("");
  const queryClient = useQueryClient();

  const chunkInfo = useMemo(() => computeChunkInfo(task), [task]);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: task.id,
      disabled: !isDraggable,
    });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["watchdog"] });
  }

  const isOverdue = chunkInfo.hasOverdueAction;

  const completeMutation = useMutation({
    mutationFn: () => tasksApi.complete(task.id, {}),
    onSuccess: invalidate,
  });

  const delegateMutation = useMutation({
    mutationFn: () => tasksApi.delegate(task.id),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: invalidate,
  });

  const updateMutation = useMutation({
    mutationFn: (body: TaskUpdate) => tasksApi.update(task.id, body),
    onSuccess: () => {
      invalidate();
      setEditing(false);
    },
  });

  const rescheduleOverdueMutation = useMutation({
    mutationFn: () => tasksApi.rescheduleOverdue(task.id),
    onSuccess: invalidate,
  });

  const moreWorkSuggestionQuery = useQuery<MoreWorkSuggestion>({
    queryKey: ["more-work-suggestion", task.id],
    queryFn: () => tasksApi.moreWorkSuggestion(task.id),
    enabled: moreWorkOpen,
    staleTime: 5 * 60 * 1000,
  });

  const moreWorkMutation = useMutation({
    mutationFn: (mins: number) => tasksApi.moreWork(task.id, mins),
    onSuccess: () => {
      invalidate();
      setMoreWorkOpen(false);
      setMoreWorkMinutes("");
    },
  });

  const deleteBlockMutation = useMutation({
    mutationFn: (blockId: number) => tasksApi.deleteBlock(task.id, blockId),
    onSuccess: invalidate,
  });

  const [doneBlockId, setDoneBlockId] = useState<number | null>(null);
  const [doneRemainingInput, setDoneRemainingInput] = useState<string>("");

  const blockDoneMutation = useMutation({
    mutationFn: ({ blockId, remaining }: { blockId: number; remaining: number }) =>
      tasksApi.blockDone(task.id, blockId, remaining),
    onSuccess: () => {
      invalidate();
      setDoneBlockId(null);
      setDoneRemainingInput("");
    },
  });

  const blockRescheduleMutation = useMutation({
    mutationFn: (blockId: number) => tasksApi.blockReschedule(task.id, blockId),
    onSuccess: invalidate,
  });

  const isBusy =
    completeMutation.isPending ||
    delegateMutation.isPending ||
    deleteMutation.isPending ||
    updateMutation.isPending ||
    rescheduleOverdueMutation.isPending ||
    moreWorkMutation.isPending ||
    deleteBlockMutation.isPending ||
    blockDoneMutation.isPending ||
    blockRescheduleMutation.isPending;

  function handleOpenMoreWork() {
    setMoreWorkOpen(true);
    setMoreWorkMinutes("");
  }

  function handleConfirmMoreWork() {
    const mins = parseInt(moreWorkMinutes, 10);
    if (!isNaN(mins) && mins >= 15 && mins <= 480) {
      moreWorkMutation.mutate(mins);
    }
  }

  const suggestion = moreWorkSuggestionQuery.data;
  useEffect(() => {
    if (moreWorkOpen && suggestion && moreWorkMinutes === "") {
      setMoreWorkMinutes(String(suggestion.suggested_additional_minutes));
    }
  }, [moreWorkOpen, suggestion, moreWorkMinutes]);

  function setField<K extends keyof EditFormState>(key: K, value: EditFormState[K]) {
    setEditForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleEditOpen() {
    setEditForm(initEditForm(task));
    setEditing(true);
    setExpanded(true);
  }

  function handleEditSave() {
    const durationMins = editForm.estimated_duration_minutes
      ? parseInt(editForm.estimated_duration_minutes, 10)
      : undefined;

    const update: TaskUpdate = {
      title: editForm.title.trim() || task.title,
      type: editForm.type,
      estimated_duration_minutes: durationMins && !isNaN(durationMins) ? durationMins : undefined,
      optional_deadline: editForm.optional_deadline || undefined,
      description: editForm.description || undefined,
      is_off_hours_allowed: editForm.is_off_hours_allowed,
      is_workday_allowed: editForm.is_workday_allowed,
      no_weekends: editForm.no_weekends,
    };
    updateMutation.mutate(update);
  }

  function handleLinkEvent(id: string, title: string, start: string) {
    updateMutation.mutate({
      linked_calendar_event_id: id,
      linked_calendar_event_title: title,
      linked_calendar_event_start: start,
    });
  }

  function handleUnlinkEvent() {
    updateMutation.mutate({
      linked_calendar_event_id: null,
      linked_calendar_event_title: null,
      linked_calendar_event_start: null,
    });
  }

  const durationLabel = formatDuration(task.estimated_duration_minutes);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        "bg-white dark:bg-gray-900 border border-gray-200/60 dark:border-gray-700/60 rounded-xl shadow-sm shadow-gray-100 dark:shadow-black/20 transition-shadow",
        isDragging ? "shadow-lg shadow-gray-200/80 dark:shadow-black/40 opacity-80 z-10" : "",
        task.procrastination_flag && "border-l-4 border-l-amber-400"
      )}
    >
      {/* Main row */}
      <div className="flex items-stretch">
        {/* Drag handle */}
        {isDraggable && (
          <button
            {...attributes}
            {...listeners}
            className="flex items-center justify-center w-10 shrink-0 text-gray-300 dark:text-gray-600
                       hover:text-gray-500 dark:hover:text-gray-400 cursor-grab active:cursor-grabbing
                       touch-none rounded-l-xl"
            aria-label="Drag to reorder"
            tabIndex={-1}
          >
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="5" cy="4" r="1.2" />
              <circle cx="11" cy="4" r="1.2" />
              <circle cx="5" cy="8" r="1.2" />
              <circle cx="11" cy="8" r="1.2" />
              <circle cx="5" cy="12" r="1.2" />
              <circle cx="11" cy="12" r="1.2" />
            </svg>
          </button>
        )}

        {/* Row body — click to expand (div role="button" to allow nested interactive elements) */}
        <div
          role="button"
          tabIndex={0}
          className="flex flex-1 items-start gap-3 px-3 py-3 text-left min-w-0
                     hover:bg-gray-50/60 dark:hover:bg-gray-800/40 transition-colors rounded-r-xl cursor-pointer"
          onClick={() => {
            if (!editing && !isDragging) setExpanded((v) => !v);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") setExpanded((v) => !v);
          }}
        >
          {/* Priority number */}
          <span className="shrink-0 w-5 text-center text-xs font-semibold text-gray-400 dark:text-gray-500 mt-0.5">
            {position ?? task.priority}
          </span>

          {/* Content */}
          <div className="flex-1 min-w-0 space-y-1">
            <div className="flex items-start gap-2 flex-wrap">
              <span
                className={clsx(
                  "text-sm font-medium text-gray-800 dark:text-gray-100 leading-snug",
                  task.procrastination_flag && "text-gray-700 dark:text-gray-200"
                )}
              >
                {task.title}
              </span>
              {task.procrastination_flag && (
                <span
                  className="text-amber-500 dark:text-amber-400 text-xs shrink-0"
                  title="Procrastination flag — this task has been waiting a while"
                >
                  ⚠
                </span>
              )}
            </div>
            <div className="flex items-center flex-wrap gap-x-2 gap-y-1">
              <TypeBadge type={task.type} />
              <StatusIndicator task={task} />
              {durationLabel && (
                <span className="text-xs text-gray-400 dark:text-gray-500">~{durationLabel}</span>
              )}
              {chunkInfo.displayed && (task.status === "scheduled" || task.status === "tentatively_done") && (
                <>
                  <ScheduledLabel iso={chunkInfo.displayed.start_at} overdue={isOverdue} />
                  {chunkInfo.displayedIndex !== null && (
                    <ChunkBadge
                      index={chunkInfo.displayedIndex}
                      total={chunkInfo.total}
                      blocks={chunkInfo.blocks}
                    />
                  )}
                </>
              )}
              {!chunkInfo.displayed && task.status === "backlog" && (
                <span className="text-xs text-gray-300 dark:text-gray-600">Unscheduled</span>
              )}
              {task.linked_calendar_event_id && (
                <span className="text-xs text-green-600 dark:text-green-400" title={task.linked_calendar_event_title ?? undefined}>
                  📅 linked
                </span>
              )}
            </div>
          </div>

          {/* Right side: inline reschedule pill (overdue + collapsed only) + expand chevron */}
          <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
            {isOverdue && !expanded && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  rescheduleOverdueMutation.mutate();
                }}
                disabled={isBusy}
                className="rounded-md bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 px-2 py-0.5 text-[11px]
                           font-medium text-gray-600 dark:text-gray-300 disabled:opacity-50 transition-colors"
                title="Reschedule this missed block"
              >
                {rescheduleOverdueMutation.isPending ? "…" : "Reschedule"}
              </button>
            )}
            <svg
              className={clsx(
                "w-4 h-4 text-gray-300 dark:text-gray-600 transition-transform",
                expanded && "rotate-180"
              )}
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-gray-100 dark:border-gray-800 px-4 py-3 ml-10 space-y-4">
          {editing ? (
            /* ── Edit mode ── */
            <div className="space-y-3">
              {/* Title */}
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Title</label>
                <input
                  type="text"
                  value={editForm.title}
                  onChange={(e) => setField("title", e.target.value)}
                  className={inputCls}
                />
              </div>

              {/* Type + Duration */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Type</label>
                  <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                    {(["work", "personal"] as Task["type"][]).map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setField("type", t)}
                        className={clsx(
                          "flex-1 py-1.5 text-xs font-medium capitalize transition-colors",
                          editForm.type === t
                            ? "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900"
                            : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Estimated (min)</label>
                  <input
                    type="number"
                    min={15}
                    max={480}
                    step={15}
                    value={editForm.estimated_duration_minutes}
                    onChange={(e) => setField("estimated_duration_minutes", e.target.value)}
                    className={inputCls}
                    placeholder="e.g. 60"
                  />
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Description</label>
                <textarea
                  value={editForm.description}
                  onChange={(e) => setField("description", e.target.value)}
                  rows={3}
                  className={`${inputCls} resize-none`}
                  placeholder="Add details, context, or notes for this task..."
                />
              </div>

              {/* Deadline + Constraint toggles */}
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Deadline</label>
                <input
                  type="date"
                  value={editForm.optional_deadline}
                  onChange={(e) => setField("optional_deadline", e.target.value)}
                  className={inputCls}
                />
              </div>

              <div className="space-y-2">
                {editForm.type === "work" && (
                  <Toggle
                    checked={editForm.is_off_hours_allowed}
                    onChange={(v) => setField("is_off_hours_allowed", v)}
                    label="Allow scheduling outside work hours"
                  />
                )}
                {editForm.type === "personal" && (
                  <Toggle
                    checked={editForm.is_workday_allowed}
                    onChange={(v) => setField("is_workday_allowed", v)}
                    label="Allow scheduling during work hours"
                  />
                )}
                <Toggle
                  checked={editForm.no_weekends}
                  onChange={(v) => setField("no_weekends", v)}
                  label="Weekdays only (no weekends)"
                />
              </div>

              {/* AI Assistant */}
              <AIAssistantButton task={task} />

              {/* Save / Cancel */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleEditSave}
                  disabled={isBusy}
                  className="rounded-lg bg-gray-900 dark:bg-gray-100 px-3 py-1.5 text-xs font-medium
                             text-white dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97]
                             disabled:opacity-50 transition-all duration-150"
                >
                  {updateMutation.isPending ? "Saving…" : "Save changes"}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-xs
                             text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            /* ── View mode ── */
            <div className="space-y-3">
              {/* Meta grid */}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                {task.optional_deadline && (
                  <>
                    <dt className="text-gray-400 dark:text-gray-500">Deadline</dt>
                    <dd className="text-gray-700 dark:text-gray-200">{task.optional_deadline}</dd>
                  </>
                )}
                {task.estimated_duration_minutes && (
                  <>
                    <dt className="text-gray-400 dark:text-gray-500">Estimated</dt>
                    <dd className="text-gray-700 dark:text-gray-200">{formatDuration(task.estimated_duration_minutes)}</dd>
                  </>
                )}
                {task.is_off_hours_allowed && task.type === "work" && (
                  <>
                    <dt className="text-gray-400 dark:text-gray-500">Off-hours</dt>
                    <dd className="text-gray-700 dark:text-gray-200">Allowed</dd>
                  </>
                )}
                {task.is_workday_allowed && task.type === "personal" && (
                  <>
                    <dt className="text-gray-400 dark:text-gray-500">Workday</dt>
                    <dd className="text-gray-700 dark:text-gray-200">Allowed</dd>
                  </>
                )}
                {task.no_weekends && (
                  <>
                    <dt className="text-gray-400 dark:text-gray-500">Weekends</dt>
                    <dd className="text-gray-700 dark:text-gray-200">Excluded</dd>
                  </>
                )}
                {task.part_of_task_id && (
                  <>
                    <dt className="text-gray-400 dark:text-gray-500">Part of</dt>
                    <dd className="text-gray-700 dark:text-gray-200">Task #{task.part_of_task_id}</dd>
                  </>
                )}
              </dl>

              {task.description && (
                <p className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap border-t border-gray-100 dark:border-gray-800 pt-2">
                  {task.description}
                </p>
              )}

              {/* Scheduled chunks */}
              {chunkInfo.blocks.length > 0 && (
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1.5">
                    Scheduled chunks ({chunkInfo.blocks.length})
                  </p>
                  <ul className="space-y-1.5">
                    {chunkInfo.blocks.map((b, i) => {
                      const start = parseISO(b.start_at);
                      const end = parseISO(b.end_at);
                      const now = new Date();
                      const isPast = end <= now;
                      const isCurrent = start <= now && end > now;
                      const isMultiChunk = chunkInfo.blocks.length > 1;
                      const dateStr = formatBlockDate(b.start_at);
                      const timeStr = format(start, "h:mm a");
                      const endStr = format(end, "h:mm a");
                      const blockDurationMinutes = Math.round((end.getTime() - start.getTime()) / 60_000);
                      const autoRemaining = Math.max(0, (task.estimated_duration_minutes ?? 0) - blockDurationMinutes);
                      const pendingDelete = deleteBlockMutation.isPending && deleteBlockMutation.variables === b.id;
                      const pendingReschedule = blockRescheduleMutation.isPending && blockRescheduleMutation.variables === b.id;
                      const pendingDone = blockDoneMutation.isPending && blockDoneMutation.variables?.blockId === b.id;
                      const isDoneOpen = doneBlockId === b.id;
                      return (
                        <li key={b.id} className="space-y-1.5">
                          <div
                            className={clsx(
                              "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs border",
                              isCurrent && "bg-orange-50 dark:bg-orange-950 border-orange-200 dark:border-orange-800",
                              isPast && !isCurrent && "bg-gray-50 dark:bg-gray-800 border-gray-100 dark:border-gray-700 text-gray-500 dark:text-gray-400",
                              !isPast && !isCurrent && "bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700 text-gray-700 dark:text-gray-200",
                            )}
                          >
                            <span className="w-4 text-center text-[10px] text-gray-400 dark:text-gray-500 shrink-0">
                              {i + 1}
                            </span>
                            <span className="flex-1 min-w-0">
                              <span className="font-medium">{dateStr}</span>
                              <span className="ml-1.5">{timeStr}–{endStr}</span>
                            </span>
                            {isCurrent && (
                              <span className="text-[10px] font-semibold text-orange-700 dark:text-orange-300 shrink-0">now</span>
                            )}
                            {isPast && !isCurrent && (
                              <span className="text-[10px] text-gray-400 dark:text-gray-500 shrink-0">past</span>
                            )}
                            {isMultiChunk && (isPast || isCurrent) && (
                              <button
                                onClick={() => {
                                  setDoneBlockId(b.id);
                                  setDoneRemainingInput(String(autoRemaining));
                                }}
                                disabled={isBusy || isDoneOpen}
                                className="text-[11px] text-emerald-600 dark:text-emerald-400 hover:text-emerald-800 dark:hover:text-emerald-200
                                           disabled:opacity-50 transition-colors shrink-0"
                                title="Mark this chunk as done — prompts for remaining estimate"
                              >
                                {pendingDone ? "…" : "Done"}
                              </button>
                            )}
                            {isMultiChunk && (
                              <button
                                onClick={() => blockRescheduleMutation.mutate(b.id)}
                                disabled={isBusy}
                                className="text-[11px] text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200
                                           disabled:opacity-50 transition-colors shrink-0"
                                title="Cancel this chunk and all subsequent, then reschedule"
                              >
                                {pendingReschedule ? "…" : "Reschedule"}
                              </button>
                            )}
                            <button
                              onClick={() => deleteBlockMutation.mutate(b.id)}
                              disabled={isBusy || pendingDelete}
                              className="text-[11px] text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300
                                         disabled:opacity-50 transition-colors shrink-0"
                              title="Delete this chunk (removes the calendar event)"
                            >
                              {pendingDelete ? "…" : "Delete"}
                            </button>
                          </div>
                          {isDoneOpen && (
                            <div className="ml-6 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/50 p-2.5 space-y-2">
                              <p className="text-xs text-gray-700 dark:text-gray-200">
                                How many minutes of work remain after this chunk?
                              </p>
                              <div className="flex items-center gap-2 flex-wrap">
                                <input
                                  type="number"
                                  min={0}
                                  max={960}
                                  step={15}
                                  value={doneRemainingInput}
                                  onChange={(e) => setDoneRemainingInput(e.target.value)}
                                  className="w-20 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-2 py-1
                                             focus-visible:border-emerald-300 dark:focus-visible:border-emerald-600 focus-visible:outline-none
                                             focus-visible:ring-2 focus-visible:ring-emerald-500/20"
                                />
                                <span className="text-xs text-gray-600 dark:text-gray-300">minutes remaining</span>
                                <button
                                  onClick={() => blockDoneMutation.mutate({
                                    blockId: b.id,
                                    remaining: parseInt(doneRemainingInput, 10) || 0,
                                  })}
                                  disabled={isBusy || doneRemainingInput === ""}
                                  className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-medium
                                             text-white hover:bg-emerald-700 active:scale-[0.97]
                                             disabled:opacity-50 transition-all duration-150"
                                >
                                  {blockDoneMutation.isPending ? "Saving…" : "Confirm"}
                                </button>
                                <button
                                  onClick={() => { setDoneBlockId(null); setDoneRemainingInput(""); }}
                                  className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                                >
                                  Cancel
                                </button>
                              </div>
                              {parseInt(doneRemainingInput, 10) === 0 && doneRemainingInput !== "" && (
                                <p className="text-xs text-emerald-700 dark:text-emerald-300">
                                  Setting to 0 will mark the entire task as done.
                                </p>
                              )}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {/* Linked calendar event */}
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mb-1.5">Linked Calendar Event</p>
                <LinkedEventSection
                  task={task}
                  onLink={handleLinkEvent}
                  onUnlink={handleUnlinkEvent}
                />
              </div>

              {/* AI Assistant */}
              <AIAssistantButton task={task} />
            </div>
          )}

          {/* Overdue / current-chunk actions */}
          {!editing && isOverdue && (
            <div className="space-y-2 pt-1 border-t border-orange-100 dark:border-orange-900">
              <p className="text-xs text-orange-700 dark:text-orange-300 font-medium">
                Current chunk has started
                {chunkInfo.displayedIndex !== null && chunkInfo.total > 1
                  ? ` (chunk ${chunkInfo.displayedIndex} of ${chunkInfo.total})`
                  : ""}
                . What happened?
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => rescheduleOverdueMutation.mutate()}
                  disabled={isBusy}
                  className="rounded-lg bg-gray-700 dark:bg-gray-300 px-3 py-1.5 text-xs font-medium
                             text-white dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97]
                             disabled:opacity-50 transition-all duration-150"
                  title="Cancel all chunks (including this one) and replan the full estimate from now"
                >
                  {rescheduleOverdueMutation.isPending ? "Rescheduling…" : "Reschedule"}
                </button>
                <button
                  onClick={() => completeMutation.mutate()}
                  disabled={isBusy}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium
                             text-white hover:bg-emerald-700 active:scale-[0.97]
                             disabled:opacity-50 transition-all duration-150"
                  title="Mark the whole task complete (cancels remaining future chunks)"
                >
                  {completeMutation.isPending ? "Saving…" : "✓ Done"}
                </button>
                <button
                  onClick={handleOpenMoreWork}
                  disabled={isBusy || moreWorkOpen}
                  className="rounded-lg border border-orange-300 dark:border-orange-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs
                             font-medium text-orange-700 dark:text-orange-300 hover:bg-orange-50 dark:hover:bg-orange-950 disabled:opacity-50
                             transition-colors"
                  title="Add more time to this task — past chunk stays put, more chunks added"
                >
                  More work needed
                </button>
              </div>

              {moreWorkOpen && (
                <div className="rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50/50 dark:bg-orange-950/50 p-3 space-y-2">
                  {moreWorkSuggestionQuery.isLoading && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">Asking AI for an estimate…</p>
                  )}
                  {suggestion && (
                    <>
                      <p className="text-xs text-gray-700 dark:text-gray-200">
                        {suggestion.ai_available
                          ? `AI suggests ~${suggestion.suggested_additional_minutes} more minutes`
                          : `Suggested: ${suggestion.suggested_additional_minutes} minutes (AI unavailable)`}
                        {suggestion.scheduled_future_minutes > 0 && (
                          <span className="text-gray-400 dark:text-gray-500">
                            {" "}· {suggestion.scheduled_future_minutes}m already on calendar after this
                          </span>
                        )}
                      </p>
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-gray-600 dark:text-gray-300">Add</label>
                        <input
                          type="number"
                          min={15}
                          max={480}
                          step={15}
                          value={moreWorkMinutes}
                          onChange={(e) => setMoreWorkMinutes(e.target.value)}
                          className="w-20 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-2 py-1
                                     focus-visible:border-orange-300 dark:focus-visible:border-orange-600 focus-visible:outline-none
                                     focus-visible:ring-2 focus-visible:ring-orange-500/20"
                        />
                        <label className="text-xs text-gray-600 dark:text-gray-300">minutes</label>
                        <button
                          onClick={handleConfirmMoreWork}
                          disabled={
                            isBusy ||
                            !moreWorkMinutes ||
                            isNaN(parseInt(moreWorkMinutes, 10))
                          }
                          className="rounded-lg bg-orange-600 px-3 py-1 text-xs font-medium
                                     text-white hover:bg-orange-700 active:scale-[0.97]
                                     disabled:opacity-50 transition-all duration-150"
                        >
                          {moreWorkMutation.isPending ? "Adding…" : "Confirm"}
                        </button>
                        <button
                          onClick={() => setMoreWorkOpen(false)}
                          className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                        >
                          Cancel
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Actions (always visible in expanded view) */}
          {!editing && (
            <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-gray-100 dark:border-gray-800">
              {task.status !== "done" && task.status !== "delegated" && !isOverdue && (
                <button
                  onClick={() => completeMutation.mutate()}
                  disabled={isBusy}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium
                             text-white hover:bg-emerald-700 active:scale-[0.97]
                             disabled:opacity-50 transition-all duration-150"
                >
                  {completeMutation.isPending ? "Saving…" : "✓ Done"}
                </button>
              )}

              {task.status !== "delegated" && task.status !== "done" && (
                <button
                  onClick={() => delegateMutation.mutate()}
                  disabled={isBusy}
                  title="Mark as delegated to someone else — cancels any scheduled calendar blocks"
                  className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-xs
                             text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50
                             transition-colors"
                >
                  {delegateMutation.isPending ? "…" : "Delegate"}
                </button>
              )}

              <button
                onClick={handleEditOpen}
                disabled={isBusy}
                className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-xs
                           text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50
                           transition-colors"
              >
                Edit
              </button>

              {confirmDelete ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-red-600 dark:text-red-400">Delete?</span>
                  <button
                    onClick={() => deleteMutation.mutate()}
                    disabled={isBusy}
                    className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium
                               text-white hover:bg-red-700 active:scale-[0.97]
                               disabled:opacity-50 transition-all duration-150"
                  >
                    Yes, delete
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-xs
                               text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDelete(true)}
                  disabled={isBusy}
                  className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-xs
                             text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 hover:border-red-200 dark:hover:border-red-800
                             disabled:opacity-50 transition-colors"
                >
                  Delete
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
