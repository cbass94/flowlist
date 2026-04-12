import api from "./api";
import type { Invite } from "../types";

export const invitesApi = {
  list(): Promise<Invite[]> {
    return api.get<Invite[]>("/invites").then((r) => r.data);
  },

  create(email: string): Promise<Invite> {
    return api.post<Invite>("/invites", { email }).then((r) => r.data);
  },

  revoke(id: number): Promise<void> {
    return api.delete(`/invites/${id}`).then(() => undefined);
  },

  verify(token: string): Promise<{ email: string; valid: boolean }> {
    return api
      .get<{ email: string; valid: boolean }>("/invites/verify", {
        params: { token },
      })
      .then((r) => r.data);
  },
};
