import React, { useState } from "react";
import { request, json } from "../api.js";
import Markdown from "../components/Markdown.jsx";
import { EmptyState } from "../components/ui.jsx";

export default function ResearchView({ notify }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(event) {
    event.preventDefault();
    const text = query.trim();
    if (!text || busy) return;
    setBusy(true);
    try { setResult(await request("/research", { method: "POST", body: json({ query: text, max_sources: 3 }) })); }
    catch (error) { notify(error.message, "error"); }
    finally { setBusy(false); }
  }

  return <div className="page page-reading">
    <form className="inline-form" onSubmit={run}>
      <label className="grow">Topic
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="What would you like to investigate?" />
      </label>
      <button className="btn btn-primary" disabled={busy || !query.trim()}>{busy ? "Researching..." : "Research"}</button>
    </form>
    {busy && <p className="muted" role="status">Reading sources and writing the report locally. This can take a minute.</p>}
    {!result && !busy && <EmptyState title="No report yet">Enter a topic to get a cited report written by your local model from Wikipedia.</EmptyState>}
    {result && <article className="report">
      <h2>{result.query}</h2>
      <Markdown text={result.report} />
      <h3>Sources</h3>
      <ol className="sources">{result.sources.map((source) => <li key={source.url}>
        <a href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a>
        <p className="muted">{source.excerpt.slice(0, 240)}{source.excerpt.length > 240 ? "..." : ""}</p>
      </li>)}</ol>
    </article>}
  </div>;
}
