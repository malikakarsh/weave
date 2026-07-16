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
  const [file, setFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [html, setHtml] = useState<string | null>(null);
  const [mapping, setMapping] = useState<Record<string, unknown> | null>(null);
  const [insights, setInsights] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [customW, setCustomW] = useState("1280");
  const [customH, setCustomH] = useState("720");
  const [dark, setDark] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

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
  }

  async function generate() {
    if (!file || !prompt.trim()) return;
    setLoading(true);
    setError(null);
    setHtml(null);
    setInsights(null);
    setMapping(null);

    const body = new FormData();
    body.append("file", file);
    body.append("prompt", prompt.trim());

    try {
      const res = await fetch(`${API}/chart`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      setHtml(data.html);
      setMapping(data.mapping);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function analyze() {
    if (!file || !mapping) return;
    setAnalyzing(true);
    setInsights(null);

    const body = new FormData();
    body.append("file", file);
    body.append("mapping", JSON.stringify(mapping));
    body.append("prompt", prompt.trim());

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
    <main className="min-h-screen bg-white dark:bg-[#13151f] text-gray-900 dark:text-white flex flex-col">

      <div className="sticky top-0 z-10">
      <header className="w-full bg-white dark:bg-[#0d0f17] border-b border-gray-200 dark:border-white/10 shadow-sm dark:shadow-[0_4px_24px_rgba(0,0,0,0.4)] flex items-center gap-4 px-8 h-[76px]">
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

      <div className="flex flex-col flex-1 gap-6 px-6 py-6 w-full max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto">

        {/* Input panel */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 cursor-pointer transition-colors
              ${dragging
                ? "border-indigo-400 bg-indigo-50 dark:bg-indigo-400/5"
                : "border-gray-300 dark:border-white/20 hover:border-gray-400 dark:hover:border-white/40"}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
          >
            <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />
            <svg className="w-8 h-8 text-gray-300 dark:text-white/30" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            {file
              ? <span className="text-sm font-medium text-indigo-500">{file.name}</span>
              : <><span className="text-sm text-gray-400 dark:text-white/50">Drop a CSV here</span><span className="text-xs text-gray-400 dark:text-white/30">or click to browse</span></>}
          </div>

          <div className="flex flex-col gap-3">
            <textarea
              className="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/15 rounded-xl px-4 py-3 text-sm
                placeholder-gray-400 dark:placeholder-white/30 text-gray-900 dark:text-white
                focus:outline-none focus:border-indigo-400 resize-none min-h-[100px]"
              placeholder={"Describe your chart…\ne.g. show revenue over time for each company"}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate(); }}
            />
            <button onClick={generate} disabled={!file || !prompt.trim() || loading}
              className="flex items-center justify-center gap-2 rounded-xl bg-indigo-500 hover:bg-indigo-400
                disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-5 py-3 text-sm font-medium text-white">
              {loading
                ? <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>Generating…</>
                : "Generate chart"}
            </button>
            <p className="text-xs text-gray-400 dark:text-white/25 text-right">⌘ Enter to generate</p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-500 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Chart */}
        {html && (
          <div className="w-full rounded-xl border border-gray-100 dark:border-white/10 bg-gray-50 dark:bg-transparent py-8">
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
                boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              }}
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        )}

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
    </main>
  );
}
