import api from "./api";
import type { AssistantRequest, AssistantResponse, FeedbackRequest, ParseRequest, ParseResponse } from "../types";

export const aiApi = {
  parseTask(req: ParseRequest): Promise<ParseResponse> {
    return api.post<ParseResponse>("/ai/parse-task", req).then((r) => r.data);
  },

  getTaskAssistance(req: AssistantRequest): Promise<AssistantResponse> {
    return api.post<AssistantResponse>("/ai/task-assistant", req).then((r) => r.data);
  },

  submitFeedback(req: FeedbackRequest): Promise<void> {
    return api.post("/ai/assistant-feedback", req).then(() => undefined);
  },
};
