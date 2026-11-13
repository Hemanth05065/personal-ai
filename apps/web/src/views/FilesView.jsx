import React, { useState } from "react";
import { request } from "../api.js";
import { useLoad } from "../hooks.js";
import { Async, EmptyState, SectionHead } from "../components/ui.jsx";

export default function FilesView({ notify }) {
  const files = useLoad(() => request("/files"));
  const [selected, setSelected] = useState(null);
  const [opening, setOpening] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState(null); // last search response
  const [searching, setSearching] = useState(false);

  async function open(path) {
    setOpening(true);
    try { setSelected(await request(`/files/${encodeURI(path)}`)); }
    catch (error) { notify(error.message, "error"); }
    finally { setOpening(false); }
  }

  async function runSearch(event) {
    event.preventDefault();
    const text = query.trim();
    if (!text || searching) return;
    setSearching(true);
    try { setFound(await request(`/search?q=${encodeURIComponent(text)}&limit=8`)); }
    catch (error) { notify(error.message, "error"); }
    finally { setSearching(false); }
  }

  const fileRow = (path, detail) => <button type="button" className="row-button" aria-current={selected?.path === path ? "true" : undefined} onClick={() => open(path)}>
    <span>{path}</span><span className="muted">{detail}</span>
  </button>;

  return <div className="page">
    <section>
      <form className="inline-form" onSubmit={runSearch} role="search">
        <label className="grow">Search your files
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Describe what you’re looking for, e.g. train tickets" />
        </label>
        <button className="btn btn-primary" disabled={searching || !query.trim()}>{searching ? "Searching..." : "Search"}</button>
        {found && <button type="button" className="btn" onClick={() => { setFound(null); setQuery(""); }}>Clear</button>}
        <small className="form-hint">Searches by meaning, not exact words. Runs on this computer with {"nomic-embed-text"}.</small>
      </form>
      {searching && <p className="muted" role="status">Searching. Files that changed since the last search are indexed first.</p>}
      {found && !searching && <div aria-live="polite">
        <SectionHead title={`Results for “${found.query}”`}
          hint={`Searched ${found.indexed_files} files${found.newly_indexed ? `, ${found.newly_indexed} newly indexed` : ""}.`}
          count={`${found.results.length} found`} />
        {found.results.length
          ? <ul className="rows">{found.results.map((hit) => <li key={hit.path} className="search-hit">
            {fileRow(hit.path, "Open")}
            <p className="muted snippet">{hit.snippet}</p>
          </li>)}</ul>
          : <EmptyState title="Nothing matched">Try describing it differently, or check the file is plain text.</EmptyState>}
      </div>}
    </section>

    <div className="split">
      <section>
        <Async load={files} rows={4}>{(items) => <>
          <SectionHead title="Workspace files" hint="Reading is automatic. Creating or editing a file asks for approval." count={`${items.length} files`} />
          {items.length ? <ul className="rows rows-tight">{items.map((file) => <li key={file.path}>
            {fileRow(file.path, `${file.size} bytes`)}
          </li>)}</ul> : <EmptyState title="The workspace is empty">Create a “write a file” task on the Tasks screen to add your first document.</EmptyState>}
        </>}</Async>
      </section>
      <section aria-busy={opening}>
        <SectionHead title={selected ? selected.path : "Preview"} hint={selected ? `${selected.size} bytes` : "Choose a text file to read it here."} />
        <pre className="preview" tabIndex={0}>{selected ? selected.content : "No file selected."}</pre>
      </section>
    </div>
  </div>;
}
