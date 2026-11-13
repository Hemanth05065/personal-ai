export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const API_KEY = import.meta.env.VITE_API_KEY || "";

const CSRF_STORAGE_KEY = "assistant_csrf";
let csrfToken = "";
try { csrfToken = sessionStorage.getItem(CSRF_STORAGE_KEY) || ""; } catch { /* storage unavailable */ }

export function setCsrf(token) {
  csrfToken = token || "";
  try {
    if (csrfToken) sessionStorage.setItem(CSRF_STORAGE_KEY, csrfToken);
    else sessionStorage.removeItem(CSRF_STORAGE_KEY);
  } catch { /* storage unavailable */ }
}

function describeDetail(detail) {
  if (!detail) return "The request failed.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  return JSON.stringify(detail);
}

function headersFor(method, extra) {
  return {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-Assistant-Key": API_KEY } : {}),
    ...(csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method) ? { "X-CSRF-Token": csrfToken } : {}),
    ...extra,
  };
}

async function send(path, options) {
  const method = options.method || "GET";
  try {
    return await fetch(`${API}/api/v1${path}`, { ...options, method, headers: headersFor(method, options.headers), credentials: "include" });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(`Can’t reach the local API at ${API}. Check that the backend is running.`);
  }
}

async function failure(response) {
  const data = await response.json().catch(() => ({}));
  const error = new Error(describeDetail(data.detail));
  error.status = response.status;
  return error;
}

export async function request(path, options = {}) {
  const response = await send(path, options);
  if (response.status === 204) return null;
  if (!response.ok) throw await failure(response);
  return response.json().catch(() => ({}));
}

/**
 * POST and read a newline-delimited JSON stream, calling onEvent for each event.
 * Pass an AbortSignal to stop early; the promise then resolves with { aborted: true }.
 */
export async function streamEvents(path, body, onEvent, signal) {
  let response;
  try {
    response = await send(path, { method: "POST", body: JSON.stringify(body), signal });
  } catch (error) {
    if (error.name === "AbortError") return { aborted: true };
    throw error;
  }
  if (!response.ok) throw await failure(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer));
  } catch (error) {
    if (error.name === "AbortError") return { aborted: true };
    throw new Error("The reply stream was interrupted.");
  }
  return { aborted: false };
}

export const json = (body) => JSON.stringify(body);
