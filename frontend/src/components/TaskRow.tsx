/**
 * TaskRow — single row in the backlog list.
 *
 * Supports:
 *  - Drag-and-drop via dnd-kit (drag handle on left)
 *  - Click anywhere on the row body to expand inline details
 *  - Inline actions: Complete, Delegate, Delete
 *  - Procrastination flag indicator
 */

import { useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { format, parseISO, differenceInDays } from "date-fns";
import clsx from "clsx";
import { tasksApi } from "../services/tasks";
import type { Task } from "../types";

// ── Badges ────────────────────────────────────────────────────────────────────

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

function StatusBadge({ status }: { status: Task["status"] }) {
  const styles: Record<Task["status"], string> = {
    backlog: "bg-gray-100 text-gray-500",
    scheduled: "bg-green-100 text-green-700",
    tentatively_done: "bg-yellow-100 text-yellow-700",
    done: "bg-emerald-100 text-emerald-700",
    delegated: "bg-slate-100 text-slate-500",
  };
  const labels: Record<Task["status"], string> = {
    backlog: "Backlog",
    scheduled: "Scheduled",
    tentatively_done: "Review",
    done: "Done",
    delegated: "Delegated",
  };
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs",
        styles[status]
      )}
    >
      {labels[status]}
    </span>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDuration(mins: number | null) {
  if (!mins) return null;
  if (mins < 60) return `${mins}m`;
  const h = mins / 60;
  return `${h === Math.floor(h) ? h : h.toFixed(1)}h`;
}

function formatScheduledDate(iso: string | null) {
  if (!iso) return null;
  try {
    const d = parseISO(iso);
    const today = new Date();
    const diff = differenceInDays(d, today);
    if (diff === 0) return "Today";
    if (diff === 1) return "Tomorrow";
    if (diff < 7) return format(d, "EEE");
    return format(d, "MMM d");
  } catch {
    return null;
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  task: Task;
  isDraggable?: boolean;
}

export function TaskRow({ task, isDraggable = true }: Props) {
  const [expanded, setExpanded] = useState(false);
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

  const isBusy =
    completeMutation.isPending ||
    delegateMutation.isPending ||
    deleteMutation.isPending;

  const scheduledLabel = formatScheduledDate(task.next_scheduled_start);
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
          onClick={() => setExpanded((v) => !v)}
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
                  title="Procrastination flag"
                >
                  ⚠
                </span>
              )}
            </div>
            <div className="flex items-center flex-wrap gap-x-2 gap-y-1">
              <TypeBadge type={task.type} />
              <StatusBadge status={task.status} />
              {durationLabel && (
                <span className="text-xs text-gray-400">~{durationLabel}</span>
              )}
              {scheduledLabel && (
                <span className="text-xs text-green-600 font-medium">
                  {scheduledLabel}
                </span>
              )}
              {!scheduledLabel && task.status === "backlog" && (
                <span className="text-xs text-gray-300">Unscheduled</span>
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
        <div className="border-t border-gray-100 px-4 py-3 ml-10 space-y-3">
          {/* Meta */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            {task.optional_deadline && (
              <>
                <dt className="text-gray-400">Deadline</dt>
                <dd className="text-gray-700">{task.optional_deadline}</dd>
              </>
            )}
            {task.notes && (
              <>
                <dt className="text-gray-400 col-span-2">Notes</dt>
                <dd className="text-gray-700 col-span-2 whitespace-pre-wrap">
                  {task.notes}
                </dd>
              </>
            )}
            <dt className="text-gray-400">Off-hours OK</dt>
            <dd className="text-gray-700">{task.is_off_hours_allowed ? "Yes" : "No"}</dd>
            {task.part_of_task_id && (
              <>
                <dt className="text-gray-400">Part of</dt>
                <dd className="text-gray-700">Task #{task.part_of_task_id}</dd>
              </>
            )}
          </dl>

          {/* Actions */}
          <div className="flex items-center gap-2 flex-wrap">
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
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs
                           text-gray-600 hover:bg-gray-50 disabled:opacity-50
                           transition-colors"
              >
                {delegateMutation.isPending ? "…" : "Delegate"}
              </button>
            )}

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
        </div>
      )}
    </div>
  );
}
