import api from "./api";
import type { Task } from "../types";

export const archiveApi = {
  list(params?: { type?: "work" | "personal"; limit?: number; offset?: number }): Promise<Task[]> {
    return api.get<Task[]>("/tasks/archive", { params }).then((r) => r.data);
  },
};
