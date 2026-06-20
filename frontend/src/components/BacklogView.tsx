/**
 * BacklogView — the primary task list.
 *
 * Active tasks (non-done, non-delegated) are sortable via dnd-kit.
 * Delegated tasks appear in a collapsed section at the bottom.
 * Reorders are debounced on the server side (the tasks router handles it).
 */

import { useState } from "react";
import { parseISO } from "date-fns";
import {
  DndContext,
  DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { tasksApi } from "../services/tasks";
import { TaskRow } from "./TaskRow";
import type { Task } from "../types";

const ACTIVE_STATUSES = new Set(["backlog", "scheduled", "tentatively_done"]);

export function BacklogView() {
  const queryClient = useQueryClient();
  const [delegatedOpen, setDelegatedOpen] = useState(false);

  const { data: allTasks = [], isLoading, isError } = useQuery({
    queryKey: ["tasks"],
    queryFn: tasksApi.list,
    staleTime: 30_000,
  });

  const [search, setSearch] = useState("");

  const matchesSearch = (t: Task) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      t.title.toLowerCase().includes(q) ||
      (t.description && t.description.toLowerCase().includes(q))
    );
  };

  const activeTasks = allTasks.filter((t) => ACTIVE_STATUSES.has(t.status));
  const delegatedTasks = allTasks.filter((t) => t.status === "delegated");

  const filteredActive = activeTasks.filter(matchesSearch);
  const filteredDelegated = delegatedTasks.filter(matchesSearch);

  const now = new Date();
  const overdueTasks = activeTasks.filter((t) => {
    if (t.status !== "scheduled" && t.status !== "tentatively_done") return false;
    return (t.blocks ?? []).some((b) => parseISO(b.start_at) <= now);
  });

  const rescheduleAllOverdueMutation = useMutation({
    mutationFn: () => tasksApi.rescheduleAllOverdue(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  // Local task order for optimistic DnD updates
  const [localOrder, setLocalOrder] = useState<number[] | null>(null);

  const displayedActive = localOrder
    ? localOrder
        .map((id) => filteredActive.find((t) => t.id === id))
        .filter((t): t is Task => !!t)
    : filteredActive;

  const reorderMutation = useMutation({
    mutationFn: (ids: number[]) =>
      tasksApi.reorder({ ordered_task_ids: ids }),
    onMutate: (ids) => {
      setLocalOrder(ids);
    },
    onSuccess: () => {
      setLocalOrder(null);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: () => {
      setLocalOrder(null);
    },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 }, // prevents drag on normal click
    }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 200, tolerance: 8 }, // hold before drag on mobile
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const ids = displayedActive.map((t) => t.id);
    const oldIndex = ids.indexOf(active.id as number);
    const newIndex = ids.indexOf(over.id as number);
    if (oldIndex === -1 || newIndex === -1) return;

    const newIds = arrayMove(ids, oldIndex, newIndex);
    reorderMutation.mutate(newIds);
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="h-16 rounded-xl bg-gray-100/80 dark:bg-gray-800/80 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-red-100 dark:border-red-900 bg-red-50 dark:bg-red-950 px-4 py-3 text-sm text-red-600 dark:text-red-400">
        Failed to load tasks. Please refresh.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Search bar */}
      {allTasks.length > 0 && (
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="7" cy="7" r="4.5" />
            <path d="M10.5 10.5L14 14" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks..."
            className="w-full rounded-xl border border-gray-200/80 dark:border-gray-700/80 bg-white dark:bg-gray-900 pl-9 pr-8 py-2.5
                       text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 shadow-sm shadow-gray-100 dark:shadow-black/20
                       focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-blue-500/20
                       transition-all duration-150"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500
                         hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-0.5"
              aria-label="Clear search"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
                <path d="M4.22 4.22a.75.75 0 0 1 1.06 0L8 6.94l2.72-2.72a.75.75 0 1 1 1.06 1.06L9.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L8 9.06l-2.72 2.72a.75.75 0 0 1-1.06-1.06L6.94 8 4.22 5.28a.75.75 0 0 1 0-1.06Z" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Overdue tasks banner */}
      {overdueTasks.length > 0 && !search.trim() && (
        <div className="rounded-xl border border-orange-200 dark:border-orange-800 bg-orange-50/60 dark:bg-orange-950/60 px-4 py-3 space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <svg className="w-4 h-4 text-orange-500 shrink-0" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4.5V8l2 1.5" stroke="currentColor" strokeWidth="1.5"
                      strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-sm font-medium text-orange-800 dark:text-orange-200">
                {overdueTasks.length === 1
                  ? "1 task missed its time block"
                  : `${overdueTasks.length} tasks missed their time blocks`}
              </span>
            </div>
            <button
              onClick={() => rescheduleAllOverdueMutation.mutate()}
              disabled={rescheduleAllOverdueMutation.isPending}
              className="shrink-0 rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-medium
                         text-white hover:bg-orange-700 active:scale-[0.97]
                         disabled:opacity-50 transition-all duration-150"
            >
              {rescheduleAllOverdueMutation.isPending
                ? "Rescheduling…"
                : overdueTasks.length === 1 ? "Reschedule" : "Reschedule All"}
            </button>
          </div>
          {overdueTasks.length > 1 && (
            <ul className="space-y-0.5 pl-6">
              {overdueTasks.map((t) => (
                <li key={t.id} className="text-xs text-orange-700 dark:text-orange-300 truncate">{t.title}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Active task list */}
      {displayedActive.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-200/80 dark:border-gray-700/80 px-4 py-10
                        text-center text-sm text-gray-400 dark:text-gray-500">
          {search.trim() ? "No tasks match your search." : "No tasks yet — add one above!"}
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={displayedActive.map((t) => t.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-1.5">
              {displayedActive.map((task, index) => (
                <TaskRow key={task.id} task={task} isDraggable position={index + 1} />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Delegated section */}
      {filteredDelegated.length > 0 && (
        <div className="pt-2">
          <button
            onClick={() => setDelegatedOpen((v) => !v)}
            className="flex items-center gap-2 w-full px-1 py-2 text-sm text-gray-400 dark:text-gray-500
                       hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <svg
              className={clsx(
                "w-3.5 h-3.5 transition-transform",
                delegatedOpen && "rotate-90"
              )}
              viewBox="0 0 14 14"
              fill="currentColor"
            >
              <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Delegated
            <span className="ml-1 rounded-full bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 text-xs text-gray-500 dark:text-gray-400">
              {filteredDelegated.length}
            </span>
          </button>

          {delegatedOpen && (
            <div className="space-y-1.5 mt-1">
              {filteredDelegated.map((task) => (
                <TaskRow key={task.id} task={task} isDraggable={false} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
