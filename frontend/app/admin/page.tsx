"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../useAuth";
import { useTheme } from "../useTheme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AdminUser {
  id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  role: "admin" | "user";
  visits: number;
  total_usage: number;
  today_usage: number;
  daily_limit: number | null;      // per-user override, or null = default
  effective_limit: number;
  created_at: string | null;
  last_seen_at: string | null;
}

interface Stats {
  users: number;
  calls_total: number;
  calls_today: number;
  default_limit: number;
}

interface ModelMetric {
  provider: string;
  model: string;
  calls: number;
  errors: number;
  error_rate: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  last_used: string | null;
  calls_per_min: number;
}

interface Metrics {
  models: ModelMetric[];
  totals: {
    calls: number; errors: number; error_rate: number;
    input_tokens: number; output_tokens: number; cost_usd: number | null; calls_per_min: number;
  };
  ts: string;
}

function fmtInt(n: number): string {
  return n >= 1000 ? n.toLocaleString() : String(n);
}
function fmtCost(c: number | null): string {
  if (c === null) return "—";
  if (c === 0) return "$0";
  return c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`;
}

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [dark, setDark] = useTheme();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [liveOn, setLiveOn] = useState(false);

  const isAdmin = user?.role === "admin";

  // Live model-performance metrics over SSE (cookie auth is sent automatically).
  useEffect(() => {
    if (!isAdmin) return;
    const es = new EventSource(`${API}/admin/metrics/stream`, { withCredentials: true });
    es.addEventListener("metrics", (e) => {
      try { setMetrics(JSON.parse((e as MessageEvent).data)); setLiveOn(true); } catch { /* ignore */ }
    });
    es.onerror = () => setLiveOn(false);   // browser auto-reconnects
    return () => es.close();
  }, [isAdmin]);

  // The admin route can load without the main page ever mounting, so apply the
  // `.dark` class here too (theme itself is shared via useTheme/localStorage).
  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
  }, [dark]);

  async function saveLimit(u: AdminUser) {
    const trimmed = draft.trim();
    // empty input clears the override (back to the global default)
    const value = trimmed === "" ? null : Number(trimmed);
    if (value !== null && (!Number.isFinite(value) || value < 0)) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/admin/users/${u.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ daily_limit: value }),
      });
      if (!res.ok) throw new Error();
      const upd = await res.json();
      setUsers((prev) =>
        (prev ?? []).map((x) =>
          x.id === u.id ? { ...x, daily_limit: upd.daily_limit, effective_limit: upd.effective_limit } : x
        )
      );
      setEditingId(null);
    } catch {
      setError("Failed to update the limit.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    (async () => {
      try {
        const [u, s] = await Promise.all([
          fetch(`${API}/admin/users`, { credentials: "include" }).then((r) => r.json()),
          fetch(`${API}/admin/stats`, { credentials: "include" }).then((r) => r.json()),
        ]);
        if (!cancelled) { setUsers(u); setStats(s); }
      } catch {
        if (!cancelled) setError("Failed to load admin data.");
      }
    })();
    return () => { cancelled = true; };
  }, [isAdmin]);

  if (loading) {
    return <main className="min-h-screen grid place-items-center bg-gray-50 dark:bg-[#0f1117] text-gray-400 dark:text-white/40">Loading…</main>;
  }

  if (!user || !isAdmin) {
    return (
      <main className="min-h-screen grid place-items-center bg-gray-50 dark:bg-[#0f1117] text-center px-6">
        <div>
          <p className="text-lg font-semibold text-gray-900 dark:text-white/90">Admin access required</p>
          <p className="mt-1 text-sm text-gray-500 dark:text-white/50">{user ? "Your account isn't an admin." : "Please sign in."}</p>
          <Link href="/" className="mt-4 inline-block text-sm font-medium text-red-600 dark:text-indigo-300 hover:underline">← Back to Weave</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white/90">
      <header className="sticky top-0 z-10 bg-white dark:bg-[#12141d] border-b border-gray-200 dark:border-white/10">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-3">
          <Link href="/" className="text-sm text-gray-400 dark:text-white/40 hover:text-gray-700 dark:hover:text-white/80">← Weave</Link>
          <span className="text-sm font-semibold">Admin</span>
          <span className="ml-auto text-xs text-gray-400 dark:text-white/40">{user.email}</span>
          <button
            onClick={() => setDark((d) => !d)}
            aria-label="Toggle theme"
            className="grid place-items-center w-8 h-8 rounded-lg border border-gray-200 dark:border-white/10 text-gray-500 dark:text-white/50 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          >
            {dark ? (
              <svg className="w-4 h-4 text-yellow-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" /><path strokeLinecap="round" d="M12 1v2m0 18v2M4.2 4.2l1.4 1.4m12.8 12.8l1.4 1.4M1 12h2m18 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" /></svg>
            ) : (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
            )}
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          {[
            { label: "Users", value: stats?.users },
            { label: "LLM calls today", value: stats?.calls_today },
            { label: "LLM calls total", value: stats?.calls_total },
            { label: "Default daily limit", value: stats?.default_limit },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-white/40">{c.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{c.value ?? "—"}</p>
            </div>
          ))}
        </div>

        {error && <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

        {/* Model performance (live) */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-sm font-semibold">Model performance</h2>
            <span className={`inline-flex items-center gap-1.5 text-xs ${liveOn ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-white/40"}`}>
              <span className={`w-2 h-2 rounded-full ${liveOn ? "bg-emerald-500 animate-pulse" : "bg-gray-300 dark:bg-white/20"}`} />
              {liveOn ? "live" : "connecting…"}
            </span>
            {metrics && (
              <span className="ml-auto text-xs text-gray-400 dark:text-white/40 tabular-nums">
                {fmtInt(metrics.totals.calls)} calls · {metrics.totals.calls_per_min}/min · {fmtCost(metrics.totals.cost_usd)}
              </span>
            )}
          </div>
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 dark:text-white/50">
                <tr className="text-left">
                  <th className="px-4 py-3 font-medium">Model</th>
                  <th className="px-4 py-3 font-medium text-right">Calls</th>
                  <th className="px-4 py-3 font-medium text-right">/min</th>
                  <th className="px-4 py-3 font-medium text-right">Avg ms</th>
                  <th className="px-4 py-3 font-medium text-right">p95 ms</th>
                  <th className="px-4 py-3 font-medium text-right">Errors</th>
                  <th className="px-4 py-3 font-medium text-right">Tokens (in / out)</th>
                  <th className="px-4 py-3 font-medium text-right">Est. cost</th>
                  <th className="px-4 py-3 font-medium">Last call</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                {!metrics ? (
                  <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-400 dark:text-white/40">Waiting for the first metrics…</td></tr>
                ) : metrics.models.length === 0 ? (
                  <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-400 dark:text-white/40">No LLM calls yet — generate a chart to see live stats.</td></tr>
                ) : (
                  metrics.models.map((m) => (
                    <tr key={`${m.provider}/${m.model}`} className="hover:bg-gray-50 dark:hover:bg-white/5">
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900 dark:text-white/90">{m.model}</div>
                        <div className="text-xs text-gray-400 dark:text-white/40">{m.provider}</div>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{fmtInt(m.calls)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{m.calls_per_min}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{m.avg_latency_ms ?? "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{m.p95_latency_ms ?? "—"}</td>
                      <td className={`px-4 py-3 text-right tabular-nums ${m.errors ? "text-red-600 dark:text-red-400" : "text-gray-400 dark:text-white/40"}`}>
                        {m.errors ? `${m.errors} (${(m.error_rate * 100).toFixed(0)}%)` : "0"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-500 dark:text-white/50">{fmtInt(m.input_tokens)} / {fmtInt(m.output_tokens)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{fmtCost(m.cost_usd)}</td>
                      <td className="px-4 py-3 text-gray-500 dark:text-white/50 whitespace-nowrap">{when(m.last_used)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Users table */}
        <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 dark:text-white/50">
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium text-right">Page opens</th>
                <th className="px-4 py-3 font-medium text-right">Today</th>
                <th className="px-4 py-3 font-medium text-right">Total calls</th>
                <th className="px-4 py-3 font-medium">Daily limit</th>
                <th className="px-4 py-3 font-medium">Last seen</th>
                <th className="px-4 py-3 font-medium">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {users === null ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400 dark:text-white/40">Loading…</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400 dark:text-white/40">No users yet.</td></tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-white/5">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        {u.picture
                          // eslint-disable-next-line @next/next/no-img-element
                          ? <img src={u.picture} alt="" width={28} height={28} className="w-7 h-7 rounded-full" referrerPolicy="no-referrer" />
                          : <span className="w-7 h-7 rounded-full bg-gray-200 dark:bg-white/10 grid place-items-center text-xs font-semibold text-gray-600 dark:text-white/60">{(u.name ?? u.email ?? "?").charAt(0).toUpperCase()}</span>}
                        <div className="min-w-0">
                          <p className="font-medium text-gray-900 dark:text-white/90 truncate">{u.name ?? "—"}</p>
                          <p className="text-xs text-gray-400 dark:text-white/40 truncate">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${u.role === "admin" ? "bg-red-50 text-red-600 dark:bg-indigo-500/15 dark:text-indigo-300" : "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-white/60"}`}>{u.role}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.visits}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.today_usage}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.total_usage}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {u.role === "admin" ? (
                        <span className="text-gray-400 dark:text-white/40">Unlimited</span>
                      ) : editingId === u.id ? (
                        <span className="inline-flex items-center gap-1.5">
                          <input
                            type="number"
                            min={0}
                            autoFocus
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") saveLimit(u); if (e.key === "Escape") setEditingId(null); }}
                            placeholder={String(stats?.default_limit ?? "")}
                            className="w-16 rounded border border-gray-300 dark:border-white/15 bg-white dark:bg-white/5 text-gray-900 dark:text-white/90 px-2 py-1 text-sm tabular-nums focus:outline-none focus:border-red-400 dark:focus:border-indigo-400"
                          />
                          <button disabled={saving} onClick={() => saveLimit(u)} className="text-xs font-medium text-red-600 dark:text-indigo-300 hover:underline disabled:opacity-50">Save</button>
                          <button onClick={() => setEditingId(null)} className="text-xs text-gray-400 dark:text-white/40 hover:text-gray-600 dark:hover:text-white/70">Cancel</button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          <span className="tabular-nums">{u.effective_limit}</span>
                          {u.daily_limit === null && <span className="text-xs text-gray-400 dark:text-white/40">(default)</span>}
                          <button
                            onClick={() => { setEditingId(u.id); setDraft(u.daily_limit === null ? "" : String(u.daily_limit)); setError(null); }}
                            className="text-xs font-medium text-red-600 dark:text-indigo-300 hover:underline"
                          >
                            Edit
                          </button>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-white/50 whitespace-nowrap">{when(u.last_seen_at)}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-white/50 whitespace-nowrap">{when(u.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
