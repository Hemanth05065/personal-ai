import React from "react";

// A small, safe Markdown renderer: React elements only, never raw HTML.
// Supports paragraphs, headings, lists, quotes, fenced code, inline code, bold, italic and http(s) links.

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;

function inline(text, prefix) {
  const nodes = [];
  let last = 0;
  let index = 0;
  let match;
  INLINE.lastIndex = 0;
  while ((match = INLINE.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${prefix}-${index++}`;
    if (match[1]) nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    else if (match[2]) nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    else if (match[3]) nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    else nodes.push(<a key={key} href={match[5]} target="_blank" rel="noreferrer noopener">{token.slice(1, token.indexOf("]("))}</a>);
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function parse(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith("```")) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) code.push(lines[i++]);
      i++;
      const indent = Math.min(...code.filter((row) => row.trim()).map((row) => row.match(/^\s*/)[0].length), Infinity);
      blocks.push({ type: "code", text: code.map((row) => row.slice(Number.isFinite(indent) ? indent : 0)).join("\n") });
    } else if (/^#{1,6}\s/.test(line)) {
      blocks.push({ type: "heading", text: line.replace(/^#{1,6}\s+/, "") });
      i++;
    } else if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      blocks.push({ type: "ul", items });
    } else if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      let start = parseInt(line.trim(), 10) || 1;
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      // A list interrupted by code blocks ("1. x / code / 1. y") keeps counting.
      let back = blocks.length - 1;
      while (back >= 0 && blocks[back].type === "code") back--;
      if (start === 1 && back < blocks.length - 1 && blocks[back]?.type === "ol") start = blocks[back].start + blocks[back].items.length;
      blocks.push({ type: "ol", items, start });
    } else if (line.startsWith(">")) {
      const quote = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push({ type: "quote", text: quote.join("\n") });
    } else {
      const paragraph = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*[-*]\s+|\s*\d+[.)]\s+|>|```)/.test(lines[i])) paragraph.push(lines[i++]);
      blocks.push({ type: "p", text: paragraph.join("\n") });
    }
  }
  return blocks;
}

function lines(text, prefix) {
  return text.split("\n").flatMap((part, index) => (index ? [<br key={`${prefix}-br${index}`} />, ...inline(part, `${prefix}-${index}`)] : inline(part, `${prefix}-${index}`)));
}

export default function Markdown({ text }) {
  const blocks = parse(text || "");
  return <div className="prose">{blocks.map((block, index) => {
    const key = `b${index}`;
    switch (block.type) {
      case "code": return <pre key={key}><code>{block.text}</code></pre>;
      case "heading": return <p key={key} className="prose-heading">{inline(block.text, key)}</p>;
      case "ul": return <ul key={key}>{block.items.map((item, n) => <li key={n}>{inline(item, `${key}-${n}`)}</li>)}</ul>;
      case "ol": return <ol key={key} start={block.start}>{block.items.map((item, n) => <li key={n}>{inline(item, `${key}-${n}`)}</li>)}</ol>;
      case "quote": return <blockquote key={key}>{lines(block.text, key)}</blockquote>;
      default: return <p key={key}>{lines(block.text, key)}</p>;
    }
  })}</div>;
}
