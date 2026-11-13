import React from "react";
import { ConfirmButton } from "./ui.jsx";

export const NAV = [
  ["chat", "Chat"], ["research", "Research"], ["memory", "Memory"],
  ["files", "Files"], ["tasks", "Tasks and approvals"], ["security", "Security"],
];

export default function Sidebar({ view, chat, user, modelStatus, drawer, onNavigate, onNewChat, onSignOut }) {
  return <aside className="sidebar" id="sidebar" data-drawer={drawer} inert={drawer === "closed"} aria-label="Main">
    <div className="brand">
      <p className="brand-name">Local Assistant</p>
      <p className="muted">{modelStatus}</p>
    </div>
    <button type="button" className="btn btn-primary" onClick={onNewChat}>New chat</button>
    <nav aria-label="Primary">
      {NAV.map(([id, label]) => <a key={id} href={`#/${id}`} aria-current={view === id ? "page" : undefined} onClick={onNavigate}>{label}</a>)}
    </nav>
    <h2 className="side-heading">Recent conversations</h2>
    <ul className="history">
      {chat.conversations.map((conversation) => <li key={conversation.id} className={chat.conversationId === conversation.id ? "is-current" : ""}>
        <button type="button" className="history-open" aria-current={chat.conversationId === conversation.id ? "true" : undefined} onClick={() => { chat.openConversation(conversation.id); window.location.hash = "#/chat"; onNavigate(); }}>
          <span>{conversation.title}</span>
        </button>
        <ConfirmButton small label={`Delete conversation: ${conversation.title}`} onConfirm={() => chat.deleteConversation(conversation.id)}>Delete</ConfirmButton>
      </li>)}
      {!chat.conversations.length && <li className="muted history-empty">No conversations yet.</li>}
    </ul>
    <div className="account">
      <p className="muted">Private by default. No paid AI API.</p>
      {user && <p>Signed in as <strong>{user.username}</strong></p>}
      {user && <button type="button" className="btn btn-sm" onClick={onSignOut}>Sign out</button>}
    </div>
  </aside>;
}
