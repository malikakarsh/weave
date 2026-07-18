"use client";

import { useState } from "react";
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

// Theme-neutral inline code + section heading (defined at module scope so they
// aren't recreated on every render).
const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="rounded px-1.5 py-0.5 text-[0.85em] font-mono bg-indigo-500/12 text-indigo-500">{children}</code>
);

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
    accent: dark ? "text-indigo-300" : "text-indigo-600",
    tocActive: dark ? "text-white" : "text-gray-900",
  };

  return (
    <main className={`min-h-screen ${c.page}`}>
      <header className={`sticky top-0 z-10 border-b ${c.header}`}>
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center gap-3">
          <Link href="/" className={`text-sm ${c.muted} hover:${c.tocActive}`}>← Weave</Link>
          <span className="text-sm font-semibold">Docs</span>
          <button
            onClick={() => setDark((d) => !d)}
            className={`ml-auto text-xs rounded-full border px-3 py-1 ${c.card} cursor-pointer`}
          >
            {dark ? "Light" : "Dark"} mode
          </button>
        </div>
      </header>

      {/* 3-column grid: [1fr | article | 1fr] keeps the article dead-centered
          while the TOC hugs its left edge (and a balancing right spacer). */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_auto_1fr] gap-8 px-6 py-10">
        {/* TOC */}
        <nav className="hidden xl:block justify-self-end w-48">
          <ul className="sticky top-20 space-y-1.5 text-sm">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className={`${c.muted} hover:${c.tocActive} transition-colors`}>{s.title}</a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Content */}
        <div className="w-full max-w-3xl mx-auto min-w-0 leading-relaxed text-[15px]">
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
          <div className={`rounded-xl border overflow-hidden ${c.card}`}>
            <table className="w-full text-sm">
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
          <div className={`rounded-xl border overflow-hidden ${c.card}`}>
            <table className="w-full text-sm">
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

        {/* right spacer balances the TOC so the article stays centered */}
        <div className="hidden xl:block" />
      </div>
    </main>
  );
}
