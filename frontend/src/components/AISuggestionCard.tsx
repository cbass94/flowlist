/**
 * AISuggestionCard
 *
 * Shows the AI's parsed task suggestion in an editable confirmation card.
 * States:
 *   "loading"  — skeleton placeholders while Claude processes
 *   "ready"    — AI fields populated; all fields editable before confirming
 *   "fallback" — AI unavailable; user fills in fields manually
 *
 * Calls onConfirm with a ready-to-submit TaskCreate payload.
 */

import { useEffect, useState } from "react";
import clsx from "clsx";
import type {
  AISuggestion,
  ConfidenceLevel,
  PriorityLevel,
  TaskCreate,
  TaskType,
} from "../types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return (
    <div className={clsx("animate-pulse rounded bg-gray-200", className)} />
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="block text-xs font-medium text-gray-500 mb-1">
      {children}
    </span>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer select-none">
      <div
        className={clsx(
          "relative w-9 h-5 rounded-full transition-colors",
          checked ? "bg-blue-600" : "bg-gray-200"
        )}
        onClick={() => onChange(!checked)}
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && onChange(!checked)}
      >
        <div
          className={clsx(
            "absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform",
            checked && "translate-x-4"
          )}
        />
      </div>
      <span className="text-sm text-gray-700">{label}</span>
    </label>
  );
}

const PRIORITY_OPTIONS: {
  value: PriorityLevel;
  label: string;
}[] = [
  { value: "top", label: "Top priority" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const CONFIDENCE_STYLE: Record<ConfidenceLevel, string> = {
  high: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
  low: "bg-gray-50 text-gray-500 border-gray-200",
};

// ── State ─────────────────────────────────────────────────────────────────────

interface EditState {
  title: string;
  type: TaskType;
  suggested_priority: PriorityLevel;
  estimated_duration_minutes: number;
  reasoning: string;
  confidence: ConfidenceLevel;
  keywords: string[];
  // Optional fields
  deadline: string;
  duration_override_hours: string;
  is_off_hours_allowed: boolean;
  is_workday_allowed: boolean;
}

function initEditState(raw: string, suggestion?: AISuggestion): EditState {
  return {
    title: suggestion?.title ?? raw,
    type: suggestion?.type ?? "work",
    suggested_priority: suggestion?.suggested_priority ?? "medium",
    estimated_duration_minutes: suggestion?.estimated_duration_minutes ?? 60,
    reasoning: suggestion?.reasoning ?? "",
    confidence: suggestion?.confidence ?? "low",
    keywords: suggestion?.keywords ?? [],
    deadline: suggestion?.optional_deadline_detected ?? "",
    duration_override_hours: "",
    is_off_hours_allowed: false,
    is_workday_allowed: false,
  };
}

// ── Main component ────────────────────────────────────────────────────────────

export type CardStatus = "loading" | "ready" | "fallback";

interface Props {
  status: CardStatus;
  rawText: string;
  suggestion?: AISuggestion;
  onConfirm: (task: TaskCreate) => void;
  onCancel: () => void;
  isSaving?: boolean;
}

export function AISuggestionCard({
  status,
  rawText,
  suggestion,
  onConfirm,
  onCancel,
  isSaving = false,
}: Props) {
  const [state, setState] = useState<EditState>(() =>
    initEditState(rawText, suggestion)
  );
  const [showOptional, setShowOptional] = useState(false);

  // Populate fields when AI response arrives
  useEffect(() => {
    if (suggestion) {
      setState(initEditState(rawText, suggestion));
    }
  }, [suggestion, rawText]);

  function set<K extends keyof EditState>(key: K, value: EditState[K]) {
    setState((prev) => ({ ...prev, [key]: value }));
  }

  const isLoading = status === "loading";
  const isFallback = status === "fallback";

  function handleSave() {
    if (isLoading || isSaving) return;

    const overrideMins = state.duration_override_hours
      ? Math.max(15, Math.round(parseFloat(state.duration_override_hours) * 60))
      : state.estimated_duration_minutes;

    const task: TaskCreate = {
      title: state.title.trim() || rawText,
      type: state.type,
      estimated_duration_minutes: overrideMins || undefined,
      optional_user_estimate: rawText,
      optional_deadline: state.deadline || undefined,
      is_off_hours_allowed: state.is_off_hours_allowed,
      is_workday_allowed: state.is_workday_allowed,
      ai_suggested_priority: state.suggested_priority,
      ai_confidence: state.confidence,
      ai_keywords: state.keywords,
    };
    onConfirm(task);
  }

  function formatMinutes(mins: number) {
    if (mins < 60) return `${mins}m`;
    const h = mins / 60;
    return h === Math.floor(h) ? `${h}h` : `${h.toFixed(1)}h`;
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 bg-gray-50/60">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-800">
            {isFallback ? "Add task" : "AI suggestion"}
          </span>
          {!isLoading && !isFallback && (
            <span
              className={clsx(
                "inline-flex items-center rounded-full border px-2 py-0.5 text-xs",
                CONFIDENCE_STYLE[state.confidence]
              )}
            >
              {state.confidence} confidence
            </span>
          )}
          {isFallback && (
            <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-500">
              AI unavailable
            </span>
          )}
        </div>
        <button
          onClick={onCancel}
          className="text-gray-400 hover:text-gray-600 transition-colors p-1 -m-1"
          aria-label="Cancel"
        >
          <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
            <path d="M4.22 4.22a.75.75 0 0 1 1.06 0L8 6.94l2.72-2.72a.75.75 0 1 1 1.06 1.06L9.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L8 9.06l-2.72 2.72a.75.75 0 0 1-1.06-1.06L6.94 8 4.22 5.28a.75.75 0 0 1 0-1.06Z" />
          </svg>
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Title */}
        <div>
          <Label>Title</Label>
          <input
            type="text"
            value={state.title}
            onChange={(e) => set("title", e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                       focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100
                       transition-colors"
            placeholder="Task title"
          />
        </div>

        {/* Type + Priority */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Type</Label>
            {isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : (
              <div className="flex rounded-lg border border-gray-200 overflow-hidden">
                {(["work", "personal"] as TaskType[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => set("type", t)}
                    className={clsx(
                      "flex-1 py-2 text-xs font-medium capitalize transition-colors",
                      state.type === t
                        ? "bg-blue-600 text-white"
                        : "bg-white text-gray-600 hover:bg-gray-50"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <Label>Priority</Label>
            {isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : (
              <select
                value={state.suggested_priority}
                onChange={(e) =>
                  set("suggested_priority", e.target.value as PriorityLevel)
                }
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2
                           text-xs focus:border-blue-400 focus:outline-none focus:ring-2
                           focus:ring-blue-100 transition-colors"
              >
                {PRIORITY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {/* AI estimate + reasoning */}
        {!isFallback && (
          <div className="rounded-lg bg-blue-50/60 border border-blue-100 px-3 py-2.5 space-y-1">
            {isLoading ? (
              <div className="space-y-1.5">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="h-3.5 w-full" />
                <Skeleton className="h-3.5 w-3/4" />
              </div>
            ) : (
              <>
                <div className="text-xs font-medium text-blue-700">
                  ~{formatMinutes(state.estimated_duration_minutes)} estimated
                </div>
                <p className="text-xs text-blue-600/80 leading-relaxed">
                  {state.reasoning}
                </p>
              </>
            )}
          </div>
        )}

        {isFallback && (
          <p className="rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-xs text-amber-700">
            AI is temporarily unavailable. Fill in the details and save manually.
          </p>
        )}

        {/* Optional fields toggle */}
        {!isLoading && (
          <button
            onClick={() => setShowOptional((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600
                       transition-colors"
          >
            <svg
              className={clsx(
                "w-3 h-3 transition-transform",
                showOptional && "rotate-90"
              )}
              viewBox="0 0 12 12"
              fill="currentColor"
            >
              <path d="M4.5 2L8.5 6L4.5 10" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {showOptional ? "Hide options" : "More options"}
          </button>
        )}

        {/* Optional fields */}
        {showOptional && !isLoading && (
          <div className="space-y-4 pt-1 border-t border-gray-100">
            <div className="grid grid-cols-2 gap-3">
              {/* Deadline */}
              <div>
                <Label>
                  Deadline{" "}
                  {state.deadline && (
                    <span className="text-blue-500 font-normal normal-case">
                      detected
                    </span>
                  )}
                </Label>
                <input
                  type="date"
                  value={state.deadline}
                  onChange={(e) => set("deadline", e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                             focus:border-blue-400 focus:outline-none focus:ring-2
                             focus:ring-blue-100 transition-colors"
                />
              </div>

              {/* Manual duration override */}
              <div>
                <Label>My time estimate (hrs)</Label>
                <input
                  type="number"
                  min={0.5}
                  max={8}
                  step={0.5}
                  value={state.duration_override_hours}
                  onChange={(e) =>
                    set("duration_override_hours", e.target.value)
                  }
                  placeholder={`AI: ${formatMinutes(state.estimated_duration_minutes)}`}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm
                             placeholder-gray-400 focus:border-blue-400 focus:outline-none
                             focus:ring-2 focus:ring-blue-100 transition-colors"
                />
              </div>
            </div>

            {/* Constraint toggles */}
            <div className="space-y-3">
              {state.type === "work" && (
                <Toggle
                  checked={state.is_off_hours_allowed}
                  onChange={(v) => set("is_off_hours_allowed", v)}
                  label="Allow scheduling outside work hours"
                />
              )}
              {state.type === "personal" && (
                <Toggle
                  checked={state.is_workday_allowed}
                  onChange={(v) => set("is_workday_allowed", v)}
                  label="Allow scheduling during work hours"
                />
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-4 py-3">
        <button
          onClick={onCancel}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50
                     transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={isLoading || isSaving}
          className={clsx(
            "rounded-lg px-4 py-1.5 text-sm font-medium text-white transition-colors",
            !isLoading && !isSaving
              ? "bg-blue-600 hover:bg-blue-700"
              : "bg-blue-300 cursor-not-allowed"
          )}
        >
          {isSaving ? "Saving…" : isLoading ? "Analysing…" : "Save Task"}
        </button>
      </div>
    </div>
  );
}
