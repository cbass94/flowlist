// Archive page — completed and delegated tasks with Work/Personal filter.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { archiveApi } from "../services/archive";
import { format, formatDistanceToNow, parseISO } from "date-fns";
import clsx from "clsx";
import type { Task, TaskType } from "../types";

function formatDuration(minutes: number | null): string {
  if (minutes == null) return "--";
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function AccuracyBadge({
  estimated,
  actual,
}: {
  estimated: number;
  actual: number;
}) {
  const diff = actual - estimated;
  const pct = Math.round((diff / estimated) * 100);
  const isAccurate = Math.abs(diff) <= 15;
  const isOver = diff > 0;

  return (
    <div className="text-right">
      <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{formatDuration(actual)}</p>
      <p
        className={clsx(
          "text-xs",
          isAccurate ? "text-green-500" : isOver ? "text-orange-500" : "text-blue-400"
        )}
      >
        est {formatDuration(estimated)}
        {" "}
        {isAccurate ? "✓" : isOver ? `+${diff}m` : `${diff}m`}
        {!isAccurate && <span className="ml-0.5 opacity-70">({isOver ? `+${pct}%` : `${pct}%`})</span>}
      </p>
    </div>
  );
}

function TaskArchiveRow({ task }: { task: Task }) {
  const [expanded, setExpanded] = useState(false);

  const isDone = task.status === "done";
  const statusLabel = isDone ? "Done" : "Delegated";
  const statusColor = isDone
    ? "text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950"
    : "text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950";

  const typeColor =
    task.type === "work"
      ? "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950"
      : "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950";

  const completedAt = task.completed_at
    ? formatDistanceToNow(parseISO(task.completed_at), { addSuffix: true })
    : task.updated_at
    ? formatDistanceToNow(parseISO(task.updated_at), { addSuffix: true })
    : null;

  const completedAtFull = task.completed_at
    ? format(parseISO(task.completed_at), "MMM d, yyyy 'at' h:mm a")
    : null;

  return (
    <div
      className={clsx(
        "transition-colors",
        expanded ? "bg-gray-50/50 dark:bg-gray-800/50" : "hover:bg-gray-50 dark:hover:bg-gray-800/30"
      )}
    >
      {/* Compact row — click to expand */}
      <button
        className="w-full px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-800 dark:text-gray-100 font-medium">{task.title}</p>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className={`text-xs px-1.5 py-0.5 rounded-md font-medium ${typeColor}`}>
                {task.type}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded-md font-medium ${statusColor}`}>
                {statusLabel}
              </span>
              {completedAt && (
                <span className="text-xs text-gray-400 dark:text-gray-500">{completedAt}</span>
              )}
            </div>
          </div>
          <div className="shrink-0 flex items-start gap-2">
            {task.actual_duration_minutes != null && task.estimated_duration_minutes != null ? (
              <AccuracyBadge
                estimated={task.estimated_duration_minutes}
                actual={task.actual_duration_minutes}
              />
            ) : task.actual_duration_minutes != null ? (
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                {formatDuration(task.actual_duration_minutes)}
              </p>
            ) : task.estimated_duration_minutes != null ? (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                est {formatDuration(task.estimated_duration_minutes)}
              </p>
            ) : null}
            <svg
              className={clsx(
                "w-4 h-4 text-gray-300 dark:text-gray-600 shrink-0 mt-0.5 transition-transform",
                expanded && "rotate-180"
              )}
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              <path
                d="M4 6l4 4 4-4"
                stroke="currentColor"
                strokeWidth="1.5"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs mt-3">
            {completedAtFull && (
              <>
                <dt className="text-gray-400 dark:text-gray-500">{isDone ? "Completed" : "Delegated"}</dt>
                <dd className="text-gray-700 dark:text-gray-200">{completedAtFull}</dd>
              </>
            )}
            {task.optional_deadline && (
              <>
                <dt className="text-gray-400 dark:text-gray-500">Deadline</dt>
                <dd className="text-gray-700 dark:text-gray-200">{task.optional_deadline}</dd>
              </>
            )}
            {task.estimated_duration_minutes != null && (
              <>
                <dt className="text-gray-400 dark:text-gray-500">Estimated</dt>
                <dd className="text-gray-700 dark:text-gray-200">{formatDuration(task.estimated_duration_minutes)}</dd>
              </>
            )}
            {task.actual_duration_minutes != null && (
              <>
                <dt className="text-gray-400 dark:text-gray-500">Actual</dt>
                <dd
                  className={clsx(
                    "font-medium",
                    task.estimated_duration_minutes
                      ? Math.abs(task.actual_duration_minutes - task.estimated_duration_minutes) <= 15
                        ? "text-green-600 dark:text-green-400"
                        : task.actual_duration_minutes > task.estimated_duration_minutes
                        ? "text-orange-500"
                        : "text-blue-500 dark:text-blue-400"
                      : "text-gray-700 dark:text-gray-200"
                  )}
                >
                  {formatDuration(task.actual_duration_minutes)}
                </dd>
              </>
            )}
            {task.part_of_task_id && (
              <>
                <dt className="text-gray-400 dark:text-gray-500">Part of</dt>
                <dd className="text-gray-700 dark:text-gray-200">Task #{task.part_of_task_id}</dd>
              </>
            )}
            {task.linked_calendar_event_title && (
              <>
                <dt className="text-gray-400 dark:text-gray-500">Linked event</dt>
                <dd className="text-gray-700 dark:text-gray-200 truncate">{task.linked_calendar_event_title}</dd>
              </>
            )}
          </dl>
          {task.description && (
            <p className="mt-2 text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap border-t border-gray-100 dark:border-gray-800 pt-2">
              {task.description}
            </p>
          )}
          {task.estimated_duration_minutes && task.actual_duration_minutes && (
            <div className="mt-3 border-t border-gray-100 dark:border-gray-800 pt-2">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Estimation accuracy</p>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                  <div
                    className={clsx(
                      "h-full rounded-full transition-all",
                      Math.abs(task.actual_duration_minutes - task.estimated_duration_minutes) <= 15
                        ? "bg-green-400"
                        : task.actual_duration_minutes > task.estimated_duration_minutes
                        ? "bg-orange-400"
                        : "bg-blue-400"
                    )}
                    style={{
                      width: `${Math.min(
                        100,
                        Math.max(
                          10,
                          100 - Math.abs(
                            ((task.actual_duration_minutes - task.estimated_duration_minutes) /
                              task.estimated_duration_minutes) *
                              100
                          )
                        )
                      )}%`,
                    }}
                  />
                </div>
                <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
                  {Math.abs(task.actual_duration_minutes - task.estimated_duration_minutes) <= 15
                    ? "On target"
                    : task.actual_duration_minutes > task.estimated_duration_minutes
                    ? `Ran over by ${task.actual_duration_minutes - task.estimated_duration_minutes}m`
                    : `Finished ${task.estimated_duration_minutes - task.actual_duration_minutes}m early`}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ArchivePage() {
  const [typeFilter, setTypeFilter] = useState<TaskType | undefined>(undefined);

  const { data: tasks, isLoading, isError, refetch } = useQuery({
    queryKey: ["archive", typeFilter],
    queryFn: () => archiveApi.list({ type: typeFilter }),
    staleTime: 30_000,
  });

  const workCount = tasks?.filter((t) => t.type === "work").length ?? 0;
  const personalCount = tasks?.filter((t) => t.type === "personal").length ?? 0;
  const doneCount = tasks?.filter((t) => t.status === "done").length ?? 0;
  const delegatedCount = tasks?.filter((t) => t.status === "delegated").length ?? 0;

  return (
    <div className="space-y-5 pb-16">
      {/* Filter tabs */}
      <div className="flex items-center gap-0.5 bg-gray-100/80 dark:bg-gray-800/80 rounded-lg p-0.5 self-start">
        {(
          [
            { label: "All", value: undefined },
            { label: "Work", value: "work" },
            { label: "Personal", value: "personal" },
          ] as { label: string; value: TaskType | undefined }[]
        ).map((opt) => (
          <button
            key={opt.label}
            onClick={() => setTypeFilter(opt.value)}
            className={`px-4 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-150 ${
              typeFilter === opt.value
                ? "bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 shadow-sm shadow-gray-200/60 dark:shadow-black/20 ring-1 ring-gray-950/[0.04] dark:ring-white/[0.04]"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white/60 dark:hover:bg-gray-700/60"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Stats row */}
      {tasks && tasks.length > 0 && (
        <div className="flex gap-4 text-xs text-gray-500 dark:text-gray-400">
          <span>{tasks.length} tasks</span>
          <span>{doneCount} done</span>
          {delegatedCount > 0 && <span>{delegatedCount} delegated</span>}
          {typeFilter == null && (
            <>
              <span>{workCount} work</span>
              <span>{personalCount} personal</span>
            </>
          )}
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-700/60 shadow-sm shadow-gray-100 dark:shadow-black/20 px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
          Loading...
        </div>
      ) : isError ? (
        <div className="bg-red-50 dark:bg-red-950 border border-red-100 dark:border-red-900 rounded-2xl px-4 py-6 text-center">
          <p className="text-red-600 dark:text-red-400 text-sm font-medium">Failed to load archive</p>
          <button
            onClick={() => refetch()}
            className="mt-2 text-xs text-red-500 dark:text-red-400 underline"
          >
            Retry
          </button>
        </div>
      ) : tasks && tasks.length > 0 ? (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-700/60 shadow-sm shadow-gray-100 dark:shadow-black/20 divide-y divide-gray-100 dark:divide-gray-800 overflow-hidden">
          {tasks.map((task) => (
            <TaskArchiveRow key={task.id} task={task} />
          ))}
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-700/60 shadow-sm shadow-gray-100 dark:shadow-black/20 px-4 py-12 text-center">
          <p className="text-gray-400 dark:text-gray-500 text-sm">No completed tasks yet.</p>
          <p className="text-gray-300 dark:text-gray-600 text-xs mt-1">
            Finished tasks will appear here.
          </p>
        </div>
      )}
    </div>
  );
}
