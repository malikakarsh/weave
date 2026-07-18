"use client";

import { createContext, useContext, useState } from "react";
import Link from "next/link";

// ── content data ────────────────────────────────────────────────────────────
const SECTIONS = [
  { id: "overview", title: "Overview" },
  { id: "getting-started", title: "Getting started" },
  { id: "refining", title: "Refining charts" },
  { id: "chart-types", title: "Chart types" },
  { id: "faceting", title: "Faceting" },
  { id: "voice", title: "Voice input" },
  { id: "accounts", title: "Accounts, threads & limits" },
  { id: "export", title: "Export & analyze" },
  { id: "samples", title: "Sample datasets" },
  { id: "tips", title: "Tips" },
];

const REFINE_COMMANDS: [string, string, string][] = [
  ["Change color", "change color to red", "Recolors a single-series chart"],
  ["Color one category", "make Good yellow", "Colors just that category (asks if the name is ambiguous)"],
  ["Named palette", "use a dark palette · tableau colors · pastel", "Swaps the whole color scheme (vibrant / dark / light / muted / tableau10 / category10 / set2 / dark2 / pastel)"],
  ["Mark size", "wider bars · thicker lines · bigger points", "Scales bar width, line thickness, or point/bubble radius (0.2–4×)"],
  ["Sort", "sort descending · sort by value", "Reorders categories"],
  ["Top-N / limit", "top 5 products · show top 10 only", "Keeps the largest N (targets the right dimension in grouped charts)"],
  ["Filter", "only show Food and Travel", "Keeps just the named values"],
  ["Change chart type", "make it a line chart · show as a scatter", "Switches type if the columns support it (rejected with a suggestion otherwise)"],
  ["Background", "white background · dark background", "Sets the chart canvas background"],
  ["Date bucketing", "by month · per year · daily", "Groups a date x-axis into buckets"],
  ["Time range", "from March to September · since 2010", "Filters the x-axis to a window"],
  ["Titles & labels", "title it Revenue by Region · label the y-axis Sales", "Edits chart text"],
];

const CHART_TYPES: [string, string, string][] = [
  ["bar", "Comparing unordered categories", "x (string), y (numeric), optional group"],
  ["line", "Trends over time or numeric x", "x (date/numeric), y (numeric), optional group"],
  ["area", "Volume/magnitude beneath a curve", "x (date/numeric), y (numeric), optional group"],
  ["stacked_area", "Cumulative composition over time", "x (date), y (numeric), group (required)"],
  ["stacked_bar", "Composition across categories", "x (string/bucketed date), y (numeric), group (required)"],
  ["histogram", "Distribution of one numeric column (auto-binned)", "x (numeric), optional group"],
  ["box_plot", "Median, quartiles, whiskers, outliers per category", "x (category), y (numeric), optional group"],
  ["violin", "Distribution shape (KDE curve + inner box)", "x (category), y (numeric), optional group"],
  ["radar", "Several numeric metrics across entities", "metric_columns (numeric), group (entity)"],
  ["pie", "Part-of-whole across ≤ 10 categories", "x (label), y (value)"],
  ["scatter", "Two-numeric-axis relationships", "x (numeric), y (numeric), optional group"],
  ["bubble", "Three-variable relationships", "x, y, z (size), optional label/group"],
  ["heatmap", "Matrix or numeric density (2D histogram)", "x, y (both category or both numeric), z (value/count)"],
  ["symbol_map", "Geographic point data on a world map", "x (lon), y (lat), optional z (size), label, group"],
  ["network", "Node-link relationships", "x (source), y (target), optional z (weight)"],
];

// Theme flows through context so the module-scope Code chip can match the app's
// accent — indigo in dark, red in light — without being recreated per render.
const DarkCtx = createContext(true);

const Code = ({ children }: { children: React.ReactNode }) => {
  const dark = useContext(DarkCtx);
  return (
    <code className={`rounded px-1.5 py-0.5 text-[0.85em] font-mono ${dark ? "bg-indigo-500/15 text-indigo-300" : "bg-red-500/10 text-red-600"}`}>{children}</code>
  );
};

const H = ({ id, children }: { id: string; children: React.ReactNode }) => (
  <h2 id={id} className="scroll-mt-20 text-xl font-semibold mb-3 mt-10 first:mt-0">{children}</h2>
);

// ── page ──────────────────────────────────────────────────────────────────
export default function DocsPage() {
  const [dark, setDark] = useState(true);

  const c = {
    page: dark ? "bg-[#0f1117] text-white/90" : "bg-white text-gray-800",
    header: dark ? "bg-[#12141d] border-white/10" : "bg-white border-gray-200",
    muted: dark ? "text-white/50" : "text-gray-500",
    card: dark ? "bg-white/5 border-white/10" : "bg-gray-50 border-gray-200",
    th: dark ? "text-white/50 border-white/10" : "text-gray-500 border-gray-200",
    tr: dark ? "border-white/5" : "border-gray-100",
    accent: dark ? "text-indigo-300" : "text-red-600",
    tocActive: dark ? "text-white" : "text-gray-900",
  };

  return (
    <DarkCtx.Provider value={dark}>
    <main className={`min-h-screen ${c.page}`}>
      <header className={`sticky top-0 z-10 border-b ${c.header}`}>
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center gap-3">
          <Link href="/" className={`text-sm ${c.muted} hover:${c.tocActive}`}>← Weave</Link>
          <span className="text-sm font-semibold">Docs</span>
          <button
            onClick={() => setDark((d) => !d)}
            title="Toggle theme"
            className={`ml-auto flex items-center gap-1 rounded-full border px-1 py-1 transition-colors cursor-pointer ${dark ? "border-white/10 bg-white/5 hover:bg-white/10" : "border-gray-200 bg-gray-100 hover:bg-gray-200"}`}
          >
            <span className={`flex items-center justify-center w-7 h-7 rounded-full transition-all ${!dark ? "bg-white text-slate-900 shadow-sm" : "text-white/30"}`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
              </svg>
            </span>
            <span className={`flex items-center justify-center w-7 h-7 rounded-full transition-all ${dark ? "bg-white/15 text-white shadow" : "text-gray-400"}`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
              </svg>
            </span>
          </button>
        </div>
      </header>

      {/* TOC + article, centered as a group (snug max width so it doesn't feel
          left-heavy). Sidebar shows from lg and up. */}
      <div className="mx-auto flex w-full max-w-4xl gap-10 px-6 py-10">
        {/* TOC */}
        <nav className="hidden lg:block w-44 shrink-0">
          <ul className="sticky top-20 space-y-1.5 text-sm">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className={`${c.muted} hover:${c.tocActive} transition-colors`}>{s.title}</a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Content */}
        <div className="flex-1 min-w-0 leading-relaxed text-[15px]">
          <H id="overview">Overview</H>
          <p className="mb-3">
            Weave turns a CSV and a plain-English description into an interactive D3 chart — no code, no config.
            Drop in a file, say what you want, and get a live chart you can refine by chatting with it.
          </p>
          <p className={c.muted}>
            Under the hood: your prompt and the dataset schema go to an LLM that picks the chart type and maps
            columns to axes; a transformer aggregates the data; and a D3 template renders it. You never write the mapping — you describe the result.
          </p>

          <H id="getting-started">Getting started</H>
          <ol className="list-decimal pl-5 space-y-2">
            <li><b>Sign in</b> with Google (required to generate — it powers per-user history and limits).</li>
            <li><b>Upload a CSV</b> (drag-and-drop or click). It must be a real CSV with at least one numeric column. Formula cells and messy headers are handled automatically.</li>
            <li><b>Describe the chart</b> in the prompt bar, e.g. <i>&ldquo;revenue over time for each company&rdquo;</i>. One prompt can produce <b>several charts</b> at once (a mini dashboard).</li>
            <li><b>Refine</b> by typing follow-ups on any chart (see below), or <b>Add chart</b> to grow the dashboard.</li>
          </ol>

          <H id="refining">Refining charts</H>
          <p className="mb-4">
            Every chart has a refine bar — talk to it in plain English and only the fields you mention change.
            Common commands (the &ldquo;flags&rdquo;):
          </p>
          <div className={`rounded-xl border overflow-x-auto ${c.card}`}>
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="text-left">
                  <th className={`px-4 py-2.5 font-medium border-b ${c.th}`}>What</th>
                  <th className={`px-4 py-2.5 font-medium border-b ${c.th}`}>Say something like</th>
                  <th className={`px-4 py-2.5 font-medium border-b ${c.th}`}>Effect</th>
                </tr>
              </thead>
              <tbody>
                {REFINE_COMMANDS.map(([what, ex, eff]) => (
                  <tr key={what} className={`border-b last:border-0 ${c.tr}`}>
                    <td className="px-4 py-2.5 font-medium whitespace-nowrap">{what}</td>
                    <td className="px-4 py-2.5"><Code>{ex}</Code></td>
                    <td className={`px-4 py-2.5 ${c.muted}`}>{eff}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={`mt-3 text-sm ${c.muted}`}>
            When you reference a category value that&rsquo;s ambiguous (e.g. &ldquo;America&rdquo; → North/South America), the chart asks which one you meant instead of guessing.
          </p>

          <H id="chart-types">Chart types</H>
          <p className="mb-4">Weave picks the type from your prompt, but you can ask for a specific one. If a type doesn&rsquo;t fit the columns, it&rsquo;s rejected with a suggestion that <i>does</i> fit.</p>
          <div className={`rounded-xl border overflow-x-auto ${c.card}`}>
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="text-left">
                  <th className={`px-4 py-2.5 font-medium border-b ${c.th}`}>Type</th>
                  <th className={`px-4 py-2.5 font-medium border-b ${c.th}`}>Best for</th>
                  <th className={`px-4 py-2.5 font-medium border-b ${c.th}`}>Key columns</th>
                </tr>
              </thead>
              <tbody>
                {CHART_TYPES.map(([t, best, cols]) => (
                  <tr key={t} className={`border-b last:border-0 ${c.tr}`}>
                    <td className="px-4 py-2.5"><Code>{t}</Code></td>
                    <td className="px-4 py-2.5">{best}</td>
                    <td className={`px-4 py-2.5 ${c.muted}`}>{cols}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <H id="faceting">Faceting (small multiples)</H>
          <p className="mb-2">Any <Code>line</Code>, <Code>area</Code>, or <Code>scatter</Code> with a group column can render as one panel per group instead of overlaid series:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li><Code>facet by region</Code> / <Code>small multiples</Code> / <Code>one chart per …</Code> → side-by-side panels (wraps at 3).</li>
            <li><Code>one per row</Code> / <Code>stacked panels</Code> → vertical panels with a shared x-axis.</li>
            <li>Add <Code>free scale</Code> / <Code>independent axes</Code> to give each panel its own y-range.</li>
          </ul>

          <H id="voice">Voice input</H>
          <p>Every prompt, add-chart, and refine bar has a mic button. Press <Code>⌥/Alt+Shift+V</Code> to toggle recording for the field you&rsquo;re in, then <Code>Enter</Code> to submit the transcript. Uses your browser&rsquo;s built-in speech recognition (Chrome/Edge).</p>

          <H id="accounts">Accounts, threads & limits</H>
          <ul className="list-disc pl-5 space-y-1.5">
            <li><b>Threads</b> — each CSV upload starts a thread (like a chat). Its charts and refine history auto-save to your account. Open the sidebar (top-left) to revisit or restore past threads; your most recent one re-opens on sign-in.</li>
            <li><b>Persistence</b> — threads live server-side, so they survive logout, browser close, and other devices. Signing out clears the screen; nothing of yours is visible to anyone else.</li>
            <li><b>Daily limit</b> — each generation and refine counts as one request against a per-user daily quota (shown in the navbar as <Code>remaining / limit</Code>). A multi-chart prompt is capped to what you have left.</li>
          </ul>

          <H id="export">Export & analyze</H>
          <ul className="list-disc pl-5 space-y-1.5">
            <li><b>Export SVG</b> — HD, Full HD, Social, and Square presets, plus custom dimensions.</li>
            <li><b>Analyze</b> — asks the model to summarize key insights from the chart&rsquo;s data.</li>
            <li><b>Edit panel</b> — fine-tune title, axis labels, colors, and background directly on the chart.</li>
          </ul>

          <H id="samples">Sample datasets</H>
          <p>No CSV handy? The landing page has ready-made datasets (Stock Prices, Company Revenue, World Cities, Diamonds, NYC Restaurants, Iris) — pick one to see an auto-generated dashboard and experiment with refinements. Uploading your own CSV starts fresh.</p>

          <H id="tips">Tips</H>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>Be specific about the story: <i>&ldquo;average price by cut, sorted high to low&rdquo;</i> beats <i>&ldquo;show prices&rdquo;</i>.</li>
            <li>Ask for multiple charts in one prompt — separate intents with &ldquo;and&rdquo;.</li>
            <li>Refinements stack: change the type, then the color, then the sort, one message at a time.</li>
            <li>Currency, thousands separators, percentages, and <Code>-</Code> placeholder cells in your CSV are parsed automatically.</li>
          </ul>

          <div className={`mt-12 pt-6 border-t ${c.tr}`}>
            <Link href="/" className={`text-sm font-medium ${c.accent} hover:underline`}>← Back to Weave</Link>
          </div>
        </div>
      </div>
    </main>
    </DarkCtx.Provider>
  );
}
