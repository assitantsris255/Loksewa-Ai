const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

function extractErrorMessage(data: any): string {
  if (!data) return "An API error occurred";
  if (typeof data === "string") return data;
  if (data.detail && typeof data.detail === "string") return data.detail;
  if (data.error && typeof data.error === "string") return data.error;
  if (data.message && typeof data.message === "string") return data.message;
  if (typeof data === "object") {
    const parts: string[] = [];
    for (const [key, val] of Object.entries(data)) {
      const field = key === "non_field_errors" || key === "detail" ? "" : `${key.replace(/_/g, " ")}: `;
      if (Array.isArray(val)) {
        parts.push(`${field}${val.map(v => typeof v === "object" ? JSON.stringify(v) : String(v)).join(", ")}`);
      } else if (typeof val === "string") {
        parts.push(`${field}${val}`);
      }
    }
    if (parts.length > 0) return parts.join(" | ");
  }
  return "An API error occurred";
}

export class ApiError extends Error {
  constructor(public status: number, public data: any) {
    super(extractErrorMessage(data));
    this.name = "ApiError";
  }
}

export const API_MUTATION_EVENT = "api-mutation-succeeded";

export const getAuthToken = () => {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
};

export const setAuthToken = (access: string, refresh: string) => {
  if (typeof window === "undefined") return;
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
};

export const clearAuthToken = () => {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
};

// Single-flight: the backend rotates and blacklists a refresh token on first
// use (ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION), so when several
// requests hit 401 at the same time only ONE refresh call may be made - the
// rest must await it. Parallel calls with the same refresh token made all but
// the first fail, which then cleared the session and logged the user out.
let refreshInFlight: Promise<string | null> | null = null;

function refreshToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = doRefreshToken().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function doRefreshToken(): Promise<string | null> {
  try {
    const refresh = localStorage.getItem("refresh_token");
    if (!refresh) return null;

    const response = await fetch(`${API_URL}/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) {
      clearAuthToken();
      return null;
    }

    const data = await response.json();
    localStorage.setItem("access_token", data.access);
    // The rotated refresh token replaces the old one (which is now
    // blacklisted); without storing it the next refresh would fail.
    if (data.refresh) localStorage.setItem("refresh_token", data.refresh);
    return data.access;
  } catch {
    // Network error: keep the session; the caller's request will fail
    // normally and can be retried.
    return null;
  }
}

export interface ApiClientOptions extends RequestInit {
  skipRedirect?: boolean;
}

const inFlightGetRequests = new Map<string, Promise<any>>();

export async function apiClient<T>(
  endpoint: string,
  options: ApiClientOptions = {}
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const isGet = (method === "GET" || method === "HEAD") && !options.body;

  if (!isGet) {
    return executeRequest<T>(endpoint, options);
  }

  const token = getAuthToken();
  const dedupKey = `${endpoint}::${token || "anon"}`;

  if (inFlightGetRequests.has(dedupKey)) {
    return inFlightGetRequests.get(dedupKey)! as Promise<T>;
  }

  const promise = executeRequest<T>(endpoint, options).finally(() => {
    inFlightGetRequests.delete(dedupKey);
  });

  inFlightGetRequests.set(dedupKey, promise);
  return promise;
}

async function executeRequest<T>(
  endpoint: string,
  options: ApiClientOptions = {}
): Promise<T> {
  const url = `${API_URL}${endpoint}`;
  
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const config: RequestInit = {
    ...options,
    headers,
    cache: 'no-store',
  };

  let response = await fetch(url, config);

  // Handle Token Expiration or Missing Token
  if (response.status === 401) {
    if (token) {
      const newToken = await refreshToken();
      if (newToken) {
        headers.set("Authorization", `Bearer ${newToken}`);
        response = await fetch(url, { ...config, headers });
      }
    }
    
    if (response.status === 401 && !options.skipRedirect) {
      // Force logout if refresh failed or no token was present. Every role
      // signs in through the same /login form, so there's only one place
      // to send anyone back to.
      if (typeof window !== "undefined") {
        const path = window.location.pathname;
        if (!path.includes("/login")) {
          window.location.href = "/login?expired=true";
          return new Promise(() => {}); // never resolve to prevent further execution
        }
      }
    }
  }

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = { detail: response.statusText };
    }
    
    // Intercept package lock
    if (response.status === 403 && errorData?.code === 'subscription_required' && !options.skipRedirect) {
      if (typeof window !== "undefined") {
        const path = window.location.pathname;
        if (path !== "/student" && !path.startsWith("/student/onboarding") && !path.startsWith("/student/plans")) {
          window.location.href = "/student";
          return new Promise(() => {}); // Prevent further execution
        }
      }
    }

    throw new ApiError(response.status, errorData);
  }

  // Any successful write may change dashboard aggregates; let the query
  // layer (see app/providers.tsx) revalidate the affected cached queries.
  const method = (options.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && typeof window !== "undefined") {
    window.dispatchEvent(new Event(API_MUTATION_EVENT));
  }

  if (response.status === 204) {
    return {} as T;
  }

  // A 200 with an empty body (e.g. Response(status=200) in DRF with no
  // serializer data) is valid and common in this backend, but
  // response.json() throws SyntaxError on empty input - read the text
  // first so a genuinely empty success response doesn't look like a
  // parse failure.
  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text);
}

/**
 * Downloads a file from an authenticated endpoint and saves it via the browser.
 *
 * A plain link or window.open() navigates without the Authorization header, so
 * protected downloads come back as a 401 page. This fetches the bytes with the
 * bearer token (retrying once after a refresh, like apiClient) and hands the
 * resulting blob to a temporary object URL.
 */
export async function downloadFile(
  endpoint: string,
  fallbackFilename: string
): Promise<void> {
  const url = `${API_URL}${endpoint}`;
  const token = getAuthToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response = await fetch(url, { headers });

  if (response.status === 401 && token) {
    const newToken = await refreshToken();
    if (newToken) {
      headers.set("Authorization", `Bearer ${newToken}`);
      response = await fetch(url, { headers });
    }
  }

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = { detail: response.statusText };
    }
    throw new ApiError(response.status, errorData);
  }

  // Prefer the server's filename from Content-Disposition when it sends one.
  let filename = fallbackFilename;
  const disposition = response.headers.get("Content-Disposition");
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (match?.[1]) filename = decodeURIComponent(match[1]);

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/**
 * Downloads a file from an already-absolute, public (no-auth) URL - e.g. the
 * `/api/media/drive/<id>/` links returned by public endpoints like the
 * syllabus page. A plain `<a href target="_blank">` only opens the browser's
 * PDF viewer instead of actually saving the file, so this fetches the bytes
 * and hands them to a temporary object URL the same way downloadFile() does
 * for authenticated downloads.
 */
export async function downloadPublicFile(url: string, fallbackFilename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new ApiError(response.status, { detail: response.statusText });
  }

  let filename = fallbackFilename;
  const disposition = response.headers.get("Content-Disposition");
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (match?.[1]) filename = decodeURIComponent(match[1]);

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
