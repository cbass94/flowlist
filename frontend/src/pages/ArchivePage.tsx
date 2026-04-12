// Archive page — completed and delegated tasks with Work/Personal filter.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { archiveApi } from "../services/archive";
import { formatDistanceToNow, parseISO } from "date-fns";
import type { Task, TaskType } from "../types";

function formatDuration(minutes: number | null): string {
  if (minutes == null) return "--";
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function TaskArchiveRow({ task }: { task: Task }) {
  const isDone = task.status === "done";
  const statusLabel = isDone ? "Done" : "Delegated";
  const statusColor = isDone
    ? "text-green-700 bg-green-50"
    : "text-purple-700 bg-purple-50";

  const typeColor =
    task.type === "work"
      ? "text-blue-600 bg-blue-50"
      : "text-teal-600 bg-teal-50";

  const completedAt = task.completed_at
    ? formatDistanceToNow(parseISO(task.completed_at), { addSuffix: true })
    : task.updated_at
    ? formatDistanceToNow(parseISO(task.updated_at), { addSuffix: true })
    : null;

  const estimateAccuracy =
    task.estimated_duration_minutes && task.actual_duration_minutes
      ? task.actual_duration_minutes - task.estimated_duration_minutes
      : null;

  return (
    <div className="px-4 py-3 hover:bg-gray-50 transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-800 font-medium truncate">{task.title}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className={`text-xs px-1.5 py-0.5 rounded-md font-medium ${typeColor}`}>
              {task.type}
            </span>
            <span className={`text-xs px-1.5 py-0.5 rounded-md font-medium ${statusColor}`}>
              {statusLabel}
            </span>
            {completedAt && (
              <span className="text-xs text-gray-400">{completedAt}</span>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          {task.actual_duration_minutes != null ? (
            <div>
              <p className="text-sm font-medium text-gray-700">
                {formatDuration(task.actual_duration_minutes)}
              </p>
              {estimateAccuracy != null && (
                <p
                  className={`text-xs ${
                    Math.abs(estimateAccuracy) <= 15
                      ? "text-green-500"
                      : estimateAccuracy > 0
                      ? "text-orange-500"
                      : "text-blue-400"
                  }`}
                >
                  est {formatDuration(task.estimated_duration_minutes)}
                  {estimateAccuracy > 0 ? ` +${estimateAccuracy}m` : ` ${estimateAccuracy}m`}
                </p>
              )}
            </div>
          ) : task.estimated_duration_minutes != null ? (
            <p className="text-xs text-gray-400">
              est {formatDuration(task.estimated_duration_minutes)}
            </p>
          ) : null}
        </div>
      </div>
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
      <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1 self-start">
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
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              typeFilter === opt.value
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Stats row */}
      {tasks && tasks.length > 0 && (
        <div className="flex gap-4 text-xs text-gray-500">
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
        <div className="bg-white rounded-2xl border border-gray-200 px-4 py-8 text-center text-gray-400 text-sm">
          Loading...
        </div>
      ) : isError ? (
        <div className="bg-red-50 border border-red-200 rounded-2xl px-4 py-6 text-center">
          <p className="text-red-600 text-sm font-medium">Failed to load archive</p>
          <button
            onClick={() => refetch()}
            className="mt-2 text-xs text-red-500 underline"
          >
            Retry
          </button>
        </div>
      ) : tasks && tasks.length > 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {tasks.map((task) => (
            <TaskArchiveRow key={task.id} task={task} />
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 px-4 py-12 text-center">
          <p className="text-gray-400 text-sm">No completed tasks yet.</p>
          <p className="text-gray-300 text-xs mt-1">
            Finished tasks will appear here.
          </p>
        </div>
      )}
    </div>
  );
}
