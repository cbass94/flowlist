// Settings page — scheduling preferences, timezone, Google account connections,
// and admin invite management.

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi, type UpdateSettings } from "../services/settings";
import { invitesApi } from "../services/invites";
import { useAuth } from "../hooks/useAuth";
import type { CalendarItem, Invite } from "../types";

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: `${i === 0 ? "12" : i <= 12 ? i : i - 12}:00 ${i < 12 ? "AM" : "PM"}`,
}));

// 30-minute increment time options, clamped to hard limits (7:00am – 10:00pm)
const TIME_OPTIONS: { value: string; label: string }[] = [];
for (let h = 7; h <= 22; h++) {
  for (const m of [0, 30]) {
    if (h === 22 && m === 30) continue;
    const val = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
    const displayH = h === 0 ? 12 : h <= 12 ? h : h - 12;
    const ampm = h < 12 ? "AM" : "PM";
    const label = `${displayH}:${String(m).padStart(2, "0")} ${ampm}`;
    TIME_OPTIONS.push({ value: val, label });
  }
}
const DEFAULT_START = "09:00:00";
const DEFAULT_END = "17:00:00";

const inputCls = "text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-2 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20 focus-visible:border-blue-300 dark:focus-visible:border-blue-500 transition-colors";

function HourSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={inputCls}
      >
        {HOUR_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function CalendarSelect({
  label,
  value,
  account,
  onChange,
}: {
  label: string;
  value: string | null;
  account: "work" | "personal";
  onChange: (id: string) => void;
}) {
  const { data: calendars, isLoading, isError } = useQuery<CalendarItem[]>({
    queryKey: ["calendars", account],
    queryFn: () => settingsApi.listCalendars(account),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-between gap-4">
        <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">{label}</label>
        <span className="text-xs text-gray-400 dark:text-gray-500">Loading...</span>
      </div>
    );
  }

  if (isError || !calendars) {
    return (
      <div className="flex items-center justify-between gap-4">
        <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">{label}</label>
        {account === "personal" ? (
          <a
            href="/api/auth/connect/personal"
            className="text-xs text-amber-600 dark:text-amber-400 hover:underline"
          >
            Token expired — Reconnect
          </a>
        ) : (
          <span className="text-xs text-red-400 dark:text-red-400">Failed to load calendars</span>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">{label}</label>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputCls} max-w-[200px]`}
      >
        <option value="">Default</option>
        {calendars.map((cal) => (
          <option key={cal.id} value={cal.id}>
            {cal.summary}{cal.primary ? " (primary)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Weekend scheduling section ─────────────────────────────────────────────────

function DayTimePickers({
  day,
  start,
  end,
  enabled,
  onToggle,
  onChange,
}: {
  day: string;
  start: string | null;
  end: string | null;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  onChange: (start: string, end: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500 dark:text-gray-400">{day}</span>
        <button
          role="switch"
          aria-checked={enabled}
          onClick={() => onToggle(!enabled)}
          className={`relative inline-flex w-8 h-4 rounded-full transition-colors ${
            enabled ? "bg-gray-900 dark:bg-gray-100" : "bg-gray-200 dark:bg-gray-700"
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white dark:bg-gray-900 rounded-full shadow transition-transform ${
              enabled ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
      </div>
      {enabled && (
        <div className="flex items-center gap-2 pl-2">
          <select
            value={start ?? DEFAULT_START}
            onChange={(e) => onChange(e.target.value, end ?? DEFAULT_END)}
            className={`${inputCls} text-xs`}
          >
            {TIME_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <span className="text-xs text-gray-400 dark:text-gray-500">to</span>
          <select
            value={end ?? DEFAULT_END}
            onChange={(e) => onChange(start ?? DEFAULT_START, e.target.value)}
            className={`${inputCls} text-xs`}
          >
            {TIME_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}

function WeekendSection({
  label,
  enabled,
  onToggle,
  satStart,
  satEnd,
  sunStart,
  sunEnd,
  onDayChange,
  onDayToggle,
}: {
  label: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  satStart: string | null;
  satEnd: string | null;
  sunStart: string | null;
  sunEnd: string | null;
  onDayChange: (day: "saturday" | "sunday", start: string, end: string) => void;
  onDayToggle: (day: "saturday" | "sunday", enabled: boolean) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4">
        <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">{label}</label>
        <button
          role="switch"
          aria-checked={enabled}
          onClick={() => onToggle(!enabled)}
          className={`relative inline-flex w-10 h-5 rounded-full transition-colors ${
            enabled ? "bg-gray-900 dark:bg-gray-100" : "bg-gray-200 dark:bg-gray-700"
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white dark:bg-gray-900 rounded-full shadow transition-transform ${
              enabled ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>
      {enabled && (
        <div className="ml-2 pl-3 border-l-2 border-gray-100 dark:border-gray-800 space-y-2">
          <DayTimePickers
            day="Saturday"
            start={satStart}
            end={satEnd}
            enabled={satStart !== null}
            onToggle={(v) => onDayToggle("saturday", v)}
            onChange={(s, e) => onDayChange("saturday", s, e)}
          />
          <DayTimePickers
            day="Sunday"
            start={sunStart}
            end={sunEnd}
            enabled={sunStart !== null}
            onToggle={(v) => onDayToggle("sunday", v)}
            onChange={(s, e) => onDayChange("sunday", s, e)}
          />
        </div>
      )}
    </div>
  );
}

// ── Invite management (admin only) ────────────────────────────────────────────

function InviteRow({
  invite,
  onRevoke,
}: {
  invite: Invite;
  onRevoke: (id: number) => void;
}) {
  const inviteUrl = `${window.location.origin}/invite?token=${invite.token}`;
  const [copied, setCopied] = useState(false);

  function copyLink() {
    navigator.clipboard.writeText(inviteUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const statusColor =
    invite.status === "accepted"
      ? "text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950"
      : invite.status === "expired"
      ? "text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800"
      : "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950";

  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 dark:text-gray-100 truncate">{invite.email}</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">
          {new Date(invite.created_at).toLocaleDateString()}
          {invite.accepted_at && (
            <> · accepted {new Date(invite.accepted_at).toLocaleDateString()}</>
          )}
        </p>
      </div>
      <span
        className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${statusColor}`}
      >
        {invite.status}
      </span>
      {invite.status === "pending" && (
        <button
          onClick={copyLink}
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline shrink-0"
        >
          {copied ? "Copied!" : "Copy link"}
        </button>
      )}
      {invite.status !== "accepted" && (
        <button
          onClick={() => onRevoke(invite.id)}
          className="text-xs text-red-400 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300 shrink-0"
        >
          Revoke
        </button>
      )}
    </div>
  );
}

function InviteSection() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const { data: invites = [], isLoading } = useQuery<Invite[]>({
    queryKey: ["invites"],
    queryFn: invitesApi.list,
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: (e: string) => invitesApi.create(e),
    onSuccess: (newInvite) => {
      qc.setQueryData<Invite[]>(["invites"], (prev = []) => [newInvite, ...prev]);
      setEmail("");
      setCreateError(null);
    },
    onError: (err: Error) => setCreateError(err.message),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => invitesApi.revoke(id),
    onSuccess: (_data, id) => {
      qc.setQueryData<Invite[]>(["invites"], (prev = []) =>
        prev.filter((i) => i.id !== id)
      );
    },
  });

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    createMutation.mutate(trimmed);
  }

  return (
    <section className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-700/60 shadow-sm shadow-gray-100 dark:shadow-black/20 divide-y divide-gray-100 dark:divide-gray-800">
      <div className="px-5 py-4">
        <h2 className="font-semibold text-gray-800 dark:text-gray-100 text-sm">Invites</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Users need an invite link to create an account. Copy and share the
          link manually.
        </p>
      </div>

      {/* Create invite */}
      <div className="px-5 py-4">
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            className="flex-1 text-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20 focus-visible:border-blue-300 dark:focus-visible:border-blue-500 transition-colors placeholder-gray-400 dark:placeholder-gray-500"
          />
          <button
            type="submit"
            disabled={createMutation.isPending || !email.trim()}
            className="text-sm px-4 py-1.5 rounded-lg bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 shrink-0"
          >
            {createMutation.isPending ? "..." : "Invite"}
          </button>
        </form>
        {createError && (
          <p className="text-xs text-red-500 dark:text-red-400 mt-2">{createError}</p>
        )}
      </div>

      {/* Invite list */}
      <div className="px-5 py-2">
        {isLoading && (
          <p className="text-sm text-gray-400 dark:text-gray-500 py-2">Loading invites...</p>
        )}
        {!isLoading && invites.length === 0 && (
          <p className="text-sm text-gray-400 dark:text-gray-500 py-2">No invites yet.</p>
        )}
        {invites.map((invite) => (
          <InviteRow
            key={invite.id}
            invite={invite}
            onRevoke={(id) => revokeMutation.mutate(id)}
          />
        ))}
      </div>
    </section>
  );
}

// ── Main settings page ────────────────────────────────────────────────────────

export function SettingsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [saveError, setSaveError] = useState<string | null>(null);
  const [rescheduling, setRescheduling] = useState(false);
  const [rescheduled, setRescheduled] = useState(false);

  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    staleTime: 60_000,
  });

  // Subscribe to the same cache key CalendarSelect uses so we can detect token expiry.
  // enabled: false until we know the account is connected (avoids a spurious 400).
  const { isError: personalCalError } = useQuery<CalendarItem[]>({
    queryKey: ["calendars", "personal"],
    queryFn: () => settingsApi.listCalendars("personal"),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: settings?.personal_account_connected ?? false,
  });

  const mutation = useMutation({
    mutationFn: (body: UpdateSettings) => settingsApi.update(body),
    onSuccess: (updated) => {
      qc.setQueryData(["settings"], updated);
      setSaveError(null);
    },
    onError: (err: Error) => setSaveError(err.message),
  });

  if (isLoading || !settings) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-400 dark:text-gray-500 text-sm">
        Loading settings...
      </div>
    );
  }

  function save(patch: UpdateSettings) {
    mutation.mutate(patch);
  }

  async function handleReschedule() {
    setRescheduling(true);
    try {
      await settingsApi.reschedule();
      setRescheduled(true);
      setTimeout(() => setRescheduled(false), 3000);
    } finally {
      setRescheduling(false);
    }
  }

  const sectionCls = "bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-700/60 shadow-sm shadow-gray-100 dark:shadow-black/20 divide-y divide-gray-100 dark:divide-gray-800";

  return (
    <div className="space-y-6 pb-16">
      {saveError && (
        <div className="bg-red-50 dark:bg-red-950 border border-red-100 dark:border-red-900 text-red-700 dark:text-red-300 text-sm px-4 py-3 rounded-xl">
          Failed to save: {saveError}
        </div>
      )}

      {/* Profile */}
      <section className={sectionCls}>
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-100 text-sm">Profile</h2>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">Display name</label>
            <input
              type="text"
              defaultValue={settings.display_name ?? ""}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== settings.display_name) save({ display_name: v });
              }}
              className={`${inputCls} w-44`}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">Timezone</label>
            <input
              type="text"
              defaultValue={settings.timezone}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== settings.timezone) save({ timezone: v });
              }}
              className={`${inputCls} w-44`}
              placeholder="America/Chicago"
            />
          </div>
        </div>
      </section>

      {/* Scheduling hours */}
      <section className={sectionCls}>
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-100 text-sm">Scheduling Hours</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Work tasks are scheduled within work hours. Personal tasks fill the gaps.
          </p>
        </div>
        <div className="px-5 py-4 space-y-4">
          {/* Work weekends */}
          <WeekendSection
            label="Schedule work tasks on weekends"
            enabled={settings.allow_work_on_weekends}
            onToggle={(v) => {
              const patch: UpdateSettings = { allow_work_on_weekends: v };
              if (v) {
                if (!settings.work_saturday_start_time) {
                  patch.work_saturday_start_time = DEFAULT_START;
                  patch.work_saturday_end_time = DEFAULT_END;
                }
                if (!settings.work_sunday_start_time) {
                  patch.work_sunday_start_time = DEFAULT_START;
                  patch.work_sunday_end_time = DEFAULT_END;
                }
              }
              save(patch);
            }}
            satStart={settings.work_saturday_start_time}
            satEnd={settings.work_saturday_end_time}
            sunStart={settings.work_sunday_start_time}
            sunEnd={settings.work_sunday_end_time}
            onDayChange={(day, start, end) => {
              if (day === "saturday") {
                save({ work_saturday_start_time: start, work_saturday_end_time: end });
              } else {
                save({ work_sunday_start_time: start, work_sunday_end_time: end });
              }
            }}
            onDayToggle={(day, enabled) => {
              if (day === "saturday") {
                save({
                  work_saturday_start_time: enabled ? DEFAULT_START : null,
                  work_saturday_end_time: enabled ? DEFAULT_END : null,
                });
              } else {
                save({
                  work_sunday_start_time: enabled ? DEFAULT_START : null,
                  work_sunday_end_time: enabled ? DEFAULT_END : null,
                });
              }
            }}
          />
          {/* Personal weekends */}
          <WeekendSection
            label="Schedule personal tasks on weekends"
            enabled={settings.allow_personal_on_weekends}
            onToggle={(v) => {
              const patch: UpdateSettings = { allow_personal_on_weekends: v };
              if (v) {
                if (!settings.personal_saturday_start_time) {
                  patch.personal_saturday_start_time = DEFAULT_START;
                  patch.personal_saturday_end_time = DEFAULT_END;
                }
                if (!settings.personal_sunday_start_time) {
                  patch.personal_sunday_start_time = DEFAULT_START;
                  patch.personal_sunday_end_time = DEFAULT_END;
                }
              }
              save(patch);
            }}
            satStart={settings.personal_saturday_start_time}
            satEnd={settings.personal_saturday_end_time}
            sunStart={settings.personal_sunday_start_time}
            sunEnd={settings.personal_sunday_end_time}
            onDayChange={(day, start, end) => {
              if (day === "saturday") {
                save({ personal_saturday_start_time: start, personal_saturday_end_time: end });
              } else {
                save({ personal_sunday_start_time: start, personal_sunday_end_time: end });
              }
            }}
            onDayToggle={(day, enabled) => {
              if (day === "saturday") {
                save({
                  personal_saturday_start_time: enabled ? DEFAULT_START : null,
                  personal_saturday_end_time: enabled ? DEFAULT_END : null,
                });
              } else {
                save({
                  personal_sunday_start_time: enabled ? DEFAULT_START : null,
                  personal_sunday_end_time: enabled ? DEFAULT_END : null,
                });
              }
            }}
          />
        </div>
        <div className="px-5 py-4 space-y-3">
          <HourSelect
            label="Work day start"
            value={settings.work_start_hour}
            onChange={(v) => save({ work_start_hour: v })}
          />
          <HourSelect
            label="Work day end"
            value={settings.work_end_hour}
            onChange={(v) => save({ work_end_hour: v })}
          />
          <HourSelect
            label="Hard limit — earliest"
            value={settings.hard_start_hour}
            onChange={(v) => save({ hard_start_hour: v })}
          />
          <HourSelect
            label="Hard limit — latest"
            value={settings.hard_end_hour}
            onChange={(v) => save({ hard_end_hour: v })}
          />
          <div className="flex items-center justify-between gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-300 flex-1">
              Buffer before each block
            </label>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={0}
                max={120}
                step={5}
                defaultValue={settings.buffer_minutes}
                onBlur={(e) => {
                  const v = Number(e.target.value);
                  if (!isNaN(v) && v !== settings.buffer_minutes) save({ buffer_minutes: v });
                }}
                className={`${inputCls} w-16 text-center`}
              />
              <span className="text-xs text-gray-400 dark:text-gray-500">min</span>
            </div>
          </div>
        </div>
      </section>

      {/* Calendars */}
      <section className={sectionCls}>
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-100 text-sm">Google Calendars</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Which calendars FlowList writes to.
          </p>
        </div>
        <div className="px-5 py-4 space-y-3">
          <CalendarSelect
            label="Work calendar"
            value={settings.work_calendar_id}
            account="work"
            onChange={(id) => save({ work_calendar_id: id })}
          />
          {settings.personal_account_connected ? (
            <CalendarSelect
              label="Personal calendar"
              value={settings.personal_calendar_id}
              account="personal"
              onChange={(id) => save({ personal_calendar_id: id })}
            />
          ) : (
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm text-gray-600 dark:text-gray-300 flex-1">Personal calendar</span>
              <a
                href="/api/auth/connect/personal"
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                Connect personal account
              </a>
            </div>
          )}
        </div>
      </section>

      {/* Google account status */}
      <section className={sectionCls}>
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-100 text-sm">Connected Accounts</h2>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-300">Work (Google)</span>
            <span className="inline-flex items-center gap-1 text-xs text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950 px-2 py-0.5 rounded-full">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Connected
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-300">Personal (Google)</span>
            {settings.personal_account_connected && !personalCalError ? (
              <span className="inline-flex items-center gap-1 text-xs text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950 px-2 py-0.5 rounded-full">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                Connected
              </span>
            ) : (
              <a
                href="/api/auth/connect/personal"
                className="text-xs text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950 hover:bg-blue-100 dark:hover:bg-blue-900 px-3 py-1 rounded-full transition-colors"
              >
                {settings.personal_account_connected && personalCalError ? "Reconnect" : "Connect"}
              </a>
            )}
          </div>
        </div>
      </section>

      {/* Reschedule */}
      <section className={sectionCls}>
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-100 text-sm">Scheduling</h2>
        </div>
        <div className="px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm text-gray-700 dark:text-gray-200 font-medium">Reschedule Now</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                Re-optimize all future calendar blocks against the current backlog order.
              </p>
            </div>
            <button
              onClick={handleReschedule}
              disabled={rescheduling || rescheduled}
              className="shrink-0 text-sm px-4 py-2 rounded-xl bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150"
            >
              {rescheduled ? "Queued!" : rescheduling ? "..." : "Reschedule"}
            </button>
          </div>
        </div>
      </section>

      {/* Invite management — admin only */}
      {user?.is_admin && <InviteSection />}

      {/* Sign out */}
      <div className="text-center">
        <a
          href="/api/auth/logout"
          className="text-sm text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 underline"
        >
          Sign out
        </a>
      </div>
    </div>
  );
}
