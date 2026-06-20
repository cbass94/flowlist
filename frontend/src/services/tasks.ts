import api from "./api";
import type {
  BlockDoneRequest,
  CompleteRequest,
  MoreWorkSuggestion,
  RescheduleAllOverdueResponse,
  ReorderRequest,
  Task,
  TaskCreate,
  TaskUpdate,
} from "../types";

export const tasksApi = {
  list(): Promise<Task[]> {
    return api.get<Task[]>("/tasks/").then((r) => r.data);
  },

  create(data: TaskCreate): Promise<Task> {
    return api.post<Task>("/tasks/", data).then((r) => r.data);
  },

  update(id: number, data: TaskUpdate): Promise<Task> {
    return api.patch<Task>(`/tasks/${id}`, data).then((r) => r.data);
  },

  reorder(data: ReorderRequest): Promise<void> {
    return api.patch("/tasks/reorder", data).then(() => undefined);
  },

  delete(id: number): Promise<void> {
    return api.delete(`/tasks/${id}`).then(() => undefined);
  },

  complete(id: number, data: CompleteRequest): Promise<Task> {
    return api.post<Task>(`/tasks/${id}/complete`, data).then((r) => r.data);
  },

  delegate(id: number): Promise<Task> {
    return api.post<Task>(`/tasks/${id}/delegate`).then((r) => r.data);
  },

  rescheduleOverdue(id: number): Promise<Task> {
    return api.post<Task>(`/tasks/${id}/reschedule-overdue`).then((r) => r.data);
  },

  rescheduleAllOverdue(): Promise<RescheduleAllOverdueResponse> {
    return api.post<RescheduleAllOverdueResponse>("/tasks/reschedule-all-overdue").then((r) => r.data);
  },

  moreWorkSuggestion(id: number): Promise<MoreWorkSuggestion> {
    return api.get<MoreWorkSuggestion>(`/tasks/${id}/more-work-suggestion`).then((r) => r.data);
  },

  moreWork(id: number, additional_minutes: number): Promise<Task> {
    return api.post<Task>(`/tasks/${id}/more-work`, { additional_minutes }).then((r) => r.data);
  },

  deleteBlock(taskId: number, blockId: number): Promise<Task> {
    return api.delete<Task>(`/tasks/${taskId}/blocks/${blockId}`).then((r) => r.data);
  },

  blockDone(taskId: number, blockId: number, confirmed_remaining_minutes: number): Promise<Task> {
    return api.post<Task>(`/tasks/${taskId}/blocks/${blockId}/done`, { confirmed_remaining_minutes })
      .then((r) => r.data);
  },

  blockReschedule(taskId: number, blockId: number): Promise<Task> {
    return api.post<Task>(`/tasks/${taskId}/blocks/${blockId}/reschedule`).then((r) => r.data);
  },
};
