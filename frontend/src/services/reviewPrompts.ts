import api from "./api";
import type { CompleteRequest, Task } from "../types";

export const reviewPromptsApi = {
  list(): Promise<Task[]> {
    return api.get<Task[]>("/review-prompts/").then((r) => r.data);
  },

  confirm(id: number, data: CompleteRequest): Promise<Task> {
    return api
      .post<Task>(`/review-prompts/${id}/confirm`, data)
      .then((r) => r.data);
  },

  reschedule(id: number): Promise<Task> {
    return api
      .post<Task>(`/review-prompts/${id}/reschedule`)
      .then((r) => r.data);
  },
};
