"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../useAuth";

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

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const isAdmin = user?.role === "admin";

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
    return <main className="min-h-screen grid place-items-center bg-gray-50 text-gray-400">Loading…</main>;
  }

  if (!user || !isAdmin) {
    return (
      <main className="min-h-screen grid place-items-center bg-gray-50 text-center px-6">
        <div>
          <p className="text-lg font-semibold text-gray-900">Admin access required</p>
          <p className="mt-1 text-sm text-gray-500">{user ? "Your account isn't an admin." : "Please sign in."}</p>
          <Link href="/" className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:underline">← Back to Weave</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900">
      <header className="sticky top-0 z-10 bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-3">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-700">← Weave</Link>
          <span className="text-sm font-semibold">Admin</span>
          <span className="ml-auto text-xs text-gray-400">{user.email}</span>
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
            <div key={c.label} className="rounded-xl border border-gray-200 bg-white p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{c.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{c.value ?? "—"}</p>
            </div>
          ))}
        </div>

        {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

        {/* Users table */}
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
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
            <tbody className="divide-y divide-gray-100">
              {users === null ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">Loading…</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">No users yet.</td></tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        {u.picture
                          // eslint-disable-next-line @next/next/no-img-element
                          ? <img src={u.picture} alt="" width={28} height={28} className="w-7 h-7 rounded-full" referrerPolicy="no-referrer" />
                          : <span className="w-7 h-7 rounded-full bg-gray-200 grid place-items-center text-xs font-semibold text-gray-600">{(u.name ?? u.email ?? "?").charAt(0).toUpperCase()}</span>}
                        <div className="min-w-0">
                          <p className="font-medium text-gray-900 truncate">{u.name ?? "—"}</p>
                          <p className="text-xs text-gray-400 truncate">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${u.role === "admin" ? "bg-indigo-50 text-indigo-600" : "bg-gray-100 text-gray-600"}`}>{u.role}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.visits}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.today_usage}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.total_usage}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {u.role === "admin" ? (
                        <span className="text-gray-400">Unlimited</span>
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
                            className="w-16 rounded border border-gray-300 px-2 py-1 text-sm tabular-nums focus:outline-none focus:border-indigo-400"
                          />
                          <button disabled={saving} onClick={() => saveLimit(u)} className="text-xs font-medium text-indigo-600 hover:underline disabled:opacity-50">Save</button>
                          <button onClick={() => setEditingId(null)} className="text-xs text-gray-400 hover:text-gray-600">Cancel</button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          <span className="tabular-nums">{u.effective_limit}</span>
                          {u.daily_limit === null && <span className="text-xs text-gray-400">(default)</span>}
                          <button
                            onClick={() => { setEditingId(u.id); setDraft(u.daily_limit === null ? "" : String(u.daily_limit)); setError(null); }}
                            className="text-xs font-medium text-indigo-600 hover:underline"
                          >
                            Edit
                          </button>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{when(u.last_seen_at)}</td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{when(u.created_at)}</td>
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
