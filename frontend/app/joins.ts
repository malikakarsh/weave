"use client";

// Client for the multi-CSV join endpoints.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface JoinTable {
  name: string;
  source: string;
  columns: string[];
  row_count: number;
  sample: Record<string, string[]>;
}

export interface JoinCandidate {
  left_table: string;
  left_col: string;
  right_table: string;
  right_col: string;
  overlap: number;
  confidence: number;
  extra_pairs?: [string, string][];   // additional key pairs for a composite join
}

export interface JoinStep {
  left_table: string;
  left_col: string;
  right_table: string;
  right_col: string;
  how?: string;
  extra_pairs?: [string, string][];   // ANDed with the primary pair (composite join)
}

/** All (left, right) column pairs of a candidate/step: primary + any composite extras. */
export function joinPairs(c: { left_col: string; right_col: string; extra_pairs?: [string, string][] }): [string, string][] {
  return [[c.left_col, c.right_col], ...(c.extra_pairs ?? [])];
}

export interface DetectResult {
  tables: JoinTable[];
  candidates: JoinCandidate[];
  plan: JoinPlan;        // auto-built spanning join (connects all joinable tables)
  unjoined: string[];    // tables with no join path
}

export interface JoinPlan {
  base_table: string;
  steps: JoinStep[];
}

async function detail(res: Response): Promise<string> {
  return (await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`;
}

export async function detectJoins(files: File[]): Promise<DetectResult> {
  const body = new FormData();
  files.forEach((f) => body.append("files", f));
  const res = await fetch(`${API}/joins/detect`, { method: "POST", body, credentials: "include" });
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export async function executeJoin(
  files: File[],
  plan: JoinPlan,
): Promise<{ name: string; columns: string[]; row_count: number; csv: string }> {
  const body = new FormData();
  files.forEach((f) => body.append("files", f));
  body.append("plan", JSON.stringify(plan));
  const res = await fetch(`${API}/joins/execute`, { method: "POST", body, credentials: "include" });
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

/** Build a sensible default connected plan from detected candidates. */
export function buildDefaultPlan(tables: JoinTable[], candidates: JoinCandidate[]): JoinPlan {
  // Base = the table that references the most others (fact table), else the largest.
  const leftCounts: Record<string, number> = {};
  candidates.forEach((c) => { leftCounts[c.left_table] = (leftCounts[c.left_table] ?? 0) + 1; });
  const base =
    Object.keys(leftCounts).sort((a, b) => leftCounts[b] - leftCounts[a])[0] ??
    [...tables].sort((a, b) => b.row_count - a.row_count)[0]?.name ??
    tables[0]?.name ?? "";

  // Greedily add candidates that bring in exactly one NEW table (a step whose
  // both tables are already joined would be a redundant/cyclic join).
  const reachable = new Set([base]);
  const steps: JoinStep[] = [];
  const pool = [...candidates];
  let added = true;
  while (added) {
    added = false;
    for (let i = 0; i < pool.length; i++) {
      const c = pool[i];
      const l = reachable.has(c.left_table);
      const r = reachable.has(c.right_table);
      if (l !== r) {   // exactly one side is new
        steps.push({ left_table: c.left_table, left_col: c.left_col, right_table: c.right_table, right_col: c.right_col, how: "left", extra_pairs: c.extra_pairs });
        reachable.add(c.left_table);
        reachable.add(c.right_table);
        pool.splice(i, 1);
        added = true;
        break;
      }
    }
  }
  return { base_table: base, steps };
}
