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
      <label className="text-sm text-gray-600 flex-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
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
        <label className="text-sm text-gray-600 flex-1">{label}</label>
        <span className="text-xs text-gray-400">Loading...</span>
      </div>
    );
  }

  if (isError || !calendars) {
    return (
      <div className="flex items-center justify-between gap-4">
        <label className="text-sm text-gray-600 flex-1">{label}</label>
        <span className="text-xs text-red-400">Failed to load calendars</span>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-sm text-gray-600 flex-1">{label}</label>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[200px]"
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
      ? "text-green-700 bg-green-50"
      : invite.status === "expired"
      ? "text-gray-400 bg-gray-100"
      : "text-blue-700 bg-blue-50";

  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 truncate">{invite.email}</p>
        <p className="text-xs text-gray-400">
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
          className="text-xs text-blue-600 hover:underline shrink-0"
        >
          {copied ? "Copied!" : "Copy link"}
        </button>
      )}
      {invite.status !== "accepted" && (
        <button
          onClick={() => onRevoke(invite.id)}
          className="text-xs text-red-400 hover:text-red-600 shrink-0"
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
    <section className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
      <div className="px-5 py-4">
        <h2 className="font-semibold text-gray-800 text-sm">Invites</h2>
        <p className="text-xs text-gray-400 mt-0.5">
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
            className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={createMutation.isPending || !email.trim()}
            className="text-sm px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            {createMutation.isPending ? "..." : "Invite"}
          </button>
        </form>
        {createError && (
          <p className="text-xs text-red-500 mt-2">{createError}</p>
        )}
      </div>

      {/* Invite list */}
      <div className="px-5 py-2">
        {isLoading && (
          <p className="text-sm text-gray-400 py-2">Loading invites...</p>
        )}
        {!isLoading && invites.length === 0 && (
          <p className="text-sm text-gray-400 py-2">No invites yet.</p>
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
      <div className="flex items-center justify-center py-20 text-gray-400 text-sm">
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

  return (
    <div className="space-y-6 pb-16">
      {saveError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl">
          Failed to save: {saveError}
        </div>
      )}

      {/* Profile */}
      <section className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 text-sm">Profile</h2>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <label className="text-sm text-gray-600 flex-1">Display name</label>
            <input
              type="text"
              defaultValue={settings.display_name ?? ""}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== settings.display_name) save({ display_name: v });
              }}
              className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 w-44 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <label className="text-sm text-gray-600 flex-1">Timezone</label>
            <input
              type="text"
              defaultValue={settings.timezone}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== settings.timezone) save({ timezone: v });
              }}
              className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 w-44 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="America/Chicago"
            />
          </div>
        </div>
      </section>

      {/* Scheduling hours */}
      <section className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 text-sm">Scheduling Hours</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Work tasks are scheduled within work hours. Personal tasks fill the gaps.
          </p>
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
            <label className="text-sm text-gray-600 flex-1">
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
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 w-16 text-center focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="text-xs text-gray-400">min</span>
            </div>
          </div>
        </div>
      </section>

      {/* Calendars */}
      <section className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 text-sm">Google Calendars</h2>
          <p className="text-xs text-gray-400 mt-0.5">
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
              <span className="text-sm text-gray-600 flex-1">Personal calendar</span>
              <a
                href="/api/auth/connect/personal"
                className="text-xs text-blue-600 hover:underline"
              >
                Connect personal account
              </a>
            </div>
          )}
        </div>
      </section>

      {/* Google account status */}
      <section className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 text-sm">Connected Accounts</h2>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">Work (Google)</span>
            <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Connected
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">Personal (Google)</span>
            {settings.personal_account_connected ? (
              <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                Connected
              </span>
            ) : (
              <a
                href="/api/auth/connect/personal"
                className="text-xs text-blue-600 border border-blue-200 bg-blue-50 hover:bg-blue-100 px-3 py-1 rounded-full transition-colors"
              >
                Connect
              </a>
            )}
          </div>
        </div>
      </section>

      {/* Reschedule */}
      <section className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-gray-800 text-sm">Scheduling</h2>
        </div>
        <div className="px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm text-gray-700 font-medium">Reschedule Now</p>
              <p className="text-xs text-gray-400 mt-0.5">
                Re-optimize all future calendar blocks against the current backlog order.
              </p>
            </div>
            <button
              onClick={handleReschedule}
              disabled={rescheduling || rescheduled}
              className="shrink-0 text-sm px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
          className="text-sm text-gray-400 hover:text-gray-600 underline"
        >
          Sign out
        </a>
      </div>
    </div>
  );
}
