/**
 * BucketPicker — pin a task to a productivity bucket, overriding the classifier.
 *
 * FlowList sorts calendar events into four buckets and colors them to match.
 * When it gets one wrong, this is where you say so: picking a bucket here
 * records a durable override that also applies to the task's future blocks,
 * and teaches the classifier not to repeat the mistake on similar work.
 *
 * Shows the AI's own answer as the "Auto" option, so the choice is always
 * between a visible current classification and a deliberate replacement rather
 * than an unlabelled set of swatches.
 *
 * Renders nothing when color-coding is switched off — there would be no colors
 * for an override to change.
 */

import clsx from "clsx";
import { useBucketColors } from "../hooks/useBucketColors";
import { isBucket } from "../lib/googleColors";

interface BucketPickerProps {
  /** The pinned bucket, or null when the task follows the classifier. */
  value: string | null;
  /** What the classifier decided, shown as the Auto option's result. */
  classified: string | null;
  disabled?: boolean;
  /** Called with a bucket key to pin, or null to clear the pin. */
  onChange: (bucket: string | null) => void;
}

export function BucketPicker({
  value,
  classified,
  disabled = false,
  onChange,
}: BucketPickerProps) {
  const { enabled, buckets, hexFor } = useBucketColors();
  if (!enabled || buckets.length === 0) return null;

  const pinned = isBucket(value) ? value : null;
  const autoHex = hexFor(classified);
  const autoLabel =
    buckets.find((b) => b.key === classified)?.label ?? "Not yet classified";

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <p className="text-xs text-gray-400 dark:text-gray-500">Calendar Color</p>
        {pinned && (
          <span className="text-[10px] text-gray-400 dark:text-gray-500">
            Overriding the AI
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {/* Auto — hand the task back to the classifier. */}
        <button
          type="button"
          disabled={disabled}
          aria-pressed={pinned === null}
          onClick={() => onChange(null)}
          title={`Let the AI decide (currently: ${autoLabel})`}
          className={clsx(
            "flex items-center gap-1.5 pl-1.5 pr-2.5 py-1 rounded-lg border text-xs transition-colors",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20",
            pinned === null
              ? "border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              : "border-gray-200/70 dark:border-gray-700/70 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600"
          )}
        >
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0 border border-black/10 dark:border-white/20"
            style={autoHex ? { backgroundColor: autoHex } : undefined}
          />
          Auto
        </button>

        {buckets.map((b) => {
          const active = pinned === b.key;
          return (
            <button
              key={b.key}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onChange(active ? null : b.key)}
              title={b.hint}
              className={clsx(
                "flex items-center gap-1.5 pl-1.5 pr-2.5 py-1 rounded-lg border text-xs transition-colors",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20",
                active
                  ? "border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  : "border-gray-200/70 dark:border-gray-700/70 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600"
              )}
            >
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0 border border-black/10 dark:border-white/20"
                style={{ backgroundColor: b.hex }}
              />
              {b.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
