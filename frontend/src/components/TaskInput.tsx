/**
 * TaskInput
 *
 * Entry point for creating a new task. Manages the full add-task flow:
 *
 *   idle       → user types + submits
 *   loading    → AISuggestionCard shown in skeleton state while Claude processes
 *   confirming → AI fields populated, user can edit before saving
 *   fallback   → AI failed, manual entry mode
 *   saving     → save button pressed, API call in flight
 */

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { tasksApi } from "../services/tasks";
import { useTaskParse } from "../hooks/useTaskParse";
import { AISuggestionCard, type CardStatus } from "./AISuggestionCard";
import type { AISuggestion, TaskCreate } from "../types";

type InputState =
  | { phase: "idle" }
  | { phase: "loading"; rawText: string }
  | { phase: "confirming"; rawText: string; suggestion: AISuggestion }
  | { phase: "fallback"; rawText: string }
  | { phase: "saving"; rawText: string };

interface Props {
  onTaskCreated?: () => void;
}

export function TaskInput({ onTaskCreated }: Props) {
  const [inputText, setInputText] = useState("");
  const [state, setState] = useState<InputState>({ phase: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);

  const queryClient = useQueryClient();
  const parseMutation = useTaskParse();

  const createMutation = useMutation({
    mutationFn: (data: TaskCreate) => tasksApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setState({ phase: "idle" });
      setInputText("");
      onTaskCreated?.();
      requestAnimationFrame(() => inputRef.current?.focus());
    },
    onError: () => {
      // Stay in confirming state so user can retry
      setState((prev) =>
        prev.phase === "saving"
          ? { phase: "fallback", rawText: prev.rawText }
          : prev
      );
    },
  });

  function handleSubmit() {
    const rawText = inputText.trim();
    if (!rawText) return;

    setState({ phase: "loading", rawText });
    setInputText("");

    parseMutation.mutate(
      { raw_text: rawText },
      {
        onSuccess: (response) => {
          if (response.ai_available) {
            setState({ phase: "confirming", rawText, suggestion: response.suggestion });
          } else {
            setState({ phase: "fallback", rawText });
          }
        },
        onError: () => {
          setState({ phase: "fallback", rawText });
        },
      }
    );
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleConfirm(task: TaskCreate) {
    if (state.phase !== "confirming" && state.phase !== "fallback") return;
    setState({ phase: "saving", rawText: state.rawText });
    createMutation.mutate(task);
  }

  function handleCancel() {
    if (state.phase !== "idle") {
      setInputText(state.rawText);
    }
    setState({ phase: "idle" });
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  // Derive card props
  const isCardShown = state.phase !== "idle";
  let cardStatus: CardStatus = "loading";
  let cardSuggestion: AISuggestion | undefined;
  let cardRawText = "";

  if (state.phase === "loading") {
    cardStatus = "loading";
    cardRawText = state.rawText;
  } else if (state.phase === "confirming") {
    cardStatus = "ready";
    cardSuggestion = state.suggestion;
    cardRawText = state.rawText;
  } else if (state.phase === "fallback") {
    cardStatus = "fallback";
    cardRawText = state.rawText;
  } else if (state.phase === "saving") {
    cardStatus = "ready";
    cardRawText = state.rawText;
  }

  return (
    <div className="space-y-3">
      {state.phase === "idle" && (
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="What needs to get done?"
            className="flex-1 rounded-xl border border-gray-200/80 dark:border-gray-700/80 bg-white dark:bg-gray-900 px-4 py-3
                       text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 shadow-sm shadow-gray-100 dark:shadow-black/20
                       focus-visible:border-blue-300 dark:focus-visible:border-blue-500 focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-blue-500/20
                       transition-all duration-150"
            autoFocus
          />
          <button
            onClick={handleSubmit}
            disabled={!inputText.trim()}
            className="rounded-xl bg-gray-900 dark:bg-gray-100 px-5 py-3 text-sm font-medium text-white dark:text-gray-900
                       shadow-sm hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97]
                       disabled:opacity-30 disabled:cursor-not-allowed
                       transition-all duration-150"
          >
            Add
          </button>
        </div>
      )}

      {isCardShown && (
        <AISuggestionCard
          status={cardStatus}
          rawText={cardRawText}
          suggestion={cardSuggestion}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          isSaving={state.phase === "saving" || createMutation.isPending}
        />
      )}

      {createMutation.isError && (
        <p className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-100 dark:border-red-900 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          Failed to save task — please try again.
        </p>
      )}
    </div>
  );
}
