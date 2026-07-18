"use client";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SchemaColumn {
  name: string;
  type: string;        // "String" | "Float" | "Date"
  sample: string[];
  min?: string | null;  // typed range: numeric for Float, date for Date, A→Z for String
  max?: string | null;
}

export interface SchemaInfo {
  row_count: number;
  columns: SchemaColumn[];
}

export async function fetchSchema(file: File): Promise<SchemaInfo> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API}/schema`, { method: "POST", body, credentials: "include" });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Failed to read schema");
  return res.json();
}

/**
 * True when the prompt asks to see the columns/schema rather than build a
 * chart. Content-based: it must mention columns/schema/fields and must NOT read
 * like a chart or aggregation request. Handles phrasings like "list all column
 * names in the dataset" as well as "show columns".
 */
export function isSchemaRequest(prompt: string): boolean {
  const p = prompt.trim().toLowerCase();
  const chartOrAgg = /\b(chart|plot|graph|diagram|bar|line|pie|scatter|map|histogram|heatmap|network|radar|box\s?plot|violin|trend|distribution|correlation|average|avg|median|mean|sum|count|total|top\s*\d|over\s+time|vs\b|versus|per\b|by\b|group(ed)?\s+by|breakdown)\b/;
  if (chartOrAgg.test(p)) return false;
  return /\b(schema|columns?|column\s+names?|fields?|field\s+names?|headers?|data\s?types?|dtypes)\b/.test(p);
}
