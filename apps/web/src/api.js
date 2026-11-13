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

export async function request(path, options = {}) {
  const method = options.method || "GET";
  const headers = {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-Assistant-Key": API_KEY } : {}),
    ...(csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method) ? { "X-CSRF-Token": csrfToken } : {}),
    ...options.headers,
  };
  let response;
  try {
    response = await fetch(`${API}/api/v1${path}`, { ...options, method, headers, credentials: "include" });
  } catch {
    throw new Error(`Can’t reach the local API at ${API}. Check that the backend is running.`);
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(describeDetail(data.detail));
    error.status = response.status;
    throw error;
  }
  return data;
}

export const json = (body) => JSON.stringify(body);
