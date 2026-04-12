import api from "./api";
import type { Task } from "../types";

export const watchdogApi = {
  list(): Promise<Task[]> {
    return api.get<Task[]>("/watchdog/").then((r) => r.data);
  },
};
