import { useMutation } from "@tanstack/react-query";
import { aiApi } from "../services/ai";
import type { ParseRequest, ParseResponse } from "../types";

export function useTaskParse() {
  return useMutation<ParseResponse, Error, ParseRequest>({
    mutationFn: (req) => aiApi.parseTask(req),
  });
}
