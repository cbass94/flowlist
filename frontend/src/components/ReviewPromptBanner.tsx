/**
 * ReviewPromptBanner
 *
 * Shown at the top of the screen when there are tasks in tentatively_done status.
 * Presents one at a time. Actions:
 *   - "Yes, Done ✓" → confirm complete
 *   - "Not quite — reschedule" → create Part 2 with editable title
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { reviewPromptsApi } from "../services/reviewPrompts";
import type { Task } from "../types";

type BannerState =
  | { mode: "prompt" }
  | { mode: "reschedule"; part2Title: string };

function formatPastTime(iso: string | null) {
  if (!iso) return null;
  try {
    return format(parseISO(iso), "EEE MMM d 'at' h:mm a");
  } catch {
    return null;
  }
}

interface SingleBannerProps {
  task: Task;
  onDismiss: () => void;
}

function SingleBanner({ task, onDismiss }: SingleBannerProps) {
  const [state, setState] = useState<BannerState>({ mode: "prompt" });
  const queryClient = useQueryClient();

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["review-prompts"] });
  }

  const confirmMutation = useMutation({
    mutationFn: () => reviewPromptsApi.confirm(task.id, {}),
    onSuccess: invalidate,
  });

  const rescheduleMutation = useMutation({
    mutationFn: (title: string) =>
      reviewPromptsApi
        .reschedule(task.id)
        .then(() => title), // title edit happens client side; Part 2 has its own title
    onSuccess: invalidate,
  });

  const scheduledLabel = formatPastTime(task.next_scheduled_start);

  return (
    <div className="rounded-xl bg-yellow-50 border border-yellow-200 shadow-sm overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className="mt-0.5 shrink-0 w-8 h-8 rounded-full bg-yellow-100 flex items-center
                          justify-center text-yellow-600 text-sm">
            ⏱
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800">{task.title}</p>
            {scheduledLabel && (
              <p className="text-xs text-gray-500 mt-0.5">
                Was scheduled for {scheduledLabel}
              </p>
            )}
          </div>

          {/* Dismiss */}
          <button
            onClick={onDismiss}
            className="text-gray-300 hover:text-gray-500 transition-colors shrink-0 p-1 -m-1"
            aria-label="Skip for now"
          >
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4.22 4.22a.75.75 0 0 1 1.06 0L8 6.94l2.72-2.72a.75.75 0 1 1 1.06 1.06L9.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L8 9.06l-2.72 2.72a.75.75 0 0 1-1.06-1.06L6.94 8 4.22 5.28a.75.75 0 0 1 0-1.06Z" />
            </svg>
          </button>
        </div>

        {/* Actions */}
        {state.mode === "prompt" && (
          <div className="flex items-center gap-2 mt-3 ml-11">
            <button
              onClick={() => confirmMutation.mutate()}
              disabled={confirmMutation.isPending}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white
                         hover:bg-emerald-700 disabled:opacity-50 transition-colors"
            >
              {confirmMutation.isPending ? "Saving…" : "Yes, Done ✓"}
            </button>
            <button
              onClick={() =>
                setState({
                  mode: "reschedule",
                  part2Title: `${task.title} — Part 2`,
                })
              }
              disabled={confirmMutation.isPending}
              className="rounded-lg border border-yellow-300 bg-white px-4 py-2 text-sm
                         text-gray-700 hover:bg-yellow-50 disabled:opacity-50 transition-colors"
            >
              Not quite — reschedule
            </button>
          </div>
        )}

        {state.mode === "reschedule" && (
          <div className="mt-3 ml-11 space-y-2">
            <label className="block text-xs text-gray-500">
              Part 2 title
            </label>
            <input
              type="text"
              value={state.part2Title}
              onChange={(e) =>
                setState((prev) =>
                  prev.mode === "reschedule"
                    ? { ...prev, part2Title: e.target.value }
                    : prev
                )
              }
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                         focus:border-blue-400 focus:outline-none focus:ring-2
                         focus:ring-blue-100 transition-colors"
            />
            <div className="flex gap-2">
              <button
                onClick={() => rescheduleMutation.mutate(state.part2Title)}
                disabled={
                  rescheduleMutation.isPending || !state.part2Title.trim()
                }
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white
                           hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {rescheduleMutation.isPending ? "Saving…" : "Schedule Part 2"}
              </button>
              <button
                onClick={() => setState({ mode: "prompt" })}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600
                           hover:bg-gray-50 transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export function ReviewPromptBanner() {
  const [skipIds, setSkipIds] = useState<Set<number>>(new Set());

  const { data: prompts = [] } = useQuery({
    queryKey: ["review-prompts"],
    queryFn: reviewPromptsApi.list,
    staleTime: 30_000,
  });

  const visible = prompts.filter((p) => !skipIds.has(p.id));
  if (visible.length === 0) return null;

  const current = visible[0];

  return (
    <div className="space-y-2">
      {visible.length > 1 && (
        <p className="text-xs text-gray-400 px-1">
          {visible.length} tasks need review
        </p>
      )}
      <SingleBanner
        key={current.id}
        task={current}
        onDismiss={() =>
          setSkipIds((prev) => new Set([...prev, current.id]))
        }
      />
    </div>
  );
}
