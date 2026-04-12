import { useQuery } from "@tanstack/react-query";
import { authApi } from "../services/auth";

export function useAuth() {
  const { data, isLoading } = useQuery({
    queryKey: ["auth", "status"],
    queryFn: authApi.status,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return {
    user: data?.user ?? null,
    isAuthenticated: data?.authenticated ?? false,
    isLoading,
  };
}
