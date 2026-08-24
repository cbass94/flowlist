/**
 * Backlog search state, lifted out of BacklogView so the collapsed search
 * control in the top nav and the list that it filters can share one value.
 *
 * The query resets whenever you leave the backlog route — otherwise a filter
 * set on the way out would silently still be applied on the way back in, with
 * no visible input to explain the missing tasks.
 */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";

interface SearchContextValue {
  query: string;
  setQuery: (q: string) => void;
  clear: () => void;
}

const SearchContext = createContext<SearchContextValue | null>(null);

export function SearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  const location = useLocation();
  const onBacklog = location.pathname === "/";

  useEffect(() => {
    if (!onBacklog) setQuery("");
  }, [onBacklog]);

  const value = useMemo(
    () => ({ query, setQuery, clear: () => setQuery("") }),
    [query]
  );

  return <SearchContext.Provider value={value}>{children}</SearchContext.Provider>;
}

export function useSearch(): SearchContextValue {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearch must be used inside a SearchProvider");
  return ctx;
}
