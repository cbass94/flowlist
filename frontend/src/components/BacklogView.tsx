/**
 * BacklogView — the primary task list.
 *
 * Active tasks (non-done, non-delegated) are sortable via dnd-kit.
 * Delegated tasks appear in a collapsed section at the bottom.
 * Reorders are debounced on the server side (the tasks router handles it).
 */

import { useState } from "react";
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

  const activeTasks = allTasks.filter((t) => ACTIVE_STATUSES.has(t.status));
  const delegatedTasks = allTasks.filter((t) => t.status === "delegated");

  // Local task order for optimistic DnD updates
  const [localOrder, setLocalOrder] = useState<number[] | null>(null);

  const displayedActive = localOrder
    ? localOrder
        .map((id) => activeTasks.find((t) => t.id === id))
        .filter((t): t is Task => !!t)
    : activeTasks;

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
            className="h-16 rounded-xl bg-gray-100 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
        Failed to load tasks. Please refresh.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Active task list */}
      {displayedActive.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-200 px-4 py-10
                        text-center text-sm text-gray-400">
          No tasks yet — add one above!
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
              {displayedActive.map((task) => (
                <TaskRow key={task.id} task={task} isDraggable />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Delegated section */}
      {delegatedTasks.length > 0 && (
        <div className="pt-2">
          <button
            onClick={() => setDelegatedOpen((v) => !v)}
            className="flex items-center gap-2 w-full px-1 py-2 text-sm text-gray-400
                       hover:text-gray-600 transition-colors"
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
            <span className="ml-1 rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
              {delegatedTasks.length}
            </span>
          </button>

          {delegatedOpen && (
            <div className="space-y-1.5 mt-1">
              {delegatedTasks.map((task) => (
                <TaskRow key={task.id} task={task} isDraggable={false} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
