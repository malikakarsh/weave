"use client";

// Thin client for the user-scoped thread persistence API. Every call carries
// the session cookie (credentials: include) so the backend knows the user.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ThreadSummary {
  id: string;
  title: string;
  chart_count: number;
  updated_at: string;
}

export interface ChartRow {
  id?: string;
  sub_prompt: string;
  mapping: Record<string, unknown> | null;
  html: string | null;
  history: { role: string; content: string }[] | null;
  position: number;
}

export interface ThreadDetail {
  id: string;
  title: string;
  csv_name: string;
  csv_content: string;
  charts: ChartRow[];
  updated_at: string;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`);
  return res.json();
}

const opts = (method: string, body?: unknown): RequestInit => ({
  method,
  credentials: "include",
  headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
  body: body !== undefined ? JSON.stringify(body) : undefined,
});

export const listThreads = () =>
  fetch(`${API}/threads`, { credentials: "include" }).then(json<ThreadSummary[]>);

export const getThread = (id: string) =>
  fetch(`${API}/threads/${id}`, { credentials: "include" }).then(json<ThreadDetail>);

export const createThread = (body: { title: string; csv_name: string; csv_content: string }) =>
  fetch(`${API}/threads`, opts("POST", body)).then(json<ThreadDetail>);

export const saveCharts = (id: string, charts: ChartRow[]) =>
  fetch(`${API}/threads/${id}/charts`, opts("PUT", charts)).then(json<ThreadDetail>);

export const renameThread = (id: string, title: string) =>
  fetch(`${API}/threads/${id}`, opts("PATCH", { title })).then(json<ThreadSummary>);

export const deleteThread = (id: string) =>
  fetch(`${API}/threads/${id}`, opts("DELETE")).then((r) => {
    if (!r.ok) throw new Error("Failed to delete");
  });
