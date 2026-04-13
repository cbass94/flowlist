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

import { useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO, isToday, isTomorrow, differenceInCalendarDays } from "date-fns";
import clsx from "clsx";
import { tasksApi } from "../services/tasks";
import api from "../services/api";
import type { Task, TaskUpdate, CalendarEvent } from "../types";

// ── Type badge ────────────────────────────────────────────────────────────────

function TypeBadge({ type }: { type: Task["type"] }) {
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium",
        type === "work"
          ? "bg-blue-100 text-blue-700"
          : "bg-violet-100 text-violet-700"
      )}
    >
      {type === "work" ? "Work" : "Personal"}
    </span>
  );
}

// ── Status display ────────────────────────────────────────────────────────────

function ScheduledLabel({ iso }: { iso: string }) {
  try {
    const d = parseISO(iso);
    const today = new Date();
    const diff = differenceInCalendarDays(d, today);
    let dateStr: string;
    if (isToday(d)) dateStr = "Today";
    else if (isTomorrow(d)) dateStr = "Tomorrow";
    else if (diff < 7) dateStr = format(d, "EEE");
    else dateStr = format(d, "MMM d");
    const timeStr = format(d, "h:mm a");
    return (
      <span className="text-xs text-green-600 font-medium">
        {dateStr} at {timeStr}
      </span>
    );
  } catch {
    return null;
  }
}

function StatusIndicator({ task }: { task: Task }) {
  if (task.status === "tentatively_done") {
    return (
      <span className="inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs bg-amber-100 text-amber-700 font-medium">
        Review needed
      </span>
    );
  }
  if (task.status === "delegated") {
    return (
      <span className="inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs bg-slate-100 text-slate-500">
        Delegated
      </span>
    );
  }
  // backlog and scheduled: no badge — show scheduled time if available
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
          checked ? "bg-blue-600" : "bg-gray-200",
          disabled && "pointer-events-none"
        )}
        onClick={() => !disabled && onChange(!checked)}
        role="switch"
        aria-checked={checked}
      >
        <div
          className={clsx(
            "absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform",
            checked && "translate-x-4"
          )}
        />
      </div>
      <span className="text-xs text-gray-600">{label}</span>
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
      <div className="flex items-center gap-2 bg-green-50 border border-green-100 rounded-lg px-3 py-2">
        <svg className="w-3.5 h-3.5 text-green-600 shrink-0" fill="none" viewBox="0 0 16 16">
          <path d="M3 8l3 3 7-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-green-800 font-medium truncate">
            {task.linked_calendar_event_title || task.linked_calendar_event_id}
          </p>
          {task.linked_calendar_event_start && (
            <p className="text-xs text-green-600">
              {formatLinkedEventStart(task.linked_calendar_event_start)}
            </p>
          )}
        </div>
        <button
          onClick={onUnlink}
          className="text-xs text-green-500 hover:text-red-500 transition-colors shrink-0"
        >
          Unlink
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {lookupId && event ? (
        <div className="flex items-start gap-2 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-blue-800 font-medium">{event.summary}</p>
            <p className="text-xs text-blue-600">{formatLinkedEventStart(event.start)}</p>
          </div>
          <div className="flex gap-1.5 shrink-0">
            <button
              onClick={() => handleConfirm(event)}
              className="text-xs text-white bg-blue-600 hover:bg-blue-700 px-2 py-0.5 rounded transition-colors"
            >
              Link
            </button>
            <button onClick={handleCancel} className="text-xs text-gray-500 hover:text-gray-700">
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
            className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5
                       focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-100
                       placeholder-gray-300 transition-colors"
          />
          <button
            onClick={handleLookup}
            disabled={!eventInput.trim() || isLooking}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-gray-100 text-gray-600
                       hover:bg-gray-200 disabled:opacity-50 transition-colors shrink-0"
          >
            {isLooking ? "…" : "Look up"}
          </button>
        </div>
      )}
      {(lookupError || isError) && (
        <p className="text-xs text-red-500">{lookupError || "Event not found."}</p>
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

// ── Inline edit panel ─────────────────────────────────────────────────────────

interface EditFormState {
  title: string;
  type: Task["type"];
  estimated_duration_minutes: string;
  optional_deadline: string;
  notes: string;
  is_off_hours_allowed: boolean;
  is_workday_allowed: boolean;
}

function initEditForm(task: Task): EditFormState {
  return {
    title: task.title,
    type: task.type,
    estimated_duration_minutes: task.estimated_duration_minutes?.toString() ?? "",
    optional_deadline: task.optional_deadline ?? "",
    notes: task.notes ?? "",
    is_off_hours_allowed: task.is_off_hours_allowed,
    is_workday_allowed: task.is_workday_allowed,
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  task: Task;
  isDraggable?: boolean;
}

export function TaskRow({ task, isDraggable = true }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<EditFormState>(() => initEditForm(task));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const queryClient = useQueryClient();

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

  const isBusy =
    completeMutation.isPending ||
    delegateMutation.isPending ||
    deleteMutation.isPending ||
    updateMutation.isPending;

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
      notes: editForm.notes || undefined,
      is_off_hours_allowed: editForm.is_off_hours_allowed,
      is_workday_allowed: editForm.is_workday_allowed,
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
        "bg-white border border-gray-200 rounded-xl transition-shadow",
        isDragging ? "shadow-lg opacity-80 z-10" : "shadow-none",
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
            className="flex items-center justify-center w-10 shrink-0 text-gray-300
                       hover:text-gray-500 cursor-grab active:cursor-grabbing
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

        {/* Row body — click to expand */}
        <button
          className="flex flex-1 items-start gap-3 px-3 py-3 text-left min-w-0
                     hover:bg-gray-50/60 transition-colors rounded-r-xl"
          onClick={() => {
            if (!editing) setExpanded((v) => !v);
          }}
          disabled={isDragging}
        >
          {/* Priority number */}
          <span className="shrink-0 w-5 text-center text-xs font-semibold text-gray-400 mt-0.5">
            {task.priority}
          </span>

          {/* Content */}
          <div className="flex-1 min-w-0 space-y-1">
            <div className="flex items-start gap-2 flex-wrap">
              <span
                className={clsx(
                  "text-sm font-medium text-gray-800 leading-snug",
                  task.procrastination_flag && "text-gray-700"
                )}
              >
                {task.title}
              </span>
              {task.procrastination_flag && (
                <span
                  className="text-amber-500 text-xs shrink-0"
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
                <span className="text-xs text-gray-400">~{durationLabel}</span>
              )}
              {task.next_scheduled_start && task.status === "scheduled" && (
                <ScheduledLabel iso={task.next_scheduled_start} />
              )}
              {!task.next_scheduled_start && task.status === "backlog" && (
                <span className="text-xs text-gray-300">Unscheduled</span>
              )}
              {task.linked_calendar_event_id && (
                <span className="text-xs text-green-600" title={task.linked_calendar_event_title ?? undefined}>
                  📅 linked
                </span>
              )}
            </div>
          </div>

          {/* Expand chevron */}
          <svg
            className={clsx(
              "w-4 h-4 text-gray-300 shrink-0 mt-0.5 transition-transform",
              expanded && "rotate-180"
            )}
            viewBox="0 0 16 16"
            fill="currentColor"
          >
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-3 ml-10 space-y-4">
          {editing ? (
            /* ── Edit mode ── */
            <div className="space-y-3">
              {/* Title */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Title</label>
                <input
                  type="text"
                  value={editForm.title}
                  onChange={(e) => setField("title", e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2
                             focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-100
                             transition-colors"
                />
              </div>

              {/* Type + Duration */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Type</label>
                  <div className="flex rounded-lg border border-gray-200 overflow-hidden">
                    {(["work", "personal"] as Task["type"][]).map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setField("type", t)}
                        className={clsx(
                          "flex-1 py-1.5 text-xs font-medium capitalize transition-colors",
                          editForm.type === t
                            ? "bg-blue-600 text-white"
                            : "bg-white text-gray-600 hover:bg-gray-50"
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Estimated (min)</label>
                  <input
                    type="number"
                    min={15}
                    max={480}
                    step={15}
                    value={editForm.estimated_duration_minutes}
                    onChange={(e) => setField("estimated_duration_minutes", e.target.value)}
                    className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2
                               focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-100
                               transition-colors"
                    placeholder="e.g. 60"
                  />
                </div>
              </div>

              {/* Deadline + Constraint toggles */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Deadline</label>
                <input
                  type="date"
                  value={editForm.optional_deadline}
                  onChange={(e) => setField("optional_deadline", e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2
                             focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-100
                             transition-colors"
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
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Notes</label>
                <textarea
                  value={editForm.notes}
                  onChange={(e) => setField("notes", e.target.value)}
                  rows={3}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2
                             focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-100
                             transition-colors resize-none"
                  placeholder="Optional notes…"
                />
              </div>

              {/* Save / Cancel */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleEditSave}
                  disabled={isBusy}
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium
                             text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {updateMutation.isPending ? "Saving…" : "Save changes"}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs
                             text-gray-600 hover:bg-gray-50 transition-colors"
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
                    <dt className="text-gray-400">Deadline</dt>
                    <dd className="text-gray-700">{task.optional_deadline}</dd>
                  </>
                )}
                {task.estimated_duration_minutes && (
                  <>
                    <dt className="text-gray-400">Estimated</dt>
                    <dd className="text-gray-700">{formatDuration(task.estimated_duration_minutes)}</dd>
                  </>
                )}
                {task.is_off_hours_allowed && task.type === "work" && (
                  <>
                    <dt className="text-gray-400">Off-hours</dt>
                    <dd className="text-gray-700">Allowed</dd>
                  </>
                )}
                {task.is_workday_allowed && task.type === "personal" && (
                  <>
                    <dt className="text-gray-400">Workday</dt>
                    <dd className="text-gray-700">Allowed</dd>
                  </>
                )}
                {task.part_of_task_id && (
                  <>
                    <dt className="text-gray-400">Part of</dt>
                    <dd className="text-gray-700">Task #{task.part_of_task_id}</dd>
                  </>
                )}
              </dl>

              {task.notes && (
                <p className="text-xs text-gray-600 whitespace-pre-wrap border-t border-gray-100 pt-2">
                  {task.notes}
                </p>
              )}

              {/* Linked calendar event */}
              <div>
                <p className="text-xs text-gray-400 mb-1.5">Linked Calendar Event</p>
                <LinkedEventSection
                  task={task}
                  onLink={handleLinkEvent}
                  onUnlink={handleUnlinkEvent}
                />
              </div>
            </div>
          )}

          {/* Actions (always visible in expanded view) */}
          {!editing && (
            <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-gray-100">
              {task.status !== "done" && task.status !== "delegated" && (
                <button
                  onClick={() => completeMutation.mutate()}
                  disabled={isBusy}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium
                             text-white hover:bg-emerald-700 disabled:opacity-50
                             transition-colors"
                >
                  {completeMutation.isPending ? "Saving…" : "✓ Done"}
                </button>
              )}

              {task.status !== "delegated" && task.status !== "done" && (
                <button
                  onClick={() => delegateMutation.mutate()}
                  disabled={isBusy}
                  title="Mark as delegated to someone else — cancels any scheduled calendar blocks"
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs
                             text-gray-600 hover:bg-gray-50 disabled:opacity-50
                             transition-colors"
                >
                  {delegateMutation.isPending ? "…" : "Delegate"}
                </button>
              )}

              <button
                onClick={handleEditOpen}
                disabled={isBusy}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs
                           text-gray-600 hover:bg-gray-50 disabled:opacity-50
                           transition-colors"
              >
                Edit
              </button>

              {confirmDelete ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-red-600">Delete?</span>
                  <button
                    onClick={() => deleteMutation.mutate()}
                    disabled={isBusy}
                    className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium
                               text-white hover:bg-red-700 disabled:opacity-50
                               transition-colors"
                  >
                    Yes, delete
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs
                               text-gray-600 hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDelete(true)}
                  disabled={isBusy}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs
                             text-red-500 hover:bg-red-50 hover:border-red-200
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
