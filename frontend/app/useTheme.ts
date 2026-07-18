"use client";

import { useCallback, useEffect, useState } from "react";

const KEY = "weave-theme";

/**
 * Shared light/dark theme, persisted to localStorage so it stays consistent
 * across pages (landing, docs, …). Returns a `[dark, setDark]` tuple that drops
 * into existing `useState<boolean>` call sites; `setDark` accepts a boolean or
 * an updater and writes through to localStorage.
 */
export function useTheme(): readonly [boolean, (d: boolean | ((prev: boolean) => boolean)) => void] {
  const [dark, setDarkState] = useState(true);

  // Hydrate from storage after mount (avoids SSR/client mismatch).
  useEffect(() => {
    const saved = localStorage.getItem(KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved === "light") setDarkState(false);
    else if (saved === "dark") setDarkState(true);
  }, []);

  const setDark = useCallback((d: boolean | ((prev: boolean) => boolean)) => {
    setDarkState((prev) => {
      const next = typeof d === "function" ? d(prev) : d;
      try { localStorage.setItem(KEY, next ? "dark" : "light"); } catch { /* ignore */ }
      return next;
    });
  }, []);

  return [dark, setDark] as const;
}
