import React, { useState } from "react";
import { request, json } from "../api.js";
import { useLoad } from "../hooks.js";
import { Async, ConfirmButton, EmptyState, SectionHead } from "../components/ui.jsx";

export default function MemoryView({ notify }) {
  const memories = useLoad(() => request("/memory"));
  const [draft, setDraft] = useState("");

  async function add(event) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    try {
      await request("/memory", { method: "POST", body: json({ content, category: "preference" }) });
      setDraft(""); notify("Saved to memory."); memories.reload();
    } catch (error) { notify(error.message, "error"); }
  }

  async function forget(id) {
    try { await request(`/memory/${id}`, { method: "DELETE" }); notify("Removed from memory."); memories.reload(); }
    catch (error) { notify(error.message, "error"); }
  }

  return <div className="page page-reading">
    <form className="inline-form" onSubmit={add}>
      <label className="grow">Add a memory
        <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Example: I prefer short, technical answers" aria-describedby="mem-hint" />
      </label>
      <button className="btn btn-primary" disabled={!draft.trim()}>Save memory</button>
      <small id="mem-hint" className="form-hint">Only save details that should shape future conversations.</small>
    </form>
    <Async load={memories} rows={3}>{(items) => <>
      <SectionHead title="Saved memories" count={`${items.length} saved`} />
      {items.length ? <ul className="rows">{items.map((memory) => <li key={memory.id}>
        <div><p>{memory.content}</p><p className="muted">{memory.category}</p></div>
        <ConfirmButton label={`Forget: ${memory.content}`} confirmLabel="Forget it" onConfirm={() => forget(memory.id)}>Forget</ConfirmButton>
      </li>)}</ul> : <EmptyState title="Nothing remembered yet">Add a preference above. You control this list, and every item can be removed.</EmptyState>}
    </>}</Async>
  </div>;
}
