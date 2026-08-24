/**
 * ColorLegend — the slim key for calendar color-coding, sitting just above the
 * task list.
 *
 * Deliberately one short line: four swatches with labels on desktop, bare
 * swatches below sm. The trailing (i) opens the 2x2 framing the bucket names
 * alone don't convey (Productive/Unproductive x Attractive/Unattractive).
 *
 * Every swatch tips with Google's own name for its color ("Basil", "Peacock"),
 * because several of the eleven look alike at this size — the name is what tells
 * you which one to reach for when recoloring an event in Google Calendar.
 *
 * Renders nothing when color-coding is off, so the row never sits there empty.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useBucketColors, type ResolvedBucket } from "../hooks/useBucketColors";

function bucketTooltip(bucket: ResolvedBucket): string {
  return `${bucket.label} — ${bucket.hint} · Google color: ${bucket.colorName}`;
}

function Swatch({ hex }: { hex: string }) {
  return (
    <span
      className="w-2.5 h-2.5 rounded-full shrink-0 ring-1 ring-black/10 dark:ring-white/20"
      style={{ backgroundColor: hex }}
    />
  );
}

function MatrixCell({ bucket }: { bucket: ResolvedBucket }) {
  return (
    <div className="flex items-center gap-1.5 min-w-0" title={bucketTooltip(bucket)}>
      <Swatch hex={bucket.hex} />
      <span className="text-xs text-gray-700 dark:text-gray-200 truncate">
        {bucket.label}
      </span>
    </div>
  );
}

function LegendPopover({ buckets }: { buckets: ResolvedBucket[] }) {
  const cell = (productive: boolean, attractive: boolean) => {
    const b = buckets.find(
      (x) => x.productive === productive && x.attractive === attractive
    );
    return b ? <MatrixCell bucket={b} /> : null;
  };

  return (
    <div
      role="dialog"
      aria-label="Calendar color key"
      className="absolute right-0 top-full mt-1.5 z-30 w-[280px] rounded-xl border border-gray-200/80
                 dark:border-gray-700/80 bg-white dark:bg-gray-900 shadow-lg shadow-gray-200/60
                 dark:shadow-black/40 p-3 space-y-2.5"
    >
      <p className="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed">
        FlowList sorts each calendar event into one of four buckets and colors it
        to match.
      </p>

      <div className="grid grid-cols-[auto_1fr_1fr] gap-x-2.5 gap-y-1.5 items-center">
        <span />
        <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
          Attractive
        </span>
        <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
          Unattractive
        </span>

        <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 text-right">
          Productive
        </span>
        {cell(true, true)}
        {cell(true, false)}

        <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 text-right">
          Unproductive
        </span>
        {cell(false, true)}
        {cell(false, false)}
      </div>

      <p className="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed pt-0.5 border-t border-gray-100 dark:border-gray-800">
        A task shows its stripe once its calendar block has been classified.{" "}
        <Link
          to="/settings"
          className="text-blue-600 dark:text-blue-400 hover:underline"
        >
          Change colors
        </Link>
      </p>
    </div>
  );
}

export function ColorLegend() {
  const { enabled, buckets } = useBucketColors();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!enabled || buckets.length === 0) return null;

  return (
    <div ref={wrapRef} className="relative flex items-center gap-x-3.5 gap-y-1 px-1 py-1">
      {buckets.map((b) => (
        <span key={b.key} className="flex items-center gap-1.5" title={bucketTooltip(b)}>
          <Swatch hex={b.hex} />
          <span className="hidden sm:inline text-xs text-gray-600 dark:text-gray-300">
            {b.label}
          </span>
        </span>
      ))}

      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="What do these colors mean?"
        aria-expanded={open}
        className="ml-auto shrink-0 text-gray-300 dark:text-gray-600 hover:text-gray-500
                   dark:hover:text-gray-400 transition-colors"
      >
        <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="8" cy="8" r="6.25" />
          <path d="M8 7.25v3.5" strokeLinecap="round" />
          <circle cx="8" cy="5.15" r="0.75" fill="currentColor" stroke="none" />
        </svg>
      </button>

      {open && <LegendPopover buckets={buckets} />}
    </div>
  );
}
