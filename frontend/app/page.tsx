"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EXPORT_PRESETS = [
  { label: "HD", w: 1280, h: 720 },
  { label: "Full HD", w: 1920, h: 1080 },
  { label: "Social", w: 1200, h: 630 },
  { label: "Square", w: 1080, h: 1080 },
];

export default function Home() {
  type HistoryMessage = { role: "user" | "assistant"; content: string };

  const [file, setFile] = useState<File | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [mapping, setMapping] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [refinePrompt, setRefinePrompt] = useState("");
  const [insights, setInsights] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refining, setRefining] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [customW, setCustomW] = useState("1280");
  const [customH, setCustomH] = useState("720");
  const [dark, setDark] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
    iframeRef.current?.contentWindow?.postMessage({ type: "weave-theme", dark }, "*");
  }, [dark]);

  function handleFile(f: File | null) {
    if (!f) return;
    if (!f.name.endsWith(".csv")) { setError("Please upload a .csv file."); return; }
    setFile(f);
    setError(null);
    setHtml(null);
    setInsights(null);
    setMapping(null);
    setHistory([]);
  }

  async function generate() {
    const p = refinePrompt.trim();
    if (!file || !p) return;
    setLoading(true);
    setError(null);
    setHtml(null);
    setInsights(null);
    setMapping(null);
    setHistory([]);
    setRefinePrompt("");

    const body = new FormData();
    body.append("file", file);
    body.append("prompt", p);

    try {
      const res = await fetch(`${API}/chart`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      setHtml(data.html);
      setMapping(data.mapping);
      setHistory([{ role: "user", content: p }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit() {
    if (!html) generate();
    else refine();
  }

  async function refine() {
    if (!file || !mapping || !refinePrompt.trim()) return;
    const instruction = refinePrompt.trim();
    setRefining(true);
    setError(null);
    setRefinePrompt("");

    const nextHistory: HistoryMessage[] = [...history, { role: "user", content: instruction }];
    setHistory(nextHistory);

    const body = new FormData();
    body.append("file", file);
    body.append("mapping", JSON.stringify(mapping));
    body.append("history", JSON.stringify(history));
    body.append("instruction", instruction);

    try {
      const res = await fetch(`${API}/refine`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      setHtml(data.html);
      setMapping(data.mapping);
      setInsights(null);
      setHistory([...nextHistory, { role: "assistant", content: JSON.stringify(data.mapping) }]);
      setTimeout(() => {
        const el = chatEndRef.current;
        if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 100);
    } catch (e: unknown) {
      setHistory(history);
      setError(e instanceof Error ? e.message : "Refinement failed");
    } finally {
      setRefining(false);
    }
  }

  async function analyze() {
    if (!file || !mapping) return;
    setAnalyzing(true);
    setInsights(null);

    const body = new FormData();
    body.append("file", file);
    body.append("mapping", JSON.stringify(mapping));
    body.append("prompt", history.find(m => m.role === "user")?.content ?? "");

    try {
      const res = await fetch(`${API}/insights`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      setInsights(data.insights);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Insights failed");
    } finally {
      setAnalyzing(false);
    }
  }

  function exportSvg(w: number, h: number) {
    if (!iframeRef.current?.contentWindow) return;
    setExporting(true);
    iframeRef.current.contentWindow.postMessage({ type: "weave-export", width: w, height: h }, "*");
  }

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      if (e.data?.type === "weave-height" && iframeRef.current) {
        const h = Math.max(e.data.height, 300);
        iframeRef.current.style.height = h + "px";
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

  return (
    <main
      className="min-h-screen text-gray-900 dark:text-white flex flex-col overflow-x-hidden"
      style={dark ? {
        backgroundColor: "#0f1117",
        backgroundImage: [
          "repeating-linear-gradient(0deg,   rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 1px, transparent 1px, transparent 6px)",
          "repeating-linear-gradient(90deg,  rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 1px, transparent 1px, transparent 6px)",
          "repeating-linear-gradient(45deg,  rgba(255,255,255,0.012) 0px, rgba(255,255,255,0.012) 1px, transparent 1px, transparent 8px)",
          "radial-gradient(ellipse 280% 80% at 50% -10%, rgba(99,102,241,0.14) 0%, transparent 100%)",
        ].join(", "),
      } : {
        backgroundColor: "#f0f2f5",
        backgroundImage: [
          "repeating-linear-gradient(0deg,  rgba(0,0,0,0.045) 0px, rgba(0,0,0,0.045) 1px, transparent 1px, transparent 6px)",
          "repeating-linear-gradient(90deg, rgba(0,0,0,0.045) 0px, rgba(0,0,0,0.045) 1px, transparent 1px, transparent 6px)",
          "repeating-linear-gradient(45deg, rgba(0,0,0,0.015) 0px, rgba(0,0,0,0.015) 1px, transparent 1px, transparent 8px)",
          "linear-gradient(180deg, #f0f2f5 0%, #f7f8fa 100%)",
        ].join(", "),
      }}
    >

      <div className="sticky top-0 z-10">
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
          <div className="w-7 h-7 rounded-lg bg-indigo-500 flex items-center justify-center shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.5 7.5 9l3 3 4.5-6L21 13.5" />
            </svg>
          </div>
          <span className="text-sm font-semibold tracking-tight text-gray-900 dark:text-white">Weave</span>
          <span className="text-[10px] font-medium text-indigo-500 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/40 rounded px-1.5 py-0.5 leading-none">
            beta
          </span>
        </div>

        <div className="flex-1" />

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

      {/* ── Landing state: vertically centered ── */}
      {!html && (
        <div className="flex flex-col flex-1 items-center justify-center px-6 py-12 text-center">

          <div className="relative flex flex-col gap-5 w-full max-w-4xl">
              {/* Decorative needle + thread — behind all 3 punchline containers */}
              <svg
                className="absolute pointer-events-none"
                viewBox="0 0 1400 520"
                preserveAspectRatio="xMidYMid meet"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                style={{ width: "105%", height: "340px", left: "-2.5%", top: "-145px", pointerEvents: "none" }}
              >
                {/* Thread — sweeps from lower-left, big arc + loop, bumps to needle eye */}
                <path
                  d="M 56 338 C 168 234,280 104,420 130 C 504 143,546 273,448 312 C 378 338,336 260,420 208 C 532 130,630 143,700 169 C 812 208,868 91,980 117 C 1064 137,1120 195,1176 156 C 1204 90,1235 82,1264 78"
                  stroke={dark ? "rgba(167,139,250,0.55)" : "rgba(99,102,241,0.45)"}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                />
                {/* Needle body */}
                <path
                  d="M 1272 68 L 1031 357 L 1035 361 L 1276 74 Z"
                  fill={dark ? "rgba(220,220,230,0.75)" : "rgba(30,41,59,0.7)"}
                />
                {/* Tip */}
                <path
                  d="M 1031 357 L 1033 367 L 1035 361 Z"
                  fill={dark ? "rgba(220,220,230,0.75)" : "rgba(30,41,59,0.7)"}
                />
                {/* Needle eye */}
                <ellipse
                  cx="1264"
                  cy="78"
                  rx="3.5"
                  ry="9"
                  transform="rotate(-46 1264 78)"
                  fill={dark ? "#0f1117" : "#f0f2f5"}
                />
              </svg>

            {/* Content lifted above SVG */}
            <div className="relative flex flex-col gap-5" style={{ zIndex: 1 }}>

            {/* Heading */}
            <div className="mb-1" style={{ fontFamily: "var(--font-sora), sans-serif" }}>

              {/* Mobile layout — stacked, centered */}
              <div className="flex flex-col items-center gap-0 md:hidden">
                <p className="text-xl sm:text-3xl font-extrabold uppercase tracking-tight leading-tight" style={{ background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                  If you can describe it,
                </p>
                <div className="flex items-baseline gap-2">
                  <span className="text-xl sm:text-3xl font-extrabold uppercase tracking-tight leading-tight" style={{ background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>we can</span>
                  <span className="text-4xl sm:text-6xl font-extrabold uppercase tracking-tight leading-none" style={{ ...(dark ? { color: "#ffffff", textShadow: "0 0 50px rgba(167,139,250,0.6), 0 0 100px rgba(129,140,248,0.3)" } : { color: "#1e293b", textShadow: "0 0 40px rgba(30,41,59,0.15), 0 0 80px rgba(30,41,59,0.08)" }) }}>WEAVE</span>
                  <span className="text-xl sm:text-3xl font-extrabold uppercase tracking-tight leading-tight" style={{ background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>it.</span>
                </div>
              </div>

              {/* Desktop layout — side by side, last-baseline aligned */}
              <div className="hidden md:flex" style={{ alignItems: "last baseline", gap: "1rem", justifyContent: "center" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  <p className="text-2xl lg:text-4xl font-extrabold uppercase tracking-tight" style={{ lineHeight: 1, background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                    If you can describe it,
                  </p>
                  <p className="text-2xl lg:text-4xl font-extrabold uppercase tracking-tight text-right" style={{ lineHeight: 1, background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                    we can
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                  <span className="text-5xl lg:text-8xl font-extrabold uppercase tracking-tight" style={{ lineHeight: 1, ...(dark ? { color: "#ffffff", textShadow: "0 0 50px rgba(167,139,250,0.6), 0 0 100px rgba(129,140,248,0.3)" } : { color: "#1e293b", textShadow: "0 0 40px rgba(30,41,59,0.15), 0 0 80px rgba(30,41,59,0.08)" }) }}>WEAVE</span>
                  <span className="text-2xl lg:text-4xl font-extrabold uppercase tracking-tight" style={{ lineHeight: 1, background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>it.</span>
                </div>
              </div>

              <p className="mt-3 text-sm text-gray-400 dark:text-white/35">
                Drop a CSV. Describe what you want. Get a beautiful interactive chart — no code, no config.
              </p>
            </div>

            {/* CSV upload — full width bar */}
            <div
              style={{ background: dragging ? "rgba(99,102,241,0.15)" : dark ? "rgba(20,22,35,0.8)" : "rgba(255,255,255,0.9)" }}
              className={`flex items-center gap-3 rounded-xl border-2 border-dashed px-5 py-3.5 cursor-pointer transition-colors
                ${dragging
                  ? "border-indigo-400"
                  : "border-white/25 hover:border-indigo-400/60"}`}
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
                ? <span className="text-sm font-medium text-indigo-400">{file.name}</span>
                : <span className="text-sm text-gray-400 dark:text-white/40">Drop a CSV here · or click to browse</span>}
              {file && (
                <button onClick={(e) => { e.stopPropagation(); setFile(null); setError(null); }}
                  className="ml-auto text-gray-400 dark:text-white/30 hover:text-white/60 transition-colors text-xl leading-none">×</button>
              )}
            </div>

            {/* Prompt + send */}
            <div className="flex gap-2">
              <input
                style={{ background: dark ? "rgba(20,22,35,0.8)" : "rgba(255,255,255,0.9)" }}
                className="flex-1 border border-white/25 rounded-xl
                  px-5 py-4 text-base placeholder-gray-400 dark:placeholder-white/40 text-gray-900 dark:text-white
                  focus:outline-none focus:border-indigo-400"
                placeholder="e.g. show revenue over time for each company"
                value={refinePrompt}
                onChange={(e) => setRefinePrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); generate(); } }}
                disabled={loading}
                autoFocus
              />
              <button
                onClick={generate}
                disabled={!file || !refinePrompt.trim() || loading}
                className="flex items-center justify-center rounded-xl bg-indigo-500 hover:bg-indigo-400
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-5 shrink-0"
              >
                {loading
                  ? <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                  : <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                    </svg>
                }
              </button>
            </div>

            {error && (
              <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
                {error}
              </div>
            )}
            </div>
          </div>
        </div>
      )}

      {/* ── Chart state: full-width layout ── */}
      {html && (
      <div className="flex flex-col flex-1 gap-6 px-6 py-6 w-full max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto">

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
            ? <span className="text-sm font-medium text-indigo-500">{file.name}</span>
            : <span className="text-sm text-gray-400 dark:text-white/40">Drop a CSV here or click to browse</span>}
          {file && (
            <button
              onClick={(e) => { e.stopPropagation(); setFile(null); setHtml(null); setMapping(null); setHistory([]); setInsights(null); setError(null); }}
              className="ml-auto text-gray-400 dark:text-white/30 hover:text-gray-600 dark:hover:text-white/60 transition-colors text-lg leading-none"
            >×</button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Chart */}
        {html && (
          <div
            className="w-full rounded-xl py-8"
            style={dark ? {
              background: "#0d1018",
              border: "1px solid rgba(255,255,255,0.08)",
            } : {
              background: "#f9fafb",
              border: "1px solid #f3f4f6",
            }}
          >
            <iframe
              ref={iframeRef}
              srcDoc={html}
              onLoad={() => iframeRef.current?.contentWindow?.postMessage({ type: "weave-theme", dark }, "*")}
              style={{
                width: "85%",
                margin: "0 auto",
                height: "480px",
                border: "none",
                display: "block",
                borderRadius: "12px",
                boxShadow: "0 4px 16px rgba(0,0,0,0.18)",
              }}
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        )}

        {/* Conversation history — only shown when a chart exists */}
        {html && history.filter(m => m.role === "user").length > 0 && (
          <div className="flex flex-col gap-2 max-h-48 overflow-y-auto pr-1">
            {history.filter(m => m.role === "user").map((m, i) => (
              <div key={i} className="flex gap-2 items-start">
                <span className="mt-1 w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center shrink-0 text-[10px] text-white font-bold">
                  U
                </span>
                <p className="text-sm text-gray-700 dark:text-white/80 leading-relaxed pt-0.5">{m.content}</p>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        )}

        {/* Prompt bar — chart state */}
        <div className="flex gap-2">
          <input
            className="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15 rounded-xl
              px-4 py-3 text-sm placeholder-gray-400 dark:placeholder-white/30 text-gray-900 dark:text-white
              focus:outline-none focus:border-indigo-400"
            placeholder="Refine the chart… e.g. make it a bar chart, filter to 2023, sort descending"
            value={refinePrompt}
            onChange={(e) => setRefinePrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); refine(); } }}
            disabled={refining}
          />
          <button
            onClick={refine}
            disabled={!refinePrompt.trim() || refining}
            className="flex items-center gap-2 rounded-xl bg-indigo-500 hover:bg-indigo-400
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-4 py-3 text-sm font-medium text-white shrink-0"
          >
            {refining
              ? <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              : <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
                </svg>
            }
          </button>
        </div>

        {/* Bottom toolbar */}
        {html && mapping && (
          <div className="flex flex-wrap items-start gap-4">

            <div className={`flex flex-col gap-3 ${insights ? "w-full" : ""}`}>
              {!insights && (
                <button onClick={analyze} disabled={analyzing}
                  className="flex items-center gap-2 rounded-xl border border-gray-200 dark:border-white/15
                    hover:border-indigo-400/60 hover:bg-indigo-50 dark:hover:bg-indigo-400/5
                    disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-5 py-2.5 text-sm
                    text-gray-700 dark:text-white">
                  {analyzing
                    ? <><svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>Analyzing…</>
                    : <><span>✦</span>Analyze chart</>}
                </button>
              )}
              {insights && (
                <div className="rounded-xl bg-gray-50 dark:bg-white/3 border border-gray-200 dark:border-white/10 p-5 w-full">
                  <p className="text-xs font-medium text-gray-400 dark:text-white/40 uppercase tracking-widest mb-3">Key insights</p>
                  <ul className="flex flex-col gap-2">
                    {insights.map((ins, i) => (
                      <li key={i} className="flex gap-3 text-sm text-gray-700 dark:text-white/80 leading-relaxed">
                        <span className="text-indigo-500 dark:text-indigo-400 mt-0.5 shrink-0">›</span>{ins}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <p className="text-xs text-gray-400 dark:text-white/40 uppercase tracking-widest mb-1">Export SVG</p>
              <div className="flex flex-wrap gap-2">
                {EXPORT_PRESETS.map((p) => (
                  <button key={p.label} onClick={() => exportSvg(p.w, p.h)} disabled={exporting}
                    className="rounded-lg border border-gray-200 dark:border-white/15 hover:border-gray-300 dark:hover:border-white/30
                      px-3 py-1.5 text-xs text-gray-700 dark:text-white
                      disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    {p.label} <span className="text-gray-400 dark:text-white/40">{p.w}×{p.h}</span>
                  </button>
                ))}
                <div className="flex items-center gap-1">
                  <input value={customW} onChange={(e) => setCustomW(e.target.value)}
                    className="w-16 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15
                      rounded-lg px-2 py-1.5 text-xs text-center text-gray-900 dark:text-white
                      focus:outline-none focus:border-indigo-400"
                    placeholder="W" />
                  <span className="text-gray-400 dark:text-white/30 text-xs">×</span>
                  <input value={customH} onChange={(e) => setCustomH(e.target.value)}
                    className="w-16 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15
                      rounded-lg px-2 py-1.5 text-xs text-center text-gray-900 dark:text-white
                      focus:outline-none focus:border-indigo-400"
                    placeholder="H" />
                  <button
                    onClick={() => exportSvg(parseInt(customW) || 1280, parseInt(customH) || 720)}
                    disabled={exporting}
                    className="rounded-lg border border-gray-200 dark:border-white/15 hover:border-gray-300 dark:hover:border-white/30
                      px-3 py-1.5 text-xs text-gray-700 dark:text-white
                      disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    {exporting ? "…" : "↓"}
                  </button>
                </div>
              </div>
            </div>

          </div>
        )}
      </div>
      )}

    </main>
  );
}
