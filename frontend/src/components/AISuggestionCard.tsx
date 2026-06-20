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
import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { aiApi } from "../services/ai";
import type {
  AISuggestion,
  AssistantResponse,
  ConfidenceLevel,
  TaskCreate,
  TaskType,
} from "../types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return (
    <div className={clsx("animate-pulse rounded bg-gray-200 dark:bg-gray-700", className)} />
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
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
          checked ? "bg-gray-900 dark:bg-gray-100" : "bg-gray-200 dark:bg-gray-700"
        )}
        onClick={() => onChange(!checked)}
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && onChange(!checked)}
      >
        <div
          className={clsx(
            "absolute top-0.5 left-0.5 w-4 h-4 bg-white dark:bg-gray-900 rounded-full shadow transition-transform",
            checked && "translate-x-4"
          )}
        />
      </div>
      <span className="text-sm text-gray-700 dark:text-gray-200">{label}</span>
    </label>
  );
}

const CONFIDENCE_STYLE: Record<ConfidenceLevel, string> = {
  high: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800",
  medium: "bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800",
  low: "bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700",
};

// ── State ─────────────────────────────────────────────────────────────────────

interface EditState {
  title: string;
  type: TaskType;
  estimated_duration_minutes: number;
  reasoning: string;
  confidence: ConfidenceLevel;
  keywords: string[];
  // Optional fields
  description: string;
  deadline: string;
  duration_override_hours: string;
  is_off_hours_allowed: boolean;
  is_workday_allowed: boolean;
}

function initEditState(raw: string, suggestion?: AISuggestion): EditState {
  return {
    title: suggestion?.title ?? raw,
    type: suggestion?.type ?? "work",
    estimated_duration_minutes: suggestion?.estimated_duration_minutes ?? 60,
    reasoning: suggestion?.reasoning ?? "",
    confidence: suggestion?.confidence ?? "low",
    keywords: suggestion?.keywords ?? [],
    description: "",
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
  const [assistantResult, setAssistantResult] = useState<AssistantResponse | null>(null);
  const [showAssistant, setShowAssistant] = useState(false);
  const [assistantFeedbackSent, setAssistantFeedbackSent] = useState(false);
  const [assistantFeedbackVote, setAssistantFeedbackVote] = useState<boolean | null>(null);
  const [assistantFeedbackComment, setAssistantFeedbackComment] = useState("");

  const assistantFeedbackMutation = useMutation({
    mutationFn: (isPositive: boolean) => {
      const suggestionsText = assistantResult?.suggestions
        .map((s) => `${s.tool_or_approach}: ${s.description}`)
        .join("; ") ?? "";
      return aiApi.submitFeedback({
        task_title: state.title,
        task_type: state.type,
        is_positive: isPositive,
        comment: assistantFeedbackComment.trim() || undefined,
        ai_summary: assistantResult?.summary ?? "",
        ai_suggestions: suggestionsText,
      });
    },
    onSuccess: () => setAssistantFeedbackSent(true),
  });

  const assistantMutation = useMutation({
    mutationFn: () =>
      aiApi.getTaskAssistance({
        title: state.title,
        type: state.type,
        estimated_duration_minutes: state.estimated_duration_minutes || undefined,
        description: state.description || undefined,
        optional_deadline: state.deadline || undefined,
        is_off_hours_allowed: state.is_off_hours_allowed,
        is_workday_allowed: state.is_workday_allowed,
      }),
    onSuccess: (data) => {
      setAssistantResult(data);
      setShowAssistant(true);
      setAssistantFeedbackSent(false);
      setAssistantFeedbackVote(null);
      setAssistantFeedbackComment("");
    },
  });

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
      description: state.description || undefined,
      optional_deadline: state.deadline || undefined,
      is_off_hours_allowed: state.is_off_hours_allowed,
      is_workday_allowed: state.is_workday_allowed,
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
    <div className="rounded-xl border border-gray-200/60 dark:border-gray-700/60 bg-white dark:bg-gray-900 shadow-sm shadow-gray-100 dark:shadow-black/20 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 px-4 py-3 bg-gray-50/60 dark:bg-gray-800/60">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
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
            <span className="inline-flex items-center rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400">
              AI unavailable
            </span>
          )}
        </div>
        <button
          onClick={onCancel}
          className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 -m-1"
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
            className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm
                       text-gray-900 dark:text-gray-100
                       focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-blue-500/20
                       transition-colors"
            placeholder="Task title"
          />
        </div>

        {/* Type */}
        <div>
          <Label>Type</Label>
          {isLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : (
            <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {(["work", "personal"] as TaskType[]).map((t) => (
                <button
                  key={t}
                  onClick={() => set("type", t)}
                  className={clsx(
                    "flex-1 py-2 text-xs font-medium capitalize transition-colors",
                    state.type === t
                      ? "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900"
                      : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* AI estimate + reasoning */}
        {!isFallback && (
          <div className="rounded-lg bg-blue-50/60 dark:bg-blue-950/60 border border-blue-100 dark:border-blue-900 px-3 py-2.5 space-y-1">
            {isLoading ? (
              <div className="space-y-1.5">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="h-3.5 w-full" />
                <Skeleton className="h-3.5 w-3/4" />
              </div>
            ) : (
              <>
                <div className="text-xs font-medium text-blue-700 dark:text-blue-300">
                  ~{formatMinutes(state.estimated_duration_minutes)} estimated
                </div>
                <p className="text-xs text-blue-600/80 dark:text-blue-400/80 leading-relaxed">
                  {state.reasoning}
                </p>
              </>
            )}
          </div>
        )}

        {isFallback && (
          <p className="rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-100 dark:border-amber-900 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            AI is temporarily unavailable. Fill in the details and save manually.
          </p>
        )}

        {/* Optional fields toggle */}
        {!isLoading && (
          <button
            onClick={() => setShowOptional((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300
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
          <div className="space-y-4 pt-1 border-t border-gray-100 dark:border-gray-800">
            {/* Description */}
            <div>
              <Label>Description</Label>
              <textarea
                value={state.description}
                onChange={(e) => set("description", e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm
                           text-gray-900 dark:text-gray-100
                           focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                           focus-visible:ring-2 focus-visible:ring-blue-500/20
                           transition-colors resize-none"
                placeholder="Add details, context, or notes for this task..."
              />
            </div>

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
                  className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm
                             text-gray-900 dark:text-gray-100
                             focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                             focus-visible:ring-2 focus-visible:ring-blue-500/20
                             transition-colors"
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
                  className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm
                             text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500
                             focus-visible:border-blue-300 dark:focus-visible:border-blue-500
                             focus-visible:outline-none focus-visible:ring-2
                             focus-visible:ring-blue-500/20 transition-colors"
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

      {/* AI Assistant */}
      {!isLoading && (
        <div className="px-4 pb-2">
          {!showAssistant && (
            <button
              onClick={() => assistantMutation.mutate()}
              disabled={!state.title.trim() || assistantMutation.isPending}
              className={clsx(
                "flex items-center gap-2 w-full rounded-lg border px-3 py-2.5 text-sm",
                "transition-all duration-150",
                state.title.trim() && !assistantMutation.isPending
                  ? "border-violet-200 dark:border-violet-800 bg-violet-50/60 dark:bg-violet-950/60 text-violet-700 dark:text-violet-300 hover:bg-violet-100/80 dark:hover:bg-violet-900/80 hover:border-violet-300 dark:hover:border-violet-700 cursor-pointer"
                  : "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed"
              )}
            >
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" />
                <circle cx="8" cy="8" r="2.5" />
              </svg>
              {assistantMutation.isPending ? "Thinking..." : "AI Assistant — How can AI help with this task?"}
            </button>
          )}

          {assistantMutation.isPending && (
            <div className="mt-2 space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          )}

          {showAssistant && assistantResult && assistantResult.ai_available && (
            <div className="rounded-lg border border-violet-200 dark:border-violet-800 bg-violet-50/40 dark:bg-violet-950/40 overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 border-b border-violet-100 dark:border-violet-900 bg-violet-50/60 dark:bg-violet-950/60">
                <span className="text-xs font-semibold text-violet-700 dark:text-violet-300">AI Assistant</span>
                <button
                  onClick={() => { setShowAssistant(false); setAssistantResult(null); }}
                  className="text-violet-400 dark:text-violet-500 hover:text-violet-600 dark:hover:text-violet-300 transition-colors p-0.5"
                  aria-label="Close assistant"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4.22 4.22a.75.75 0 0 1 1.06 0L8 6.94l2.72-2.72a.75.75 0 1 1 1.06 1.06L9.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L8 9.06l-2.72 2.72a.75.75 0 0 1-1.06-1.06L6.94 8 4.22 5.28a.75.75 0 0 1 0-1.06Z" />
                  </svg>
                </button>
              </div>

              <div className="p-3 space-y-3">
                <p className="text-sm text-violet-800 dark:text-violet-200 font-medium">{assistantResult.summary}</p>

                <div className="space-y-2">
                  {assistantResult.suggestions.map((s, i) => (
                    <div key={i} className="rounded-md bg-white/80 dark:bg-gray-800/80 border border-violet-100 dark:border-violet-900 p-2.5">
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

                {assistantResult.recommended_workflow && (
                  <div className="border-t border-violet-100 dark:border-violet-900 pt-2.5">
                    <span className="text-xs font-semibold text-violet-700 dark:text-violet-300 block mb-1">Recommended workflow</span>
                    <p className="text-xs text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-line">
                      {assistantResult.recommended_workflow}
                    </p>
                  </div>
                )}

                {/* Feedback */}
                <div className="border-t border-violet-100 dark:border-violet-900 pt-2.5">
                  {assistantFeedbackSent ? (
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Thanks for your feedback!</p>
                  ) : (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 dark:text-gray-400">Was this helpful?</span>
                        <button
                          onClick={() => setAssistantFeedbackVote(true)}
                          className={clsx(
                            "rounded-md border px-2 py-1 text-xs transition-all duration-150",
                            assistantFeedbackVote === true
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
                          onClick={() => setAssistantFeedbackVote(false)}
                          className={clsx(
                            "rounded-md border px-2 py-1 text-xs transition-all duration-150",
                            assistantFeedbackVote === false
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
                      {assistantFeedbackVote !== null && (
                        <div className="space-y-1.5">
                          <textarea
                            value={assistantFeedbackComment}
                            onChange={(e) => setAssistantFeedbackComment(e.target.value)}
                            rows={2}
                            className="w-full text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 rounded-lg px-2.5 py-1.5
                                       text-gray-900 dark:text-gray-100
                                       focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                                       focus-visible:ring-2 focus-visible:ring-blue-500/20
                                       placeholder-gray-300 dark:placeholder-gray-600 transition-colors resize-none"
                            placeholder={assistantFeedbackVote ? "What was most useful? (optional)" : "What could be better? (optional)"}
                          />
                          <button
                            onClick={() => assistantFeedbackMutation.mutate(assistantFeedbackVote!)}
                            disabled={assistantFeedbackMutation.isPending}
                            className="rounded-md bg-gray-900 dark:bg-gray-100 px-3 py-1 text-xs font-medium text-white dark:text-gray-900
                                       hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97] disabled:opacity-50
                                       transition-all duration-150"
                          >
                            {assistantFeedbackMutation.isPending ? "Sending..." : "Submit feedback"}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {showAssistant && assistantResult && !assistantResult.ai_available && (
            <p className="rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-100 dark:border-amber-900 px-3 py-2 text-xs text-amber-700 dark:text-amber-300 mt-2">
              AI Assistant is temporarily unavailable. Try again in a moment.
            </p>
          )}

          {assistantMutation.isError && !assistantMutation.isPending && (
            <p className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-100 dark:border-red-900 px-3 py-2 text-xs text-red-600 dark:text-red-400 mt-2">
              Failed to get AI suggestions. Please try again.
            </p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-end gap-2 border-t border-gray-100 dark:border-gray-800 px-4 py-3">
        <button
          onClick={onCancel}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800
                     transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={isLoading || isSaving}
          className={clsx(
            "rounded-lg px-4 py-1.5 text-sm font-medium text-white dark:text-gray-900 transition-all duration-150",
            !isLoading && !isSaving
              ? "bg-gray-900 dark:bg-gray-100 hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97]"
              : "bg-gray-400 dark:bg-gray-600 cursor-not-allowed"
          )}
        >
          {isSaving ? "Saving…" : isLoading ? "Analysing…" : "Save Task"}
        </button>
      </div>
    </div>
  );
}
