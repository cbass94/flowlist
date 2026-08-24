/**
 * Google Calendar's fixed event-color palette, plus the four productivity
 * buckets FlowList sorts events into.
 *
 * Single source of truth for both the Settings color pickers and the backlog
 * legend / row stripes — so a bucket's name, hint, and swatch can never drift
 * between the place you configure it and the place you read it.
 */

export interface GoogleColor {
  id: string;
  name: string;
  hex: string;
}

// colorId → name + hex swatch (Google's palette is fixed; these are its 11 slots)
export const GOOGLE_COLORS: GoogleColor[] = [
  { id: "1", name: "Lavender", hex: "#7986cb" },
  { id: "2", name: "Sage", hex: "#33b679" },
  { id: "3", name: "Grape", hex: "#8e24aa" },
  { id: "4", name: "Flamingo", hex: "#e67c73" },
  { id: "5", name: "Banana", hex: "#f6bf26" },
  { id: "6", name: "Tangerine", hex: "#f4511e" },
  { id: "7", name: "Peacock", hex: "#039be5" },
  { id: "8", name: "Graphite", hex: "#616161" },
  { id: "9", name: "Blueberry", hex: "#3f51b5" },
  { id: "10", name: "Basil", hex: "#0b8043" },
  { id: "11", name: "Tomato", hex: "#d50000" },
];

export const FALLBACK_HEX = "#9ca3af";
export const FALLBACK_COLOR_NAME = "Default";

export function hexForColorId(colorId: string | null | undefined): string {
  return GOOGLE_COLORS.find((c) => c.id === colorId)?.hex ?? FALLBACK_HEX;
}

/**
 * Google's own name for a colorId ("Basil", "Peacock", ...).
 *
 * Several of the eleven are near-indistinguishable at swatch size, so the name
 * is what actually tells you which one to pick from Google Calendar's menu when
 * recoloring an event by hand.
 */
export function nameForColorId(colorId: string | null | undefined): string {
  return GOOGLE_COLORS.find((c) => c.id === colorId)?.name ?? FALLBACK_COLOR_NAME;
}

export type Bucket = "purposeful" | "necessary" | "distracting" | "unnecessary";

export interface BucketMeta {
  key: Bucket;
  label: string;
  /** Short hint shown in Settings and in the legend popover. */
  hint: string;
  /** Which half of each axis this bucket sits on (drives the 2x2 in the popover). */
  productive: boolean;
  attractive: boolean;
}

// Ordered as they read in the legend: the two productive buckets first.
export const BUCKET_META: BucketMeta[] = [
  {
    key: "purposeful",
    label: "Purposeful",
    hint: "Productive + engaging",
    productive: true,
    attractive: true,
  },
  {
    key: "necessary",
    label: "Necessary",
    hint: "Productive but not enjoyable",
    productive: true,
    attractive: false,
  },
  {
    key: "distracting",
    label: "Distracting",
    hint: "Enjoyable but low-value",
    productive: false,
    attractive: true,
  },
  {
    key: "unnecessary",
    label: "Unnecessary",
    hint: "Low-value busywork",
    productive: false,
    attractive: false,
  },
];

export function isBucket(value: string | null | undefined): value is Bucket {
  return BUCKET_META.some((b) => b.key === value);
}
