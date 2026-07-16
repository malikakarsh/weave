"use client";

import { useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFile(f: File | null) {
    if (!f) return;
    if (!f.name.endsWith(".csv")) {
      setError("Please upload a .csv file.");
      return;
    }
    setFile(f);
    setError(null);
    setHtml(null);
  }

  async function generate() {
    if (!file || !prompt.trim()) return;
    setLoading(true);
    setError(null);
    setHtml(null);

    const body = new FormData();
    body.append("file", file);
    body.append("prompt", prompt.trim());

    try {
      const res = await fetch(`${API}/chart`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Unknown error");
      setHtml(data.html);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#13151f] text-white flex flex-col">
      {/* Header */}
      <header className="px-8 py-5 border-b border-white/10 flex items-center gap-3">
        <span className="text-xl font-semibold tracking-tight">Weave</span>
        <span className="text-white/40 text-sm">CSV → interactive chart</span>
      </header>

      <div className="flex flex-col flex-1 gap-6 p-8 max-w-5xl mx-auto w-full">

        {/* Input panel */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* CSV drop zone */}
          <div
            className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 cursor-pointer transition-colors
              ${dragging ? "border-indigo-400 bg-indigo-400/5" : "border-white/20 hover:border-white/40"}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
            />
            <svg className="w-8 h-8 text-white/30" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            {file ? (
              <span className="text-sm font-medium text-indigo-300">{file.name}</span>
            ) : (
              <>
                <span className="text-sm text-white/50">Drop a CSV here</span>
                <span className="text-xs text-white/30">or click to browse</span>
              </>
            )}
          </div>

          {/* Prompt + button */}
          <div className="flex flex-col gap-3">
            <textarea
              className="flex-1 bg-white/5 border border-white/15 rounded-xl px-4 py-3 text-sm placeholder-white/30
                focus:outline-none focus:border-indigo-400 resize-none min-h-[100px]"
              placeholder={"Describe your chart…\ne.g. show revenue over time for each company"}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate(); }}
            />
            <button
              onClick={generate}
              disabled={!file || !prompt.trim() || loading}
              className="flex items-center justify-center gap-2 rounded-xl bg-indigo-500 hover:bg-indigo-400
                disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-5 py-3 text-sm font-medium"
            >
              {loading ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Generating…
                </>
              ) : "Generate chart"}
            </button>
            <p className="text-xs text-white/25 text-right">⌘ Enter to generate</p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Chart */}
        {html && (
          <div className="rounded-xl overflow-hidden border border-white/10">
            <iframe
              srcDoc={html}
              className="w-full"
              style={{ height: 520, border: "none" }}
              sandbox="allow-scripts"
            />
          </div>
        )}
      </div>
    </main>
  );
}
