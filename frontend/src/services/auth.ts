import api from "./api";
import type { AuthStatus } from "../types";

export const authApi = {
  status(): Promise<AuthStatus> {
    return api.get<AuthStatus>("/auth/status").then((r) => r.data);
  },

  logout(): Promise<void> {
    return api.post("/auth/logout").then(() => undefined);
  },
};
