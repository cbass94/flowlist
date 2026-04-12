import api from "./api";
import type {
  CompleteRequest,
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

  createPart2(id: number): Promise<Task> {
    return api.post<Task>(`/tasks/${id}/create-part2`).then((r) => r.data);
  },
};
