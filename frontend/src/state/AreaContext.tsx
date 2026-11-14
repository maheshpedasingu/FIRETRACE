import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { AreaQuery } from "../lib/area";

interface AreaState {
  query: AreaQuery | null; // null until the user selects an area — there is no default region
  setQuery: (q: AreaQuery | null) => void;
  /** Stable string identity of the query, for reload keys. */
  key: string | null;
}

const AreaContext = createContext<AreaState | null>(null);

export function AreaProvider({ children, initial = null }: { children: ReactNode; initial?: AreaQuery | null }) {
  const [query, setQuery] = useState<AreaQuery | null>(initial);
  const value = useMemo(
    () => ({ query, setQuery, key: query ? JSON.stringify(query) : null }),
    [query],
  );
  return <AreaContext.Provider value={value}>{children}</AreaContext.Provider>;
}

export function useArea(): AreaState {
  const ctx = useContext(AreaContext);
  if (!ctx) throw new Error("useArea must be used inside <AreaProvider>");
  return ctx;
}
