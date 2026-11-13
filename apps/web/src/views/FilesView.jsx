import React, { useState } from "react";
import { request } from "../api.js";
import { useLoad } from "../hooks.js";
import { Async, EmptyState, SectionHead } from "../components/ui.jsx";

export default function FilesView({ notify }) {
  const files = useLoad(() => request("/files"));
  const [selected, setSelected] = useState(null);
  const [opening, setOpening] = useState(false);

  async function open(path) {
    setOpening(true);
    try { setSelected(await request(`/files/${encodeURI(path)}`)); }
    catch (error) { notify(error.message, "error"); }
    finally { setOpening(false); }
  }

  return <div className="page split">
    <section>
      <Async load={files} rows={4}>{(items) => <>
        <SectionHead title="Workspace files" hint="Reading is automatic. Creating or editing a file asks for approval." count={`${items.length} files`} />
        {items.length ? <ul className="rows rows-tight">{items.map((file) => <li key={file.path}>
          <button type="button" className="row-button" aria-current={selected?.path === file.path ? "true" : undefined} onClick={() => open(file.path)}>
            <span>{file.path}</span><span className="muted">{file.size} bytes</span>
          </button>
        </li>)}</ul> : <EmptyState title="The workspace is empty">Create a “write a file” task on the Tasks screen to add your first document.</EmptyState>}
      </>}</Async>
    </section>
    <section aria-busy={opening}>
      <SectionHead title={selected ? selected.path : "Preview"} hint={selected ? `${selected.size} bytes` : "Choose a text file to read it here."} />
      <pre className="preview" tabIndex={0}>{selected ? selected.content : "No file selected."}</pre>
    </section>
  </div>;
}
