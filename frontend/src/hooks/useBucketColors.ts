/**
 * Resolves the four productivity buckets to the colors the user picked in
 * Settings, so the legend and the task-row stripes always agree with the
 * calendar (and with each other).
 *
 * Reads the same ["settings"] query SettingsPage writes, so changing a color
 * there repaints the backlog as soon as the mutation settles.
 */

import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../services/settings";
import {
  BUCKET_META,
  hexForColorId,
  isBucket,
  type Bucket,
  type BucketMeta,
} from "../lib/googleColors";

export interface ResolvedBucket extends BucketMeta {
  hex: string;
}

export interface BucketColors {
  /** False when color-coding is switched off — callers render nothing. */
  enabled: boolean;
  /** In legend order. Empty until settings load. */
  buckets: ResolvedBucket[];
  /** Hex for a bucket key straight off a task block, or null if unusable. */
  hexFor: (bucket: string | null | undefined) => string | null;
}

export function useBucketColors(): BucketColors {
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    staleTime: 5 * 60_000,
  });

  const enabled = settings?.colorize_enabled ?? false;

  const colorIdFor = (key: Bucket): string | undefined => {
    if (!settings) return undefined;
    switch (key) {
      case "purposeful":
        return settings.color_purposeful;
      case "necessary":
        return settings.color_necessary;
      case "distracting":
        return settings.color_distracting;
      case "unnecessary":
        return settings.color_unnecessary;
    }
  };

  const buckets: ResolvedBucket[] = settings
    ? BUCKET_META.map((meta) => ({ ...meta, hex: hexForColorId(colorIdFor(meta.key)) }))
    : [];

  const hexFor = (bucket: string | null | undefined): string | null => {
    if (!enabled || !isBucket(bucket)) return null;
    return hexForColorId(colorIdFor(bucket));
  };

  return { enabled, buckets, hexFor };
}
