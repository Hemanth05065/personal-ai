// The server ends a searched answer with one line: "Sources: [title](url) · [title](url)".
// The chat shows that line as chips; this splits it off the answer.

const LINE = /(?:^|\n)Sources: ([^\n]*)\s*$/;
const LINK = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

/** { body, sources: [{ title, url, host }] }. Text without a sources line comes back unchanged. */
export function splitSources(text) {
  const match = LINE.exec(text || "");
  if (!match) return { body: text || "", sources: [] };
  const sources = [...match[1].matchAll(LINK)].map(([, title, url]) => ({ title, url, host: hostOf(url) }));
  if (!sources.length) return { body: text, sources: [] };
  return { body: text.slice(0, match.index).trimEnd(), sources };
}
