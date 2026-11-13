import React, { useState } from "react";
import { ConfirmButton, EmptyState, ErrorState, SectionHead, Skeleton } from "../components/ui.jsx";

const pad = (value) => String(value).padStart(2, "0");

/** A Date as the "YYYY-MM-DDTHH:mm" local value a datetime-local input expects. */
function localInput(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function inMinutes(minutes) {
  const date = new Date(Date.now() + minutes * 60000);
  date.setSeconds(0, 0);
  return date;
}

function tomorrowAt(hour) {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(hour, 0, 0, 0);
  return date;
}

export function formatWhen(value) {
  return new Date(value).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

const SHORTCUTS = [["In 10 minutes", () => inMinutes(10)], ["In 1 hour", () => inMinutes(60)], ["Tomorrow 9:00", () => tomorrowAt(9)]];

function NotificationSetting() {
  const supported = "Notification" in window;
  const [permission, setPermission] = useState(supported ? Notification.permission : "unsupported");
  if (permission === "granted") return <p className="muted">Windows notifications are on. They appear while this app is open in a browser tab.</p>;
  if (permission === "unsupported") return <p className="muted">This browser can’t show system notifications. Reminders still appear at the top of the app.</p>;
  if (permission === "denied") return <p className="muted">Notifications are blocked for this site. To turn them on, use the lock icon in the address bar, then reload. Reminders still appear at the top of the app.</p>;
  return <div className="notify-setting">
    <p className="muted">Get a Windows notification when a reminder goes off. Your browser will ask once.</p>
    <button type="button" className="btn" onClick={async () => setPermission(await Notification.requestPermission())}>Turn on notifications</button>
  </div>;
}

export default function RemindersView({ reminders }) {
  const [text, setText] = useState("");
  const [when, setWhen] = useState(() => localInput(inMinutes(60)));
  const { items, status, error, refresh } = reminders;

  async function add(event) {
    event.preventDefault();
    const due = new Date(when);
    if (!text.trim() || Number.isNaN(due.getTime())) return;
    if (await reminders.create(text.trim(), due.toISOString())) {
      setText(""); setWhen(localInput(inMinutes(60)));
    }
  }

  const upcoming = items.filter((item) => item.status === "pending");
  const fired = items.filter((item) => item.status === "fired");
  const earlier = items.filter((item) => item.status === "dismissed" || item.status === "cancelled").reverse();

  return <div className="page page-reading">
    <section>
      <form className="form" onSubmit={add}>
        <label>Remind me to
          <input required maxLength={500} value={text} onChange={(event) => setText(event.target.value)} placeholder="Example: call the electricity office" />
        </label>
        <label>When
          <input required type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} />
        </label>
        <div className="row-actions">
          {SHORTCUTS.map(([label, make]) => <button key={label} type="button" className="btn btn-sm" onClick={() => setWhen(localInput(make()))}>{label}</button>)}
        </div>
        <div><button className="btn btn-primary" disabled={!text.trim()}>Set reminder</button></div>
      </form>
    </section>

    <NotificationSetting />

    {status === "loading" && !items.length ? <Skeleton rows={3} />
      : status === "error" && !items.length ? <ErrorState message={error} onRetry={refresh} />
        : <>
          {fired.length > 0 && <section>
            <SectionHead title="Gone off" count={`${fired.length}`} />
            <ul className="rows">{fired.map((item) => <li key={item.id}>
              <div><p>{item.text}</p><p className="muted">Due {formatWhen(item.due_at)}</p></div>
              <button type="button" className="btn" onClick={() => reminders.dismiss(item.id)}>Dismiss</button>
            </li>)}</ul>
          </section>}

          <section>
            <SectionHead title="Upcoming" count={`${upcoming.length}`} />
            {upcoming.length ? <ul className="rows">{upcoming.map((item) => <li key={item.id}>
              <div><p>{item.text}</p><p className="muted">{formatWhen(item.due_at)}</p></div>
              <ConfirmButton label={`Cancel reminder: ${item.text}`} confirmLabel="Cancel it" onConfirm={() => reminders.cancel(item.id)}>Cancel</ConfirmButton>
            </li>)}</ul> : <EmptyState title="Nothing coming up">Set a reminder above and it will go off here and as a notification.</EmptyState>}
          </section>

          {earlier.length > 0 && <details className="disclosure">
            <summary>Earlier this week ({earlier.length})</summary>
            <ul className="rows rows-flush">{earlier.map((item) => <li key={item.id}>
              <div><p>{item.text}</p><p className="muted">{item.status === "cancelled" ? "Cancelled" : "Done"}, due {formatWhen(item.due_at)}</p></div>
            </li>)}</ul>
          </details>}
        </>}
  </div>;
}
