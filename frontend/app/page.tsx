"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState, type RefObject } from "react";
import { get, set, del } from "idb-keyval";
import { useAuth } from "./useAuth";

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
    viz: "line",
    prompt: "show stock price trend over time for each company as a multi-series line chart, and show average stock price per company as a bar chart",
  },
  {
    id: "revenue",
    name: "Company Revenue",
    description: "Monthly revenue across multiple companies over several years",
    viz: "bar",
    prompt: "show total revenue per company as a bar chart sorted descending, and revenue trend over time for each company as a line chart",
  },
  {
    id: "world_cities",
    name: "World Cities",
    description: "55 major cities with population and continent",
    viz: "map",
    prompt: "plot world cities on a symbol map sized by population and colored by continent, and show total population by continent as a bar chart",
  },
  {
    id: "diamonds",
    name: "Diamonds",
    description: "Prices and attributes: cut, color, clarity, carat",
    viz: "groupedBar",
    prompt: "show average diamond price by cut as a bar chart, and show average diamond price with diamond color on the x-axis and cut as the group column as a bar chart (not stacked)",
  },
  {
    id: "restaurants",
    name: "NYC Restaurants",
    description: "Inspection records with grades, violations, and borough",
    viz: "pie",
    prompt: "show inspection count by borough as a bar chart, and a breakdown of inspection grades as a pie chart",
  },
  {
    id: "iris",
    name: "Iris Flowers",
    description: "Classic dataset: sepal/petal measurements for 3 species",
    viz: "scatter",
    prompt: "show sepal length vs sepal width as a scatter plot colored by species, and average petal length by species as a bar chart",
  },
] as const;

type VizKind = (typeof PLAYGROUND_DATASETS)[number]["viz"];

// Tiny stylized chart drawn per sample card; animates in on card hover (see
// `.card-glyph` rules in globals.css). Stroke uses currentColor so the parent
// sets the accent (indigo in dark, red in light).
function CardGlyph({ kind }: { kind: VizKind }) {
  const common = { className: "card-glyph", width: 30, height: 20, viewBox: "0 0 30 20", fill: "none" as const };
  if (kind === "line") {
    return (
      <svg {...common}>
        <polyline className="draw" points="1,15 7,9 12,12 18,4 24,7 29,2"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (kind === "bar") {
    const bars = [[2, 12], [9, 7], [16, 10], [23, 3]];
    return (
      <svg {...common}>
        {bars.map(([x, y], i) => (
          <rect key={i} className="bar" x={x} y={y} width="5" height={19 - y} rx="1" fill="currentColor" />
        ))}
      </svg>
    );
  }
  if (kind === "groupedBar") {
    // three groups of two bars (paired), alternating opacity within a group
    const groups = [[3, 9], [12, 5], [21, 11]];
    return (
      <svg {...common}>
        {groups.flatMap(([x, y], g) => [
          <rect key={`${g}a`} className="bar" x={x} y={y} width="3" height={19 - y} rx="0.8" fill="currentColor" />,
          <rect key={`${g}b`} className="bar" x={x + 3.6} y={y - 3} width="3" height={19 - (y - 3)} rx="0.8" fill="currentColor" fillOpacity="0.55" />,
        ])}
      </svg>
    );
  }
  if (kind === "scatter") {
    // tight diagonal cluster (a correlation)
    const pts = [[5, 15], [9, 13], [12, 11], [14, 8], [18, 7], [22, 4]];
    return (
      <svg {...common}>
        {pts.map(([cx, cy], i) => (
          <circle key={i} className="dot" cx={cx} cy={cy} r="1.9" fill="currentColor" />
        ))}
      </svg>
    );
  }
  if (kind === "map") {
    // dots spread across the width like pins on a map, varied sizes
    const pins = [[3, 12, 1.7], [8, 6, 2.1], [13, 14, 1.6], [17, 9, 2.4], [22, 5, 1.8], [27, 12, 2.0]];
    return (
      <svg {...common}>
        {pins.map(([cx, cy, r], i) => (
          <circle key={i} className="dot" cx={cx} cy={cy} r={r} fill="currentColor" fillOpacity={0.55 + (i % 3) * 0.18} />
        ))}
      </svg>
    );
  }
  // pie
  return (
    <svg {...common} viewBox="0 0 20 20">
      <path className="slice" d="M10 10 L10 1 A9 9 0 0 1 18 13 Z" fill="currentColor" />
      <path className="slice" d="M10 10 L18 13 A9 9 0 0 1 3 15 Z" fill="currentColor" fillOpacity="0.6" />
      <path className="slice" d="M10 10 L3 15 A9 9 0 0 1 10 1 Z" fill="currentColor" fillOpacity="0.32" />
    </svg>
  );
}

// Faint engineering grid — a single fine hairline per tile, low opacity, so it
// reads as ambient depth rather than a pronounced dotted pattern.
const LIGHT_WEAVE_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26">' +
  '<path d="M26 0H0V26" fill="none" stroke="black" stroke-opacity="0.07" stroke-width="0.5"/>' +
  '</svg>'
);

const DARK_WEAVE_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26">' +
  '<path d="M26 0H0V26" fill="none" stroke="white" stroke-opacity="0.03" stroke-width="0.5"/>' +
  '</svg>'
);

type HistoryMessage = { role: "user" | "assistant"; content: string };

interface ChartSession {
  id: string;
  subPrompt: string;
  status: "pending" | "done" | "error";
  stage: string | null;
  html: string | null;
  mapping: Record<string, unknown> | null;
  history: HistoryMessage[];
  error: string | null;
}

// ── Speech-to-text mic button ─────────────────────────────────────────────────

type MicHandle = { stop: () => void; getTranscript: () => string; toggle: () => void };

const MicButton = forwardRef<MicHandle, {
  onTranscript: (t: string) => void;
  dark: boolean;
  small?: boolean;
  onEnter?: (transcript: string) => void;
  disabled?: boolean;
}>(function MicButton({ onTranscript, dark, small = false, onEnter, disabled = false }, ref) {
  const [supported, setSupported] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<{ stop: () => void } | null>(null);
  const transcriptRef = useRef("");

  useEffect(() => {
    setSupported("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
  }, []);

  function stop() {
    recRef.current?.stop();
    recRef.current = null;
    setRecording(false);
    // Clear so a subsequent Enter (without re-recording) doesn't resubmit the
    // previous transcript. Callers read getTranscript() before calling stop().
    transcriptRef.current = "";
  }

  useImperativeHandle(ref, () => ({
    stop,
    toggle,
    getTranscript: () => transcriptRef.current,
  }));

  if (!supported) return null;

  function start() {
    setError(null);
    transcriptRef.current = "";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (e: { results: { [key: number]: { [key: number]: { transcript: string } }; length: number } }) => {
      const t = Array.from({ length: e.results.length }, (_, i) => e.results[i][0].transcript).join(" ").trim();
      transcriptRef.current = t;
      onTranscript(t);
    };
    rec.onerror = (e: { error: string }) => {
      if (e.error === "not-allowed" || e.error === "permission-denied") {
        setError("Mic blocked");
      } else if (e.error !== "aborted" && e.error !== "no-speech") {
        setError(e.error);
      }
      setRecording(false);
    };
    rec.onend = () => setRecording(false);
    recRef.current = rec;
    rec.start();
    setRecording(true);
  }

  function toggle() {
    if (disabled) return;
    if (recording) { stop(); } else { start(); }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled}
      onKeyDown={(e) => {
        // While the mic button holds focus, Enter should stop recording AND
        // submit — otherwise it only fires the button's default click (stop).
        if (e.key === "Enter") {
          e.preventDefault();
          const t = transcriptRef.current;
          stop();
          onEnter?.(t);
        }
      }}
      title={disabled ? "Upload a CSV first" : error ?? (recording ? "Stop recording (⌥/Alt+Shift+V)" : "Speak your prompt (⌥/Alt+Shift+V)")}
      className={`flex items-center justify-center shrink-0 rounded-xl transition-colors
        ${disabled ? "opacity-80 cursor-not-allowed" : "cursor-pointer"}
        ${small ? "w-10" : "w-12"}
        ${error
          ? "bg-yellow-400/20 border border-yellow-400/50"
          : recording
            ? "bg-red-500 hover:bg-red-400"
            : dark
              ? "bg-white/5 hover:bg-white/10 border border-white/15"
              : "bg-gray-100 hover:bg-gray-200 border border-gray-200"
        }`}
    >
      {error
        ? <svg className={`${small ? "w-3.5 h-3.5" : "w-4 h-4"} text-yellow-500`} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        : recording
          ? <span className="w-2.5 h-2.5 rounded-full bg-white animate-pulse" />
          : <svg className={`${small ? "w-3.5 h-3.5" : "w-4 h-4"} ${dark ? "text-white/50" : "text-gray-400"}`} fill="currentColor" viewBox="0 0 24 24">
              <path d="M8.25 4.5a3.75 3.75 0 1 1 7.5 0v8.25a3.75 3.75 0 1 1-7.5 0V4.5Z"/>
              <path d="M6 10.5a.75.75 0 0 1 .75.75v1.5a5.25 5.25 0 0 0 10.5 0v-1.5a.75.75 0 0 1 1.5 0v1.5a6.751 6.751 0 0 1-6 6.709V21h3a.75.75 0 0 1 0 1.5h-7.5a.75.75 0 0 1 0-1.5h3v-2.291A6.751 6.751 0 0 1 5.25 12.75v-1.5A.75.75 0 0 1 6 10.5Z"/>
            </svg>
      }
    </button>
  );
});

function stageLabel(stage: string | null): string {
  switch (stage) {
    case "loading":     return "Loading CSV…";
    case "mapping":     return "Mapping columns…";
    case "transforming": return "Transforming data…";
    case "rendering":   return "Rendering chart…";
    default:            return "Generating…";
  }
}

// Voice-recording shortcut: ⌥/Alt+Shift+V. On macOS the Option key may be
// consumed for character composition (altKey can be false, key becomes a glyph
// like "◊"/"Dead"), so accept either signal alongside the physical V key.
function isVoiceShortcut(e: Pick<KeyboardEvent, "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "code" | "key">): boolean {
  if (e.metaKey || e.ctrlKey || !e.shiftKey || e.code !== "KeyV") return false;
  return e.altKey || e.key === "◊" || e.key === "Dead" || e.key === "√";
}

// ── Per-chart card ────────────────────────────────────────────────────────────

interface ChartCardProps {
  session: ChartSession;
  file: File;
  dark: boolean;
  onUpdate: (id: string, updates: Partial<ChartSession>) => void;
  onDelete: (id: string) => void;
  onRegenerate: (id: string, prompt: string) => void;
  registerRefineMic?: (id: string, ref: RefObject<MicHandle | null> | null) => void;
  onActive?: (id: string) => void;
}

function ChartCard({ session, file, dark, onUpdate, onDelete, onRegenerate, registerRefineMic, onActive }: ChartCardProps) {
  const [refinePrompt, setRefinePrompt] = useState("");
  const [refining, setRefining] = useState(false);
  const [refineStage, setRefineStage] = useState<string | null>(null);
  const [refineError, setRefineError] = useState<string | null>(null);
  type Clar = { field: string; term: string; column: string; options: string[]; reason: string; color: string | null };
  const [clarify, setClarify] = useState<{ clarifications: Clar[]; mapping: Record<string, unknown> } | null>(null);
  const [clarifyBusy, setClarifyBusy] = useState(false);
  const [insights, setInsights] = useState<string[] | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [customW, setCustomW] = useState("1280");
  const [customH, setCustomH] = useState("720");
  const [iframeHeight, setIframeHeight] = useState("400px");
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeWrapRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const refineMicRef = useRef<MicHandle | null>(null);

  // Register this card's refine mic so the global ⌥⇧V shortcut can toggle it.
  useEffect(() => {
    registerRefineMic?.(session.id, refineMicRef);
    return () => registerRefineMic?.(session.id, null);
  }, [session.id, registerRefineMic]);

  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage({ type: "weave-theme", dark }, "*");
  }, [dark]);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      // Only handle messages from this card's iframe
      if (e.source !== iframeRef.current?.contentWindow) return;
      if (e.data?.type === "weave-height") {
        const h = Math.max(e.data.height, 300) + "px";
        setIframeHeight(h);
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

  async function refine(forcedValue?: string) {
    const instruction = (forcedValue ?? refinePrompt).trim();
    if (!instruction || !session.mapping) return;

    if (/^regenerate$/i.test(instruction)) {
      setRefinePrompt("");
      onRegenerate(session.id, session.subPrompt);
      return;
    }

    setRefining(true);
    setRefineStage(null);
    setRefineError(null);
    setClarify(null);
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
      const res = await fetch(`${API}/refine/stream`, { method: "POST", body, credentials: "include" });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Unknown error");
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
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!dataStr || dataStr === "{}") continue;
          try {
            const data = JSON.parse(dataStr);
            if (data.stage === "done") {
              onUpdate(session.id, {
                html: data.html,
                mapping: data.mapping,
                history: [...nextHistory, { role: "assistant", content: JSON.stringify(data.mapping) }],
              });
              setInsights(null);
              setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 100);
            } else if (data.stage === "clarify") {
              // Ambiguous category reference — ask the user which value they meant.
              setClarify({ clarifications: data.clarifications, mapping: data.mapping });
            } else if (data.stage === "error") {
              // Keep the existing chart; surface the reason (e.g. dimensions mismatch).
              setRefineError(data.detail ?? "Couldn't apply that change.");
              onUpdate(session.id, { history: session.history });
            } else {
              setRefineStage(data.stage);
            }
          } catch { /* malformed SSE — skip */ }
        }
      }
    } catch (e: unknown) {
      setRefineError(e instanceof Error ? e.message : "Couldn't apply that change.");
      onUpdate(session.id, { history: session.history });
    } finally {
      setRefining(false);
      setRefineStage(null);
    }
  }

  // Apply the user's pick for one clarification; when all are answered, re-render
  // the resolved mapping with no further LLM call.
  // chosen === null → "none of these": skip this reference (don't apply it).
  async function resolveClarification(clar: Clar, chosen: string | null) {
    if (!clarify) return;
    const mapping = { ...clarify.mapping } as Record<string, unknown>;
    if (chosen !== null) {
      if (clar.field === "category_colors") {
        mapping.category_colors = { ...(mapping.category_colors as Record<string, string> || {}), [chosen]: clar.color };
      } else if (clar.field === "group_filter") {
        mapping.group_filter = [...((mapping.group_filter as string[]) || []), chosen];
      } else if (clar.field === "filters") {
        const filters = ((mapping.filters as { column: string; values: string[] }[]) || []).map(f => ({ ...f }));
        const existing = filters.find(f => f.column === clar.column);
        if (existing) existing.values = [...(existing.values || []), chosen];
        else filters.push({ column: clar.column, values: [chosen] });
        mapping.filters = filters;
      }
    }

    const remaining = clarify.clarifications.filter(c => c !== clar);
    if (remaining.length > 0) {
      setClarify({ clarifications: remaining, mapping });
      return;
    }

    setClarifyBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("mapping", JSON.stringify(mapping));
      const res = await fetch(`${API}/render`, { method: "POST", body, credentials: "include" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Render failed");
      onUpdate(session.id, {
        html: data.html,
        mapping: data.mapping,
        history: [...session.history, { role: "assistant", content: JSON.stringify(data.mapping) }],
      });
      setClarify(null);
    } catch (e: unknown) {
      setRefineError(e instanceof Error ? e.message : "Couldn't apply that change.");
      setClarify(null);
    } finally {
      setClarifyBusy(false);
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
      const res = await fetch(`${API}/insights`, { method: "POST", body, credentials: "include" });
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
      data-card-id={session.id}
      className="flex flex-col gap-2 rounded-xl p-3"
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
        <div className="flex flex-col items-center justify-center h-64 gap-3">
          <div className="flex items-center gap-3 text-sm text-gray-400 dark:text-white/30">
            <svg className="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            {stageLabel(session.stage)}
          </div>
          {session.stage && (
            <div className="flex gap-1.5">
              {(["loading", "mapping", "transforming", "rendering"] as const).map((s) => (
                <div
                  key={s}
                  className="h-1 w-10 rounded-full transition-colors duration-300"
                  style={{
                    background: ["loading", "mapping", "transforming", "rendering"].indexOf(s) <=
                      ["loading", "mapping", "transforming", "rendering"].indexOf(session.stage ?? "")
                      ? (dark ? "#6366f1" : "#dc2626")
                      : (dark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)"),
                  }}
                />
              ))}
            </div>
          )}
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
        <div ref={iframeWrapRef} style={{
          height: iframeHeight,
          borderRadius: "12px",
          overflow: "hidden",
          flexShrink: 0,
          boxShadow: dark
            ? "0 1px 6px rgba(0,0,0,0.22)"
            : "0 1px 6px rgba(0,0,0,0.06)",
        }}>
          <iframe
            ref={iframeRef}
            srcDoc={session.html}
            onLoad={() => iframeRef.current?.contentWindow?.postMessage({ type: "weave-theme", dark }, "*")}
            style={{ width: "100%", height: iframeHeight, border: "none", display: "block" }}
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      )}

      {/* Conversation history */}
      {session.status === "done" && session.history.filter(m => m.role === "user").length > 0 && (
        <div
          className="flex flex-col gap-2 max-h-32 overflow-y-auto pr-1"
          style={{ scrollbarWidth: "thin", scrollbarColor: dark ? "#374151 transparent" : "#cbd5e1 transparent" }}
        >
          {session.history.filter(m => m.role === "user").map((m, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className={`mt-0.5 w-4 h-4 rounded-full ${dark ? "bg-indigo-500" : "bg-red-600"} flex items-center justify-center shrink-0 text-[9px] text-white font-bold`}>
                U
              </span>
              <p className="text-xs text-gray-700 dark:text-white/80 leading-relaxed pt-0.5">{m.content}</p>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      )}

      {/* Per-chart refine bar */}
      {session.status === "done" && (
        <div className="flex gap-2">
          <input
            data-refine-input="1"
            className="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15 rounded-xl
              px-3 py-1.5 text-xs placeholder-gray-400 dark:placeholder-white/30 text-gray-900 dark:text-white
              focus:outline-none focus:border-red-500 dark:focus:border-indigo-400"
            placeholder="Refine this chart… e.g. sort descending, change color to red, show top 10 only"
            value={refinePrompt}
            onFocus={() => onActive?.(session.id)}
            onChange={(e) => setRefinePrompt(e.target.value)}
            onKeyDown={(e) => {
              if (isVoiceShortcut(e)) { e.preventDefault(); refineMicRef.current?.toggle(); return; }
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const t = refineMicRef.current?.getTranscript(); refineMicRef.current?.stop(); refine(t || (e.target as HTMLInputElement).value); }
            }}
            disabled={refining}
          />
          <MicButton ref={refineMicRef} onTranscript={(t) => setRefinePrompt(t)} onEnter={(t) => refine(t || refinePrompt)} dark={dark} small />
          <button
            onClick={() => refine()}
            disabled={!refinePrompt.trim() || refining}
            className={`flex items-center justify-center rounded-xl ${dark ? "bg-indigo-500 hover:bg-indigo-400" : "bg-red-600 hover:bg-red-500"}
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-4 shrink-0`}
          >
            {refining
              ? <div className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  {refineStage === "mapping" && <span className="text-xs text-white/80 hidden sm:block">Mapping…</span>}
                </div>
              : <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                </svg>
            }
          </button>
        </div>
      )}

      {/* Clarification (ambiguous / unknown category reference) */}
      {session.status === "done" && clarify && clarify.clarifications.length > 0 && (() => {
        const c = clarify.clarifications[0];
        const prompt = c.reason === "none"
          ? <>No category matches <span className="font-semibold">&ldquo;{c.term}&rdquo;</span> in <span className="font-mono">{c.column}</span>. Did you mean:</>
          : <><span className="font-semibold">&ldquo;{c.term}&rdquo;</span> is ambiguous in <span className="font-mono">{c.column}</span> — which did you mean?</>;
        return (
          <div className="rounded-lg bg-indigo-500/10 border border-indigo-500/30 px-3 py-2.5 text-xs text-gray-700 dark:text-white/80 flex flex-col gap-2">
            <span>{prompt}</span>
            <div className="flex flex-wrap gap-2">
              {c.options.map(opt => (
                <button
                  key={opt}
                  disabled={clarifyBusy}
                  onClick={() => resolveClarification(c, opt)}
                  className="flex items-center gap-1.5 rounded-full border border-gray-300 dark:border-white/20 bg-white dark:bg-white/5
                    px-2.5 py-1 hover:border-indigo-400 dark:hover:border-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
                >
                  {c.field === "category_colors" && c.color && (
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c.color }} />
                  )}
                  {opt}
                </button>
              ))}
              <button
                disabled={clarifyBusy}
                onClick={() => resolveClarification(c, null)}
                className="rounded-full border border-transparent px-2.5 py-1 text-gray-500 dark:text-white/40
                  hover:text-gray-700 dark:hover:text-white/70 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                None of these
              </button>
            </div>
            <span className="text-[11px] text-gray-400 dark:text-white/30">Or refine again with a more specific name.</span>
          </div>
        );
      })()}

      {/* Refine error (e.g. dimensions mismatch) */}
      {session.status === "done" && refineError && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-500 dark:text-red-300 flex items-start gap-2">
          <svg className="w-4 h-4 shrink-0 mt-px" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span>{refineError}</span>
        </div>
      )}

      {/* Analyze + Export */}
      {session.status === "done" && session.mapping && (
        <div className="flex flex-col gap-2">
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

          <div className="flex flex-wrap items-center gap-2">
            {!insights && (
              <button onClick={analyze} disabled={analyzing}
                className="flex items-center gap-2 rounded-lg border border-gray-200 dark:border-white/15
                  hover:border-indigo-400/60 hover:bg-indigo-50 dark:hover:bg-indigo-400/5
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-3 py-1.5 text-xs
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
  const { user, login, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hydrated = useRef(false);
  const promptMicRef = useRef<MicHandle | null>(null);
  const addMicRef = useRef<MicHandle | null>(null);
  // Registry of each chart card's refine mic, keyed by session id.
  const refineMicRegistry = useRef<Map<string, RefObject<MicHandle | null>>>(new Map());
  // The chart the user is currently amending (last-focused refine field), so the
  // ⌥⇧V shortcut sticks to it instead of jumping to the most recent chart.
  const activeCardRef = useRef<string | null>(null);
  const setActiveCard = useCallback((id: string) => { activeCardRef.current = id; }, []);
  const registerRefineMic = useCallback((id: string, ref: RefObject<MicHandle | null> | null) => {
    if (ref) refineMicRegistry.current.set(id, ref);
    else refineMicRegistry.current.delete(id);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
  }, [dark]);

  // ── Restore persisted state on mount ────────────────────────────────────────
  useEffect(() => {
    async function restore() {
      try {
        const [storedDark, storedFile, storedSessions, storedPlayground] = await Promise.all([
          get<boolean>("weave:dark"),
          get<{ name: string; type: string; bytes: ArrayBuffer }>("weave:file"),
          get<ChartSession[]>("weave:sessions"),
          get<{ isPlayground: boolean; playgroundName: string }>("weave:playground"),
        ]);

        if (storedDark !== undefined) setDark(storedDark);

        if (storedFile) {
          const f = new File([storedFile.bytes], storedFile.name, { type: storedFile.type });
          setFile(f);
        }

        if (storedSessions?.length) {
          // Any session that was mid-generation when the page closed becomes an error
          setSessions(storedSessions.map(s =>
            s.status === "pending"
              ? { ...s, status: "error", stage: null, error: "Generation interrupted — please regenerate" }
              : s
          ));
        }

        if (storedPlayground) {
          setIsPlayground(storedPlayground.isPlayground);
          setPlaygroundName(storedPlayground.playgroundName);
        }
      } catch { /* IndexedDB unavailable (private browsing, etc.) — silent */ }
      hydrated.current = true;
    }
    restore();
  }, []);

  // ── Persist on change (skip until hydration is complete) ────────────────────
  useEffect(() => {
    if (!hydrated.current) return;
    set("weave:dark", dark).catch(() => {});
  }, [dark]);

  useEffect(() => {
    if (!hydrated.current) return;
    if (!file) { del("weave:file").catch(() => {}); return; }
    file.arrayBuffer().then(bytes =>
      set("weave:file", { name: file.name, type: file.type, bytes }).catch(() => {})
    );
  }, [file]);

  useEffect(() => {
    if (!hydrated.current) return;
    if (!sessions.length) { del("weave:sessions").catch(() => {}); return; }
    set("weave:sessions", sessions).catch(() => {});
  }, [sessions]);

  useEffect(() => {
    if (!hydrated.current) return;
    set("weave:playground", { isPlayground, playgroundName }).catch(() => {});
  }, [isPlayground, playgroundName]);

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
    updateSession(id, { status: "pending", stage: null, html: null, mapping: null, error: null, history: [] });
    const body = new FormData();
    body.append("file", file);
    body.append("prompt", prompt);
    try {
      const res = await fetch(`${API}/chart/stream`, { method: "POST", body, credentials: "include" });
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
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!dataStr || dataStr === "{}") continue;
          try {
            const data = JSON.parse(dataStr);
            if (data.stage === "done") {
              updateSession(id, { status: "done", stage: null, html: data.html, mapping: data.mapping, history: [{ role: "user", content: prompt }] });
            } else if (data.stage === "error") {
              updateSession(id, { status: "error", stage: null, error: data.detail ?? "Regeneration failed", history: [] });
            } else {
              updateSession(id, { stage: data.stage });
            }
          } catch { /* malformed SSE — skip */ }
        }
      }
    } catch (e: unknown) {
      updateSession(id, { status: "error", stage: null, error: e instanceof Error ? e.message : "Regeneration failed", history: [] });
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
      const res = await fetch(`${API}/dashboard`, { method: "POST", body, credentials: "include" });
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
                  status: "pending" as const,
                  stage: null,
                  html: null,
                  mapping: null,
                  history: [],
                  error: null,
                }))
              );
            } else if (eventType === "progress") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${data.index}`
                    ? { ...s, stage: data.stage }
                    : s
                )
              );
            } else if (eventType === "chart") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${data.index}`
                    ? { ...s, status: "done", stage: null, html: data.html, mapping: data.mapping, history: [{ role: "user", content: data.sub_prompt }] }
                    : s
                )
              );
            } else if (eventType === "error") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${data.index}`
                    ? { ...s, status: "error", stage: null, error: data.detail }
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

  async function generate(forcedValue?: string) {
    const p = (forcedValue ?? prompt).trim();
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

  async function addChart(forcedValue?: string) {
    const p = (forcedValue ?? addPrompt).trim();
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
      const res = await fetch(`${API}/dashboard`, { method: "POST", body, credentials: "include" });
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
                  stage: null,
                  html: null,
                  mapping: null,
                  history: [],
                  error: null,
                })),
              ]);
            } else if (eventType === "progress") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${offset + data.index}`
                    ? { ...s, stage: data.stage }
                    : s
                )
              );
            } else if (eventType === "chart") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${offset + data.index}`
                    ? { ...s, status: "done", stage: null, html: data.html, mapping: data.mapping, history: [{ role: "user" as const, content: data.sub_prompt }] }
                    : s
                )
              );
            } else if (eventType === "error") {
              setSessions(prev =>
                prev.map(s =>
                  s.id === `session-${offset + data.index}`
                    ? { ...s, status: "error", stage: null, error: data.detail }
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

  // Global shortcut (⌥/Alt+Shift+V) to toggle voice recording, never auto-opening
  // the add-chart bar:
  //   • landing screen        → the prompt mic
  //   • focused in add bar     → the add-chart mic
  //   • otherwise (dashboard)  → the current chart's refine mic
  //     (the focused card, else the most recent one)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!isVoiceShortcut(e)) return;
      const active = document.activeElement as HTMLElement | null;
      // Compose inputs handle the combo themselves (and preventDefault) so they
      // toggle their own mic — don't double-handle here.
      if (active?.dataset?.refineInput || active?.dataset?.addInput || active?.dataset?.promptInput) return;
      e.preventDefault(); // suppress the special char this combo would type
      if (!hasSessions) { promptMicRef.current?.toggle(); return; }
      // Dashboard, focus outside any field → the chart being amended:
      // the focused card, else the last one you touched, else the most recent.
      const focusedCard = active?.closest("[data-card-id]") as HTMLElement | null;
      const active_ = activeCardRef.current;
      const targetId = focusedCard?.getAttribute("data-card-id")
        ?? (active_ && refineMicRegistry.current.has(active_) ? active_ : undefined)
        ?? sessions[sessions.length - 1]?.id;
      if (!targetId) return;
      // Focus the card's refine field so Enter can submit after speaking.
      const card = focusedCard ?? document.querySelector(`[data-card-id="${CSS.escape(targetId)}"]`);
      (card?.querySelector("[data-refine-input]") as HTMLElement | null)?.focus();
      refineMicRegistry.current.get(targetId)?.current?.toggle();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hasSessions, sessions]);

  return (
    <main
      className="min-h-screen text-gray-900 dark:text-white flex flex-col overflow-x-hidden"
      style={dark ? {
        backgroundColor: "#0f1117",
        backgroundImage: [
          // layered radial mesh for depth — warm indigo top, cool violet lower-left
          "radial-gradient(ellipse 280% 80% at 50% -10%, rgba(99,102,241,0.16) 0%, transparent 60%)",
          "radial-gradient(ellipse 90% 70% at 12% 108%, rgba(139,92,246,0.10) 0%, transparent 55%)",
          `url("data:image/svg+xml,${DARK_WEAVE_SVG}")`,
        ].join(", "),
      } : {
        backgroundColor: "#f0f1f5",
        backgroundImage: [
          // same radial geometry as dark mode, in the red brand hue (softened)
          "radial-gradient(ellipse 280% 80% at 50% -10%, rgba(244,63,94,0.04) 0%, transparent 60%)",
          "radial-gradient(ellipse 90% 70% at 12% 108%, rgba(220,38,38,0.03) 0%, transparent 55%)",
          `url("data:image/svg+xml,${LIGHT_WEAVE_SVG}")`,
        ].join(", "),
      }}
    >
      <div className="fixed top-0 left-0 right-0 z-10">
        <header
          className="w-full flex items-center gap-4 px-6 h-[56px] border-b"
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
            <div className={`w-6 h-6 rounded-md ${dark ? "bg-indigo-500" : "bg-red-600"} flex items-center justify-center shrink-0`}>
              <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
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
              className="text-xs text-gray-400 dark:text-white/40 hover:text-gray-700 dark:hover:text-white/70 transition-colors mr-3 cursor-pointer"
            >
              ← New
            </button>
          )}

          <button
            onClick={() => setDark(!dark)}
            className="flex items-center gap-1 rounded-full border border-gray-200 dark:border-white/10
              bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 transition-colors px-1 py-1 cursor-pointer"
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

          {/* Auth control */}
          {user ? (
            <div className="relative ml-3">
              <button
                onClick={() => setUserMenuOpen((o) => !o)}
                className="flex items-center gap-2 rounded-full border border-gray-200 dark:border-white/10 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 transition-colors pl-1 pr-2.5 py-1 cursor-pointer"
                title={user.email ?? undefined}
              >
                {user.picture
                  ? <img src={user.picture} alt="" width={24} height={24} className="w-6 h-6 rounded-full" referrerPolicy="no-referrer" />
                  : <span className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-semibold text-white ${dark ? "bg-indigo-500" : "bg-red-600"}`}>{(user.name ?? user.email ?? "?").charAt(0).toUpperCase()}</span>}
                <span className="text-xs font-medium text-gray-700 dark:text-white/70 max-w-[120px] truncate hidden sm:block">{user.name ?? user.email}</span>
              </button>
              {userMenuOpen && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setUserMenuOpen(false)} />
                  <div className="absolute right-0 mt-2 w-56 z-30 rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#161822] shadow-lg overflow-hidden">
                    <div className="px-3 py-2.5 border-b border-gray-100 dark:border-white/10">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{user.name}</p>
                      <p className="text-xs text-gray-400 dark:text-white/40 truncate">{user.email}</p>
                    </div>
                    <button
                      onClick={() => { setUserMenuOpen(false); logout(); }}
                      className="w-full text-left px-3 py-2 text-sm text-gray-700 dark:text-white/70 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors cursor-pointer"
                    >
                      Log out
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <button
              onClick={login}
              className="ml-3 flex items-center gap-2 rounded-full border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors px-3 py-1.5 cursor-pointer"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
                <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
              </svg>
              <span className="text-xs font-medium text-gray-700 dark:text-white/80">Sign in</span>
            </button>
          )}
        </header>
      </div>

      {/* ── Landing state ── */}
      {!hasSessions && !generating && (
        <div className="flex flex-col items-center justify-center px-6 py-6 text-center" style={{ minHeight: "calc(100vh - 56px)", marginTop: "56px" }}>
          <div className="relative flex flex-col gap-3 w-full max-w-2xl">
            {/* Decorative needle + thread */}
            <svg
              className="absolute pointer-events-none"
              viewBox="0 0 1400 520"
              preserveAspectRatio="xMidYMid meet"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              style={{ width: "92%", height: "296px", left: "4%", top: "-140px", pointerEvents: "none" }}
            >
              <defs>
                <filter id="thread-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3.5" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              {/* soft glow underlay */}
              <path
                d="M 56 338 C 168 234,280 104,420 130 C 504 143,546 273,448 312 C 378 338,336 260,420 208 C 532 130,630 143,700 169 C 812 208,868 91,980 117 C 1064 137,1120 195,1176 156 C 1204 90,1235 82,1264 78"
                stroke={dark ? "rgba(167,139,250,0.35)" : "rgba(220,38,38,0.3)"}
                strokeWidth="3" strokeLinecap="round" fill="none" filter="url(#thread-glow)"
              />
              {/* crisp thin thread */}
              <path
                d="M 56 338 C 168 234,280 104,420 130 C 504 143,546 273,448 312 C 378 338,336 260,420 208 C 532 130,630 143,700 169 C 812 208,868 91,980 117 C 1064 137,1120 195,1176 156 C 1204 90,1235 82,1264 78"
                stroke={dark ? "rgba(196,181,253,0.7)" : "rgba(220,38,38,0.6)"}
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"
              />
              <path d="M 1272 68 L 1031 357 L 1035 361 L 1276 74 Z"
                fill={dark ? "rgba(220,220,230,0.75)" : "rgba(30,41,59,0.7)"} />
              <path d="M 1031 357 L 1028 365 L 1035 361 Z"
                fill={dark ? "rgba(220,220,230,0.75)" : "rgba(30,41,59,0.7)"} />
              <ellipse cx="1264" cy="78" rx="3.5" ry="9" transform="rotate(-46 1264 78)"
                fill={dark ? "#0f1117" : "#f0f2f5"} />
            </svg>

            <div className="relative flex flex-col gap-5" style={{ zIndex: 1 }}>
              {/* Heading */}
              <div className="mb-1" style={{ fontFamily: "var(--font-sora), sans-serif" }}>
                <div className="flex flex-col items-center gap-0 md:hidden">
                  <p className="text-lg sm:text-2xl font-semibold uppercase tracking-tight leading-tight" style={dark ? { backgroundImage: "linear-gradient(135deg, #818cf8 0%, #c4b5fd 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { backgroundImage: "linear-gradient(135deg, #0f172a 0%, #dc2626 135%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                    If you can describe it,
                  </p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-lg sm:text-2xl font-semibold uppercase tracking-tight leading-tight" style={dark ? { backgroundImage: "linear-gradient(135deg, #818cf8 0%, #c4b5fd 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { backgroundImage: "linear-gradient(135deg, #0f172a 0%, #dc2626 135%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>we can</span>
                    <span className="text-3xl sm:text-5xl font-bold uppercase tracking-tight leading-none" style={{ lineHeight: 1, ...(dark ? { color: "#ffffff", textShadow: "0 0 24px rgba(196,181,253,0.75), 0 0 60px rgba(129,140,248,0.5), 0 0 110px rgba(129,140,248,0.25)" } : { color: "#dc2626", textShadow: "0 0 22px rgba(220,38,38,0.35), 0 0 55px rgba(244,63,94,0.28), 0 0 110px rgba(244,63,94,0.14)" }) }}>WEAVE</span>
                    <span className="text-lg sm:text-2xl font-semibold uppercase tracking-tight leading-tight" style={dark ? { backgroundImage: "linear-gradient(135deg, #818cf8 0%, #c4b5fd 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { backgroundImage: "linear-gradient(135deg, #0f172a 0%, #dc2626 135%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>it.</span>
                  </div>
                </div>
                <div className="hidden md:flex" style={{ alignItems: "flex-end", gap: "1rem", justifyContent: "center" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                    <p className="text-xl lg:text-2xl font-semibold uppercase tracking-tight" style={dark ? { lineHeight: 1, backgroundImage: "linear-gradient(135deg, #818cf8 0%, #c4b5fd 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { lineHeight: 1, backgroundImage: "linear-gradient(135deg, #0f172a 0%, #dc2626 135%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                      If you can describe it,
                    </p>
                    <p className="text-xl lg:text-2xl font-semibold uppercase tracking-tight text-right" style={dark ? { lineHeight: 1, backgroundImage: "linear-gradient(135deg, #818cf8 0%, #c4b5fd 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { lineHeight: 1, backgroundImage: "linear-gradient(135deg, #0f172a 0%, #dc2626 135%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                      we can
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                    <span className="text-4xl lg:text-5xl font-bold uppercase tracking-tight" style={{ lineHeight: 1, ...(dark ? { color: "#ffffff", textShadow: "0 0 24px rgba(196,181,253,0.75), 0 0 60px rgba(129,140,248,0.5), 0 0 110px rgba(129,140,248,0.25)" } : { color: "#dc2626", textShadow: "0 0 22px rgba(220,38,38,0.35), 0 0 55px rgba(244,63,94,0.28), 0 0 110px rgba(244,63,94,0.14)" }) }}>WEAVE</span>
                    <span className="text-xl lg:text-2xl font-semibold uppercase tracking-tight" style={dark ? { lineHeight: 1, backgroundImage: "linear-gradient(135deg, #818cf8 0%, #c4b5fd 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" } : { lineHeight: 1, backgroundImage: "linear-gradient(135deg, #0f172a 0%, #dc2626 135%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>it.</span>
                  </div>
                </div>
                <p className="mt-3 text-sm font-light tracking-wide text-gray-500 dark:text-white/40">
                  Drop a CSV. Describe what you want. Get interactive charts — no code, no config.
                </p>
              </div>

              {/* Unified command palette — CSV attach + prompt in one frosted box */}
              <div
                className="flex flex-col rounded-2xl p-2 transition-shadow focus-within:ring-2 focus-within:ring-indigo-400/40"
                style={dark ? {
                  background: "rgba(20,22,35,0.55)",
                  border: "1px solid rgba(255,255,255,0.10)",
                  backdropFilter: "blur(14px)",
                  WebkitBackdropFilter: "blur(14px)",
                  boxShadow: "0 8px 40px rgba(0,0,0,0.35)",
                } : {
                  background: "rgba(255,255,255,0.85)",
                  border: "1px solid rgba(15,23,42,0.05)",
                  backdropFilter: "blur(14px)",
                  WebkitBackdropFilter: "blur(14px)",
                  boxShadow: "0 12px 40px rgba(15,23,42,0.10), 0 2px 6px rgba(15,23,42,0.04), inset 0 1px 0 rgba(255,255,255,0.7)",
                }}
              >
                {/* Attach-CSV row */}
                <div
                  style={dragging ? { background: dark ? "rgba(99,102,241,0.14)" : "rgba(220,38,38,0.08)" } : undefined}
                  className="flex items-center gap-2.5 rounded-xl px-2.5 py-1.5 cursor-pointer transition-colors hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
                >
                  <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
                    onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />
                  <svg className={`w-4 h-4 shrink-0 ${file ? (dark ? "text-indigo-400" : "text-red-500") : "text-gray-400 dark:text-white/30"}`} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                  </svg>
                  {file
                    ? <span className={`text-sm font-medium ${dark ? "text-indigo-300" : "text-red-600"}`}>{file.name}</span>
                    : <span className="text-sm text-gray-400 dark:text-white/40">Drop a CSV here · or click to browse</span>}
                  {file && (
                    <button onClick={(e) => { e.stopPropagation(); setFile(null); setError(null); }}
                      className="ml-auto text-gray-400 dark:text-white/30 hover:text-gray-600 dark:hover:text-white/60 transition-colors text-lg leading-none">×</button>
                  )}
                </div>

                {/* Divider */}
                <div className="h-px mx-1 my-1" style={{ background: dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)" }} />

                {/* Prompt row */}
                <div className="flex items-stretch gap-2 pl-1.5">
                  <input
                    data-prompt-input="1"
                    className="flex-1 bg-transparent border-0 px-1.5 py-1.5 text-sm placeholder-gray-400 dark:placeholder-white/40 text-gray-900 dark:text-white
                      focus:outline-none disabled:cursor-not-allowed"
                    placeholder={file ? "e.g. show revenue over time for each company" : "Upload a CSV to get started…"}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => { if (isVoiceShortcut(e)) { e.preventDefault(); promptMicRef.current?.toggle(); return; } if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const t = promptMicRef.current?.getTranscript(); promptMicRef.current?.stop(); generate(t || (e.target as HTMLInputElement).value); } }}
                    disabled={!file || generating}
                    autoFocus
                  />
                  <MicButton ref={promptMicRef} onTranscript={(t) => setPrompt(t)} onEnter={(t) => generate(t || prompt)} dark={dark} disabled={!file || generating} />
                  <button
                    onClick={() => generate()}
                    disabled={!file || !prompt.trim() || generating}
                    style={{ boxShadow: "inset 0 1px 0 rgba(255,255,255,0.18)" }}
                    className={`group/send flex items-center justify-center rounded-xl h-9 w-10 shrink-0 transition-all
                      ${dark ? "bg-indigo-500 hover:bg-indigo-400 hover:shadow-[0_0_20px_rgba(129,140,248,0.55)]" : "bg-red-600 hover:bg-red-500 hover:shadow-[0_0_18px_rgba(220,38,38,0.4)]"}
                      disabled:opacity-70 disabled:shadow-none disabled:cursor-not-allowed`}
                  >
                    <svg className="w-4 h-4 text-white transition-transform group-hover/send:translate-x-px" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                    </svg>
                  </button>
                </div>
              </div>

              {error && (
                <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
                  {error}
                </div>
              )}

              {/* Playground dataset picker */}
              <div className="flex flex-col gap-2 mt-1 text-left">
                <p className="text-xs font-medium uppercase tracking-widest text-gray-400 dark:text-white/30 text-center">
                  Or explore a sample dataset
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {PLAYGROUND_DATASETS.map((ds) => (
                    <button
                      key={ds.id}
                      onClick={() => loadPlayground(ds.id, ds.prompt, ds.name)}
                      disabled={loadingPlayground !== null}
                      className="group flex flex-col gap-0.5 rounded-xl px-2.5 py-2 text-left transition-colors cursor-pointer
                        disabled:opacity-40 disabled:cursor-not-allowed"
                      style={dark ? {
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.10)",
                        backdropFilter: "blur(8px)",
                        WebkitBackdropFilter: "blur(8px)",
                      } : {
                        background: "rgba(255,255,255,0.8)",
                        border: "1px solid rgba(15,23,42,0.05)",
                        backdropFilter: "blur(8px)",
                        WebkitBackdropFilter: "blur(8px)",
                        boxShadow: "0 4px 16px rgba(15,23,42,0.05), inset 0 1px 0 rgba(255,255,255,0.6)",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = dark ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.97)"; e.currentTarget.style.borderColor = dark ? "rgba(129,140,248,0.45)" : "rgba(220,38,38,0.35)"; if (!dark) e.currentTarget.style.boxShadow = "0 10px 28px rgba(220,38,38,0.10), inset 0 1px 0 rgba(255,255,255,0.7)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = dark ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.8)"; e.currentTarget.style.borderColor = dark ? "rgba(255,255,255,0.10)" : "rgba(15,23,42,0.05)"; if (!dark) e.currentTarget.style.boxShadow = "0 4px 16px rgba(15,23,42,0.05), inset 0 1px 0 rgba(255,255,255,0.6)"; }}
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
                          <span className={`mb-0.5 ${dark ? "text-indigo-300" : "text-red-500"}`}>
                            <CardGlyph kind={ds.viz} />
                          </span>
                          <span className={`text-xs font-semibold ${dark ? "text-white" : "text-gray-900"}`}>{ds.name}</span>
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
        <div className="flex flex-col flex-1 items-center justify-center gap-3 pt-[56px] text-sm text-gray-400 dark:text-white/30">
          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Analysing your data…
        </div>
      )}

      {/* ── Dashboard state ── */}
      {hasSessions && (
        <div className="flex flex-col flex-1 gap-3 px-5 py-4 pt-[calc(56px+1.5rem)] w-full max-w-4xl mx-auto">

          {/* CSV strip */}
          <div
            className={`flex items-center gap-3 rounded-xl border-2 border-dashed px-3 py-2 cursor-pointer transition-colors
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
          <div className="flex flex-col gap-3">
            {sessions.map((session) => (
              <ChartCard
                key={session.id}
                session={session}
                file={file!}
                dark={dark}
                onUpdate={updateSession}
                onDelete={deleteSession}
                onRegenerate={regenerateSession}
                registerRefineMic={registerRefineMic}
                onActive={setActiveCard}
              />
            ))}
          </div>

          {/* Add chart */}
          {showAddBar ? (
            <div className="flex gap-2">
              <input
                data-add-input="1"
                className="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15 rounded-xl
                  px-3 py-2 text-sm placeholder-gray-400 dark:placeholder-white/30 text-gray-900 dark:text-white
                  focus:outline-none focus:border-red-500 dark:focus:border-indigo-400"
                placeholder="Describe the next chart…"
                value={addPrompt}
                onChange={(e) => setAddPrompt(e.target.value)}
                onKeyDown={(e) => { if (isVoiceShortcut(e)) { e.preventDefault(); addMicRef.current?.toggle(); return; } if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const t = addMicRef.current?.getTranscript(); addMicRef.current?.stop(); addChart(t || (e.target as HTMLInputElement).value); } if (e.key === "Escape") { setShowAddBar(false); setAddPrompt(""); } }}
                disabled={adding}
                autoFocus
              />
              <MicButton ref={addMicRef} onTranscript={(t) => setAddPrompt(t)} onEnter={(t) => addChart(t || addPrompt)} dark={dark} small />
              <button
                onClick={() => addChart()}
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
