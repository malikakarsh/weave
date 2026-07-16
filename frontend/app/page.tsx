"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EXPORT_PRESETS = [
  { label: "HD", w: 1280, h: 720 },
  { label: "Full HD", w: 1920, h: 1080 },
  { label: "Social", w: 1200, h: 630 },
  { label: "Square", w: 1080, h: 1080 },
];

const PLAYGROUND_DATASETS = [
  {
    id: "stocks",
    name: "Stock Prices",
    description: "AAPL, AMZN, GOOG, IBM & MSFT - daily closes 2000-2010",
    emoji: "📈",
    prompt: "show stock price trend over time for each company as a multi-series line chart, and show average stock price per company as a bar chart",
  },
  {
    id: "revenue",
    name: "Company Revenue",
    description: "Monthly revenue across multiple companies over several years",
    emoji: "💰",
    prompt: "show total revenue per company as a bar chart sorted descending, and revenue trend over time for each company as a line chart",
  },
  {
    id: "world_cities",
    name: "World Cities",
    description: "55 major cities with population and continent",
    emoji: "🌍",
    prompt: "plot world cities on a symbol map sized by population and colored by continent, and show total population by continent as a bar chart",
  },
  {
    id: "diamonds",
    name: "Diamonds",
    description: "Prices and attributes: cut, color, clarity, carat",
    emoji: "💎",
    prompt: "show average diamond price by cut as a bar chart, and price distribution by cut as a box-style bar chart",
  },
  {
    id: "restaurants",
    name: "NYC Restaurants",
    description: "Inspection records with grades, violations, and borough",
    emoji: "🍕",
    prompt: "show inspection count by borough as a bar chart, and a breakdown of inspection grades as a pie chart",
  },
  {
    id: "iris",
    name: "Iris Flowers",
    description: "Classic dataset: sepal/petal measurements for 3 species",
    emoji: "🌸",
    prompt: "show sepal length vs sepal width as a scatter plot colored by species, and average petal length by species as a bar chart",
  },
] as const;

const LIGHT_WEAVE_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">' +
  '<rect x="0" y="0" width="4" height="4" fill="black" fill-opacity="0.07"/>' +
  '<rect x="4" y="4" width="4" height="4" fill="black" fill-opacity="0.07"/>' +
  '<path d="M0 0H8M0 4H8M0 0V8M4 0V8" stroke="black" stroke-opacity="0.07" stroke-width="0.4"/>' +
  '</svg>'
);

const DARK_WEAVE_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">' +
  '<rect x="0" y="0" width="5" height="5" fill="white" fill-opacity="0.045"/>' +
  '<rect x="5" y="5" width="5" height="5" fill="white" fill-opacity="0.045"/>' +
  '<path d="M0 0H10M0 5H10M0 0V10M5 0V10" stroke="white" stroke-opacity="0.07" stroke-width="0.5"/>' +
  '</svg>'
);

type HistoryMessage = { role: "user" | "assistant"; content: string };

interface ChartSession {
  id: string;
  subPrompt: string;
  status: "pending" | "done" | "error";
  html: string | null;
  mapping: Record<string, unknown> | null;
  history: HistoryMessage[];
  error: string | null;
}

// ── Per-chart card ────────────────────────────────────────────────────────────

interface ChartCardProps {
  session: ChartSession;
  file: File;
  dark: boolean;
  onUpdate: (id: string, updates: Partial<ChartSession>) => void;
  onDelete: (id: string) => void;
  onRegenerate: (id: string, prompt: string) => void;
}

function ChartCard({ session, file, dark, onUpdate, onDelete, onRegenerate }: ChartCardProps) {
  const [refinePrompt, setRefinePrompt] = useState("");
  const [refining, setRefining] = useState(false);
  const [insights, setInsights] = useState<string[] | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [customW, setCustomW] = useState("1280");
  const [customH, setCustomH] = useState("720");
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage({ type: "weave-theme", dark }, "*");
  }, [dark]);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      // Only handle messages from this card's iframe
      if (e.source !== iframeRef.current?.contentWindow) return;
      if (e.data?.type === "weave-height" && iframeRef.current) {
        iframeRef.current.style.height = Math.max(e.data.height, 300) + "px";
      }
      if (e.data?.type === "weave-svg") {
        const blob = new Blob([e.data.content], { type: "image/svg+xml" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `chart_${e.data.w}x${e.data.h}.svg`;
        a.click();
        URL.revokeObjectURL(url);
        setExporting(false);
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  async function refine() {
    if (!refinePrompt.trim() || !session.mapping) return;
    const instruction = refinePrompt.trim();

    if (/^regenerate$/i.test(instruction)) {
      setRefinePrompt("");
      onRegenerate(session.id, session.subPrompt);
      return;
    }

    setRefining(true);
    setRefinePrompt("");

    const nextHistory: HistoryMessage[] = [
      ...session.history,
      { role: "user", content: instruction },
    ];
    onUpdate(session.id, { history: nextHistory });

    const body = new FormData();
    body.append("file", file);
    body.append("mapping", JSON.stringify(session.mapping));
    body.append("history", JSON.stringify(session.history));
    body.append("instruction", instruction);

    try {
      const res = await fetch(`${API}/refine`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      onUpdate(session.id, {
        html: data.html,
        mapping: data.mapping,
        history: [...nextHistory, { role: "assistant", content: JSON.stringify(data.mapping) }],
      });
      setInsights(null);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 100);
    } catch {
      onUpdate(session.id, { history: session.history });
    } finally {
      setRefining(false);
    }
  }

  async function analyze() {
    if (!session.mapping) return;
    setAnalyzing(true);
    setInsights(null);
    const body = new FormData();
    body.append("file", file);
    body.append("mapping", JSON.stringify(session.mapping));
    body.append("prompt", session.history.find(m => m.role === "user")?.content ?? "");
    try {
      const res = await fetch(`${API}/insights`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Insights failed");
      setInsights(data.insights);
    } catch {
      // silent — non-critical feature
    } finally {
      setAnalyzing(false);
    }
  }

  function exportSvg(w: number, h: number) {
    if (!iframeRef.current?.contentWindow) return;
    setExporting(true);
    iframeRef.current.contentWindow.postMessage({ type: "weave-export", width: w, height: h }, "*");
  }

  return (
    <div
      className="flex flex-col gap-4 rounded-2xl p-5"
      style={dark ? {
        background: "#0d1018",
        border: "1px solid rgba(255,255,255,0.08)",
      } : {
        background: "#ffffff",
        border: "1px solid #e5e7eb",
        boxShadow: "0 8px 40px rgba(0,0,0,0.13), 0 2px 8px rgba(0,0,0,0.07)",
      }}
    >
      {/* Delete button */}
      <div className="flex justify-end -mb-1">
        <button
          onClick={() => onDelete(session.id)}
          title="Delete chart"
          className="shrink-0 flex items-center justify-center w-8 h-8 rounded-md transition-colors cursor-pointer"
          style={{ color: dark ? "rgba(255,255,255,0.25)" : "#d1d5db" }}
          onMouseEnter={e => (e.currentTarget.style.color = dark ? "rgba(239,68,68,0.8)" : "#ef4444")}
          onMouseLeave={e => (e.currentTarget.style.color = dark ? "rgba(255,255,255,0.25)" : "#d1d5db")}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Pending */}
      {session.status === "pending" && (
        <div className="flex items-center justify-center h-64 gap-3 text-sm text-gray-400 dark:text-white/30">
          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Generating…
        </div>
      )}

      {/* Error */}
      {session.status === "error" && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
          {session.error ?? "Chart generation failed"}
        </div>
      )}

      {/* Iframe */}
      {session.status === "done" && session.html && (
        <iframe
          ref={iframeRef}
          srcDoc={session.html}
          onLoad={() => iframeRef.current?.contentWindow?.postMessage({ type: "weave-theme", dark }, "*")}
          style={{ width: "100%", height: "420px", border: "none", display: "block", borderRadius: "8px" }}
          sandbox="allow-scripts allow-same-origin"
        />
      )}

      {/* Conversation history */}
      {session.status === "done" && session.history.filter(m => m.role === "user").length > 0 && (
        <div
          className="flex flex-col gap-2 max-h-32 overflow-y-auto pr-1"
          style={{ scrollbarWidth: "thin", scrollbarColor: dark ? "#374151 transparent" : "#cbd5e1 transparent" }}
        >
          {session.history.filter(m => m.role === "user").map((m, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className={`mt-1 w-5 h-5 rounded-full ${dark ? "bg-indigo-500" : "bg-red-600"} flex items-center justify-center shrink-0 text-[10px] text-white font-bold`}>
                U
              </span>
              <p className="text-sm text-gray-700 dark:text-white/80 leading-relaxed pt-0.5">{m.content}</p>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      )}

      {/* Per-chart refine bar */}
      {session.status === "done" && (
        <div className="flex gap-2">
          <input
            className="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15 rounded-xl
              px-4 py-3 text-sm placeholder-gray-400 dark:placeholder-white/30 text-gray-900 dark:text-white
              focus:outline-none focus:border-red-500 dark:focus:border-indigo-400"
            placeholder="Refine this chart… e.g. sort descending, change color to red, show top 10 only"
            value={refinePrompt}
            onChange={(e) => setRefinePrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); refine(); } }}
            disabled={refining}
          />
          <button
            onClick={refine}
            disabled={!refinePrompt.trim() || refining}
            className={`flex items-center justify-center rounded-xl ${dark ? "bg-indigo-500 hover:bg-indigo-400" : "bg-red-600 hover:bg-red-500"}
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-4 shrink-0`}
          >
            {refining
              ? <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              : <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                </svg>
            }
          </button>
        </div>
      )}

      {/* Analyze + Export */}
      {session.status === "done" && session.mapping && (
        <div className="flex flex-col gap-3">
          {insights && (
            <div className="rounded-xl bg-gray-50 dark:bg-white/3 border border-gray-200 dark:border-white/10 p-4">
              <p className="text-xs font-medium text-gray-400 dark:text-white/40 uppercase tracking-widest mb-2">Key insights</p>
              <ul className="flex flex-col gap-2">
                {insights.map((ins, i) => (
                  <li key={i} className="flex gap-3 text-sm text-gray-700 dark:text-white/80 leading-relaxed">
                    <span className="text-indigo-500 dark:text-indigo-400 mt-0.5 shrink-0">›</span>{ins}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            {!insights && (
              <button onClick={analyze} disabled={analyzing}
                className="flex items-center gap-2 rounded-xl border border-gray-200 dark:border-white/15
                  hover:border-indigo-400/60 hover:bg-indigo-50 dark:hover:bg-indigo-400/5
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-4 py-2 text-sm
                  text-gray-700 dark:text-white shrink-0">
                {analyzing
                  ? <><svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>Analyzing…</>
                  : <><span>✦</span>Analyze</>}
              </button>
            )}

            <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-white/40 uppercase tracking-widest mr-1">Export SVG</span>
            <div className="flex flex-wrap gap-1.5">
              {EXPORT_PRESETS.map((p) => (
                <button key={p.label} onClick={() => exportSvg(p.w, p.h)} disabled={exporting}
                  className="rounded-lg border border-gray-200 dark:border-white/15 hover:border-gray-300 dark:hover:border-white/30
                    px-2.5 py-1 text-xs text-gray-700 dark:text-white
                    disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                  {p.label} <span className="text-gray-400 dark:text-white/40">{p.w}×{p.h}</span>
                </button>
              ))}
              <div className="flex items-center gap-1">
                <input value={customW} onChange={(e) => setCustomW(e.target.value)}
                  className="w-14 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15
                    rounded-lg px-2 py-1 text-xs text-center text-gray-900 dark:text-white
                    focus:outline-none focus:border-indigo-400"
                  placeholder="W" />
                <span className="text-gray-400 dark:text-white/30 text-xs">×</span>
                <input value={customH} onChange={(e) => setCustomH(e.target.value)}
                  className="w-14 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15
                    rounded-lg px-2 py-1 text-xs text-center text-gray-900 dark:text-white
                    focus:outline-none focus:border-indigo-400"
                  placeholder="H" />
                <button
                  onClick={() => exportSvg(parseInt(customW) || 1280, parseInt(customH) || 720)}
                  disabled={exporting}
                  className="rounded-lg border border-gray-200 dark:border-white/15 hover:border-gray-300 dark:hover:border-white/30
                    px-2.5 py-1 text-xs text-gray-700 dark:text-white
                    disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                  {exporting ? "…" : "↓"}
                </button>
              </div>
            </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [sessions, setSessions] = useState<ChartSession[]>([]);
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [addPrompt, setAddPrompt] = useState("");
  const [adding, setAdding] = useState(false);
  const [showAddBar, setShowAddBar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [dark, setDark] = useState(true);
  const [isPlayground, setIsPlayground] = useState(false);
  const [playgroundName, setPlaygroundName] = useState("");
  const [loadingPlayground, setLoadingPlayground] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
  }, [dark]);

  function handleFile(f: File | null) {
    if (!f) return;
    if (!f.name.endsWith(".csv")) { setError("Please upload a .csv file."); return; }
    setFile(f);
    setIsPlayground(false);
    setPlaygroundName("");
    setError(null);
    setSessions([]);
  }

  function updateSession(id: string, updates: Partial<ChartSession>) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, ...updates } : s));
  }

  function deleteSession(id: string) {
    setSessions(prev => prev.filter(s => s.id !== id));
  }

  async function regenerateSession(id: string, prompt: string) {
    if (!file) return;
    updateSession(id, { status: "pending", html: null, mapping: null, error: null, history: [] });
    const body = new FormData();
    body.append("file", file);
    body.append("prompt", prompt);
    try {
      const res = await fetch(`${API}/chart`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      updateSession(id, { status: "done", html: data.html, mapping: data.mapping, history: [{ role: "user", content: prompt }] });
    } catch (e: unknown) {
      updateSession(id, { status: "error", error: e instanceof Error ? e.message : "Regeneration failed", history: [] });
    }
  }

  async function generateWith(f: File, p: string) {
    setGenerating(true);
    setError(null);
    setSessions([]);

    const body = new FormData();
    body.append("file", f);
    body.append("prompt", p);

    try {
      const res = await fetch(`${API}/dashboard`, { method: "POST", body });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Unknown error");
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Normalize CRLF → LF so splits work with plain strings
        buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop()!;

        for (const block of blocks) {
          const lines = block.split("\n");
          let eventType = "message";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!dataStr || dataStr === "{}") continue;

          try {
            const data = JSON.parse(dataStr);
            if (eventType === "start") {
              setSessions(
                (data.sub_prompts as string[]).map((sp, i) => ({
                  id: `session-${i}`,
                  subPrompt: sp,
                  status: "pending",
                  html: null,
                  mapping: null,
                  history: [],
                  error: null,
                }))
              );
            } else if (eventType === "chart") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${data.index}`
                    ? { ...s, status: "done", html: data.html, mapping: data.mapping, history: [{ role: "user", content: data.sub_prompt }] }
                    : s
                )
              );
            } else if (eventType === "error") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${data.index}`
                    ? { ...s, status: "error", error: data.detail }
                    : s
                )
              );
            }
          } catch { /* malformed SSE data — skip */ }
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setGenerating(false);
    }
  }

  async function generate() {
    const p = prompt.trim();
    if (!file || !p) return;
    setPrompt("");
    await generateWith(file, p);
  }

  async function loadPlayground(datasetId: string, datasetPrompt: string, name: string) {
    setLoadingPlayground(datasetId);
    try {
      const res = await fetch(`${API}/playground/csv/${datasetId}`);
      if (!res.ok) throw new Error("Failed to fetch sample dataset");
      const blob = await res.blob();
      const csvFile = new File([blob], `${datasetId}.csv`, { type: "text/csv" });
      setFile(csvFile);
      setIsPlayground(true);
      setPlaygroundName(name);
      await generateWith(csvFile, datasetPrompt);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load playground dataset");
    } finally {
      setLoadingPlayground(null);
    }
  }

  async function addChart() {
    const p = addPrompt.trim();
    if (!file || !p) return;
    setAdding(true);
    setAddPrompt("");
    setShowAddBar(false);

    const body = new FormData();
    body.append("file", file);
    body.append("prompt", p);

    // Offset new session IDs so they don't collide with existing ones
    const offset = sessions.length;

    try {
      const res = await fetch(`${API}/dashboard`, { method: "POST", body });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Unknown error");
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop()!;

        for (const block of blocks) {
          const lines = block.split("\n");
          let eventType = "message";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!dataStr || dataStr === "{}") continue;

          try {
            const data = JSON.parse(dataStr);
            if (eventType === "start") {
              setSessions(prev => [
                ...prev,
                ...(data.sub_prompts as string[]).map((sp: string, i: number) => ({
                  id: `session-${offset + i}`,
                  subPrompt: sp,
                  status: "pending" as const,
                  html: null,
                  mapping: null,
                  history: [],
                  error: null,
                })),
              ]);
            } else if (eventType === "chart") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${offset + data.index}`
                    ? { ...s, status: "done", html: data.html, mapping: data.mapping, history: [{ role: "user" as const, content: data.sub_prompt }] }
                    : s
                )
              );
            } else if (eventType === "error") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${offset + data.index}`
                    ? { ...s, status: "error", error: data.detail }
                    : s
                )
              );
            }
          } catch { /* skip */ }
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add chart");
    } finally {
      setAdding(false);
    }
  }

  const hasSessions = sessions.length > 0;

  return (
    <main
      className="min-h-screen text-gray-900 dark:text-white flex flex-col overflow-x-hidden"
      style={dark ? {
        backgroundColor: "#0f1117",
        backgroundImage: [
          "radial-gradient(ellipse 280% 80% at 50% -10%, rgba(99,102,241,0.14) 0%, transparent 100%)",
          `url("data:image/svg+xml,${DARK_WEAVE_SVG}")`,
        ].join(", "),
      } : {
        backgroundColor: "#f5f5f3",
        backgroundImage: [
          // fade out toward center so texture feels ambient, not loud
          "radial-gradient(ellipse 70% 60% at 50% 40%, rgba(245,245,243,0.85) 0%, transparent 100%)",
          `url("data:image/svg+xml,${LIGHT_WEAVE_SVG}")`,
        ].join(", "),
      }}
    >
      <div className="fixed top-0 left-0 right-0 z-10">
        <header
          className="w-full flex items-center gap-4 px-8 h-[76px] border-b"
          style={dark ? {
            background: "linear-gradient(to bottom, #161822, #0f1117)",
            borderColor: "rgba(255,255,255,0.07)",
            boxShadow: "0 1px 0 rgba(255,255,255,0.03), 0 4px 24px rgba(0,0,0,0.4)",
          } : {
            background: "rgba(255,255,255,0.82)",
            backdropFilter: "blur(12px)",
            borderColor: "#e4e6ea",
            boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
          }}
        >
          <div className="flex items-center gap-2.5">
            <div className={`w-7 h-7 rounded-lg ${dark ? "bg-indigo-500" : "bg-red-600"} flex items-center justify-center shrink-0`}>
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.5 7.5 9l3 3 4.5-6L21 13.5" />
              </svg>
            </div>
            <span className="text-sm font-semibold tracking-tight text-gray-900 dark:text-white">Weave</span>
            <span className="text-[10px] font-medium text-red-600 dark:text-indigo-300 border border-red-200 dark:border-indigo-500/40 rounded px-1.5 py-0.5 leading-none">
              beta
            </span>
          </div>

          <div className="flex-1" />

          {/* Start over — only shown in dashboard state */}
          {hasSessions && (
            <button
              onClick={() => { setSessions([]); setPrompt(""); setError(null); setFile(null); setIsPlayground(false); setPlaygroundName(""); }}
              className="text-xs text-gray-400 dark:text-white/40 hover:text-gray-700 dark:hover:text-white/70 transition-colors mr-3"
            >
              ← New
            </button>
          )}

          <button
            onClick={() => setDark(!dark)}
            className="flex items-center gap-1 rounded-full border border-gray-200 dark:border-white/10
              bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 transition-colors px-1 py-1"
            title="Toggle theme"
          >
            <span className={`flex items-center justify-center w-7 h-7 rounded-full transition-all
              ${!dark ? "bg-white text-slate-900 shadow-sm" : "text-white/30"}`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
              </svg>
            </span>
            <span className={`flex items-center justify-center w-7 h-7 rounded-full transition-all
              ${dark ? "bg-white/15 text-white shadow" : "text-gray-400"}`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
              </svg>
            </span>
          </button>
        </header>
      </div>

      {/* ── Landing state ── */}
      {!hasSessions && !generating && (
        <div className="flex flex-col flex-1 items-center justify-center px-6 py-12 pt-[calc(76px+3rem)] text-center">
          <div className="relative flex flex-col gap-5 w-full max-w-4xl">
            {/* Decorative needle + thread */}
            <svg
              className="absolute pointer-events-none"
              viewBox="0 0 1400 520"
              preserveAspectRatio="xMidYMid meet"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              style={{ width: "105%", height: "340px", left: "-2.5%", top: "-145px", pointerEvents: "none" }}
            >
              <path
                d="M 56 338 C 168 234,280 104,420 130 C 504 143,546 273,448 312 C 378 338,336 260,420 208 C 532 130,630 143,700 169 C 812 208,868 91,980 117 C 1064 137,1120 195,1176 156 C 1204 90,1235 82,1264 78"
                stroke={dark ? "rgba(167,139,250,0.55)" : "rgba(220,38,38,0.55)"}
                strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none"
              />
              <path d="M 1272 68 L 1031 357 L 1035 361 L 1276 74 Z"
                fill={dark ? "rgba(220,220,230,0.75)" : "rgba(30,41,59,0.7)"} />
              <path d="M 1031 357 L 1033 367 L 1035 361 Z"
                fill={dark ? "rgba(220,220,230,0.75)" : "rgba(30,41,59,0.7)"} />
              <ellipse cx="1264" cy="78" rx="3.5" ry="9" transform="rotate(-46 1264 78)"
                fill={dark ? "#0f1117" : "#f0f2f5"} />
            </svg>

            <div className="relative flex flex-col gap-5" style={{ zIndex: 1 }}>
              {/* Heading */}
              <div className="mb-1" style={{ fontFamily: "var(--font-sora), sans-serif" }}>
                <div className="flex flex-col items-center gap-0 md:hidden">
                  <p className="text-xl sm:text-3xl font-extrabold uppercase tracking-tight leading-tight" style={dark ? { background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { color: "#0f172a" }}>
                    If you can describe it,
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-xl sm:text-3xl font-extrabold uppercase tracking-tight leading-tight" style={dark ? { background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { color: "#0f172a" }}>we can</span>
                    <span className="text-4xl sm:text-6xl font-extrabold uppercase tracking-tight leading-none" style={{ lineHeight: 1, ...(dark ? { color: "#ffffff", textShadow: "0 0 50px rgba(167,139,250,0.6), 0 0 100px rgba(129,140,248,0.3)" } : { color: "#dc2626", textShadow: "0 0 40px rgba(220,38,38,0.2), 0 0 80px rgba(220,38,38,0.1)" }) }}>WEAVE</span>
                    <span className="text-xl sm:text-3xl font-extrabold uppercase tracking-tight leading-tight" style={dark ? { background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { color: "#0f172a" }}>it.</span>
                  </div>
                </div>
                <div className="hidden md:flex" style={{ alignItems: "last baseline", gap: "1rem", justifyContent: "center" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                    <p className="text-2xl lg:text-4xl font-extrabold uppercase tracking-tight" style={dark ? { lineHeight: 1, background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { lineHeight: 1, color: "#0f172a" }}>
                      If you can describe it,
                    </p>
                    <p className="text-2xl lg:text-4xl font-extrabold uppercase tracking-tight text-right" style={dark ? { lineHeight: 1, background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { lineHeight: 1, color: "#0f172a" }}>
                      we can
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                    <span className="text-5xl lg:text-8xl font-extrabold uppercase tracking-tight" style={{ lineHeight: 1, ...(dark ? { color: "#ffffff", textShadow: "0 0 50px rgba(167,139,250,0.6), 0 0 100px rgba(129,140,248,0.3)" } : { color: "#dc2626", textShadow: "0 0 40px rgba(220,38,38,0.2), 0 0 80px rgba(220,38,38,0.1)" }) }}>WEAVE</span>
                    <span className="text-2xl lg:text-4xl font-extrabold uppercase tracking-tight" style={dark ? { lineHeight: 1, background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { lineHeight: 1, color: "#0f172a" }}>it.</span>
                  </div>
                </div>
                <p className="mt-3 text-sm text-gray-400 dark:text-white/35">
                  Drop a CSV. Describe what you want. Get interactive charts - no code, no config.
                </p>
              </div>

              {/* CSV dropzone */}
              <div
                style={{ background: dragging ? (dark ? "rgba(99,102,241,0.15)" : "rgba(220,38,38,0.1)") : dark ? "rgba(20,22,35,0.8)" : "rgba(255,255,255,0.9)" }}
                className={`flex items-center gap-3 rounded-xl border-2 border-dashed px-5 py-3.5 cursor-pointer transition-colors
                  ${dragging ? "border-indigo-400" : "border-white/25 hover:border-indigo-400/60"}`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
              >
                <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
                  onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />
                <svg className="w-4 h-4 text-gray-400 dark:text-white/30 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
                {file
                  ? <span className={`text-sm font-medium ${dark ? "text-indigo-400" : "text-red-600"}`}>{file.name}</span>
                  : <span className="text-sm text-gray-400 dark:text-white/40">Drop a CSV here · or click to browse</span>}
                {file && (
                  <button onClick={(e) => { e.stopPropagation(); setFile(null); setError(null); }}
                    className="ml-auto text-gray-400 dark:text-white/30 hover:text-white/60 transition-colors text-xl leading-none">×</button>
                )}
              </div>

              {/* Prompt bar */}
              <div className="flex gap-2">
                <input
                  style={{ background: dark ? "rgba(20,22,35,0.8)" : "rgba(255,255,255,0.9)" }}
                  className="flex-1 border border-white/25 rounded-xl
                    px-5 py-4 text-base placeholder-gray-400 dark:placeholder-white/40 text-gray-900 dark:text-white
                    focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-400 focus:border-red-500"
                  placeholder="e.g. show revenue over time for each company"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); generate(); } }}
                  disabled={generating}
                  autoFocus
                />
                <button
                  onClick={generate}
                  disabled={!file || !prompt.trim() || generating}
                  className={`flex items-center justify-center rounded-xl ${dark ? "bg-indigo-500 hover:bg-indigo-400" : "bg-red-600 hover:bg-red-500"}
                    disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-5 shrink-0`}
                >
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                  </svg>
                </button>
              </div>

              {error && (
                <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
                  {error}
                </div>
              )}

              {/* Playground dataset picker */}
              <div className="flex flex-col gap-3 mt-2 text-left">
                <p className="text-xs font-medium uppercase tracking-widest text-gray-400 dark:text-white/30 text-center">
                  Or explore a sample dataset
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {PLAYGROUND_DATASETS.map((ds) => (
                    <button
                      key={ds.id}
                      onClick={() => loadPlayground(ds.id, ds.prompt, ds.name)}
                      disabled={loadingPlayground !== null}
                      className={`flex flex-col gap-1.5 rounded-xl border px-4 py-3 text-left transition-colors cursor-pointer
                        ${dark
                          ? "border-white/15 hover:border-indigo-400/60"
                          : "border-gray-200 bg-white hover:border-red-300 hover:bg-red-50"
                        } disabled:opacity-40 disabled:cursor-not-allowed`}
                      style={dark ? { background: "rgba(13, 15, 26, 0.75)" } : undefined}
                    >
                      {loadingPlayground === ds.id ? (
                        <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-white/40">
                          <svg className="w-3.5 h-3.5 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                          </svg>
                          Loading…
                        </div>
                      ) : (
                        <>
                          <span className="text-xl leading-none">{ds.emoji}</span>
                          <span className={`text-sm font-semibold ${dark ? "text-white" : "text-gray-900"}`}>{ds.name}</span>
                          <span className="text-xs text-gray-400 dark:text-white/40 leading-snug">{ds.description}</span>
                        </>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Decomposing / waiting for first SSE event ── */}
      {generating && sessions.length === 0 && (
        <div className="flex flex-col flex-1 items-center justify-center gap-3 pt-[76px] text-sm text-gray-400 dark:text-white/30">
          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Analysing your data…
        </div>
      )}

      {/* ── Dashboard state ── */}
      {hasSessions && (
        <div className="flex flex-col flex-1 gap-6 px-6 py-6 pt-[calc(76px+1.5rem)] w-full max-w-7xl mx-auto">

          {/* CSV strip */}
          <div
            className={`flex items-center gap-3 rounded-xl border-2 border-dashed px-4 py-2.5 cursor-pointer transition-colors
              ${dragging
                ? "border-indigo-400 bg-indigo-50 dark:bg-indigo-400/5"
                : "border-gray-300 dark:border-white/10 hover:border-gray-400 dark:hover:border-indigo-500/40"}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
          >
            <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />
            <svg className="w-4 h-4 text-gray-400 dark:text-white/30 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            {file
              ? <span className={`text-sm font-medium ${dark ? "text-indigo-400" : "text-red-600"}`}>
                  {isPlayground ? `Playground - ${playgroundName}` : file.name}
                </span>
              : <span className="text-sm text-gray-400 dark:text-white/40">Drop a CSV here or click to browse</span>}
            {file && !isPlayground && (
              <button
                onClick={(e) => { e.stopPropagation(); setFile(null); setSessions([]); setError(null); }}
                className="ml-auto text-gray-400 dark:text-white/30 hover:text-gray-600 dark:hover:text-white/60 transition-colors text-lg leading-none"
              >×</button>
            )}
          </div>

          {error && (
            <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
              {error}
            </div>
          )}

          {/* Chart grid */}
          <div className="flex flex-col gap-6">
            {sessions.map((session) => (
              <ChartCard
                key={session.id}
                session={session}
                file={file!}
                dark={dark}
                onUpdate={updateSession}
                onDelete={deleteSession}
                onRegenerate={regenerateSession}
              />
            ))}
          </div>

          {/* Add chart */}
          {showAddBar ? (
            <div className="flex gap-2">
              <input
                className="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15 rounded-xl
                  px-4 py-3 text-sm placeholder-gray-400 dark:placeholder-white/30 text-gray-900 dark:text-white
                  focus:outline-none focus:border-red-500 dark:focus:border-indigo-400"
                placeholder="Describe the next chart…"
                value={addPrompt}
                onChange={(e) => setAddPrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); addChart(); } if (e.key === "Escape") { setShowAddBar(false); setAddPrompt(""); } }}
                disabled={adding}
                autoFocus
              />
              <button
                onClick={addChart}
                disabled={!addPrompt.trim() || adding}
                className={`flex items-center justify-center rounded-xl ${dark ? "bg-indigo-500 hover:bg-indigo-400" : "bg-red-600 hover:bg-red-500"}
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-4 shrink-0`}
              >
                {adding
                  ? <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                  : <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                    </svg>
                }
              </button>
              <button
                onClick={() => { setShowAddBar(false); setAddPrompt(""); }}
                className="rounded-xl border border-gray-200 dark:border-white/15 px-4 text-sm text-gray-500 dark:text-white/40 hover:text-gray-700 dark:hover:text-white/70 transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowAddBar(true)}
              disabled={adding}
              className={`flex items-center gap-2 self-start rounded-xl border px-5 py-2.5 text-sm font-medium transition-colors
                ${dark
                  ? "border-white/15 text-white/60 hover:border-indigo-400/60 hover:text-white hover:bg-indigo-400/5"
                  : "border-gray-300 text-gray-500 hover:border-red-400/60 hover:text-gray-800 hover:bg-red-50"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              Add chart
            </button>
          )}

        </div>
      )}
    </main>
  );
}
