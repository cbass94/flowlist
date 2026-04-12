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
