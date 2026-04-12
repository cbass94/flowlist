// FlowList — Axios API client
// All requests go through /api (proxied to FastAPI by Vite / Caddy in prod).
// Response interceptor auto-unwraps the { data, error, meta } envelope so
// service functions can use `r.data` directly.

import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

// Unwrap envelope and surface API errors as thrown Errors
api.interceptors.response.use(
  (response) => {
    const body = response.data;
    if (
      body !== null &&
      typeof body === "object" &&
      "data" in body &&
      "error" in body
    ) {
      if (body.error) {
        const err = new Error(body.error.message || "API error") as Error & {
          code?: string;
        };
        err.code = body.error.code;
        return Promise.reject(err);
      }
      return { ...response, data: body.data };
    }
    return response;
  },
  (error) => {
    if (error.response?.data?.error) {
      const apiError = new Error(
        error.response.data.error.message || "API error"
      ) as Error & { code?: string; status?: number };
      apiError.code = error.response.data.error.code;
      apiError.status = error.response.status;
      return Promise.reject(apiError);
    }
    return Promise.reject(error);
  }
);

export default api;
