import api from "./api";
import type { CalendarItem, UserSettings } from "../types";

export interface UpdateSettings {
  timezone?: string;
  display_name?: string;
  work_start_hour?: number;
  work_end_hour?: number;
  hard_start_hour?: number;
  hard_end_hour?: number;
  buffer_minutes?: number;
  work_calendar_id?: string;
  personal_calendar_id?: string;
  allow_work_on_weekends?: boolean;
  allow_personal_on_weekends?: boolean;
  work_saturday_start_time?: string | null;
  work_saturday_end_time?: string | null;
  work_sunday_start_time?: string | null;
  work_sunday_end_time?: string | null;
  personal_saturday_start_time?: string | null;
  personal_saturday_end_time?: string | null;
  personal_sunday_start_time?: string | null;
  personal_sunday_end_time?: string | null;
}

export const settingsApi = {
  get(): Promise<UserSettings> {
    return api.get<UserSettings>("/settings/").then((r) => r.data);
  },

  update(body: UpdateSettings): Promise<UserSettings> {
    return api.patch<UserSettings>("/settings/", body).then((r) => r.data);
  },

  listCalendars(account: "work" | "personal"): Promise<CalendarItem[]> {
    return api.get<CalendarItem[]>("/settings/calendars", { params: { account } }).then((r) => r.data);
  },

  reschedule(): Promise<void> {
    return api.post("/settings/reschedule").then(() => undefined);
  },
};
