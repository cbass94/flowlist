import api from "./api";
import type { ParseRequest, ParseResponse } from "../types";

export const aiApi = {
  parseTask(req: ParseRequest): Promise<ParseResponse> {
    return api.post<ParseResponse>("/ai/parse-task", req).then((r) => r.data);
  },
};
