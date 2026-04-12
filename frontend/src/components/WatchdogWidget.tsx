/**
 * WatchdogWidget — collapsible list of procrastination-flagged tasks.
 *
 * Shown when the nightly ARQ cron has flagged tasks that have been in the
 * backlog for more than WATCHDOG_THRESHOLD_DAYS without progress.
 *
 * Per-task actions: Done | Delegate | Delete
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { differenceInDays, parseISO } from "date-fns";
import clsx from "clsx";
import { watchdogApi } from "../services/watchdog";
import { tasksApi } from "../services/tasks";

export function WatchdogWidget() {
  const [open, setOpen] = useState(true);
  const queryClient = useQueryClient();

  const { data: tasks = [] } = useQuery({
    queryKey: ["watchdog"],
    queryFn: watchdogApi.list,
    staleTime: 60_000,
  });

  if (tasks.length === 0) return null;

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["watchdog"] });
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3
                   hover:bg-amber-100/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm">⚠️</span>
          <span className="text-sm font-medium text-amber-900">
            Stalled tasks
          </span>
          <span className="rounded-full bg-amber-200 px-1.5 py-0.5 text-xs font-medium text-amber-800">
            {tasks.length}
          </span>
        </div>
        <svg
          className={clsx(
            "w-4 h-4 text-amber-500 transition-transform",
            open && "rotate-180"
          )}
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-amber-200 divide-y divide-amber-100">
          {tasks.map((task) => {
            const days = differenceInDays(
              new Date(),
              parseISO(task.created_at)
            );

            return (
              <WatchdogTaskRow
                key={task.id}
                taskId={task.id}
                title={task.title}
                days={days}
                onAction={invalidate}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Row ───────────────────────────────────────────────────────────────────────

interface RowProps {
  taskId: number;
  title: string;
  days: number;
  onAction: () => void;
}

function WatchdogTaskRow({ taskId, title, days, onAction }: RowProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const completeMutation = useMutation({
    mutationFn: () => tasksApi.complete(taskId, {}),
    onSuccess: onAction,
  });

  const delegateMutation = useMutation({
    mutationFn: () => tasksApi.delegate(taskId),
    onSuccess: onAction,
  });

  const deleteMutation = useMutation({
    mutationFn: () => tasksApi.delete(taskId),
    onSuccess: onAction,
  });

  const isBusy =
    completeMutation.isPending ||
    delegateMutation.isPending ||
    deleteMutation.isPending;

  return (
    <div className="px-4 py-3 space-y-2">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-800 font-medium leading-snug">{title}</p>
          <p className="text-xs text-amber-600 mt-0.5">
            Stalled for {days} day{days !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {confirmDelete ? (
        <div className="flex items-center gap-2">
          <span className="text-xs text-red-600">Delete this task?</span>
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={isBusy}
            className="rounded-lg bg-red-600 px-3 py-1 text-xs font-medium text-white
                       hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            Yes, delete
          </button>
          <button
            onClick={() => setConfirmDelete(false)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1 text-xs
                       text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={() => completeMutation.mutate()}
            disabled={isBusy}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white
                       hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {completeMutation.isPending ? "…" : "Done"}
          </button>
          <button
            onClick={() => delegateMutation.mutate()}
            disabled={isBusy}
            className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs
                       text-gray-700 hover:bg-amber-50 disabled:opacity-50 transition-colors"
          >
            {delegateMutation.isPending ? "…" : "Delegate"}
          </button>
          <button
            onClick={() => setConfirmDelete(true)}
            disabled={isBusy}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs
                       text-red-500 hover:bg-red-50 hover:border-red-200
                       disabled:opacity-50 transition-colors"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
