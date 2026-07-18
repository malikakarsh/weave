"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Usage {
  used: number;
  limit: number | null; // null = unlimited (admin)
  remaining: number | null;
}

export interface AuthUser {
  sub: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  role: "admin" | "user";
  usage: Usage;
}

/**
 * Auth state backed by the FastAPI httpOnly session cookie. The cookie itself
 * is not readable from JS (by design); we learn who the user is by calling
 * `/auth/me` with credentials. `login()` sends the browser to the backend's
 * Google OAuth entry point; after the round-trip the backend redirects home
 * and this hook re-fetches on mount.
 */
export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API}/auth/me`, { credentials: "include" });
      setUser(res.ok ? await res.json() : null);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const pingedRef = useRef(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API}/auth/me`, { credentials: "include" });
        const next = res.ok ? ((await res.json()) as AuthUser) : null;
        if (!cancelled) setUser(next);
        // Count this page open once per load, only when authenticated.
        if (next && !pingedRef.current) {
          pingedRef.current = true;
          fetch(`${API}/auth/visit`, { method: "POST", credentials: "include" }).catch(() => {});
        }
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(() => {
    window.location.href = `${API}/auth/login/google`;
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });
    } finally {
      setUser(null);
    }
  }, []);

  return { user, loading, login, logout, refresh };
}
