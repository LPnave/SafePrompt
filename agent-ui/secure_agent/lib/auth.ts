/**
 * Auth utilities — token storage, user profile, login/logout.
 *
 * Tokens are stored in:
 *   - localStorage (for client-side JS access)
 *   - a cookie named `auth_token` (for Next.js middleware route protection)
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_SANITIZER_API_URL || "http://localhost:8003";

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const USER_KEY = "auth_user";
const COOKIE_NAME = "auth_token";

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  role: string;
  department: string | null;
  is_admin: boolean;
  allow_file_uploads?: boolean;
  time_restriction_start?: string | null;
  time_restriction_end?: string | null;
  session_timeout_minutes?: number;
  max_conversation_turns?: number;
  security_level?: "low" | "medium" | "high";
  max_prompt_length?: number;
  max_requests_per_day?: number;
  requests_today?: number;
}

// ---------------------------------------------------------------------------
// Cookie helpers (readable by Next.js middleware)
// ---------------------------------------------------------------------------

function setCookie(name: string, value: string, days: number) {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 86400000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Strict`;
}

function deleteCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

export function saveTokens(accessToken: string, refreshToken: string, user: AuthUser) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  // Set cookie so the middleware can gate routes without JS
  setCookie(COOKIE_NAME, accessToken, 1); // 1 day (matches 24h JWT expiry)
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  deleteCookie(COOKIE_NAME);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function updateStoredUser(user: AuthUser) {
  if (typeof window === "undefined") return;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function login(username: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail || "Login failed");
  }

  const data = await res.json();
  const user: AuthUser = data.user;
  saveTokens(data.access_token, data.refresh_token, user);
  return user;
}

export function logout() {
  void invalidateSessionOnServer();
  clearTokens();
}

export async function invalidateSessionOnServer(): Promise<void> {
  if (typeof window === "undefined") return;
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (!token) return;
  try {
    await fetch(`${BACKEND_URL}/api/auth/invalidate-session`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Best-effort server invalidation
  }
}

export async function refreshIfExpired(): Promise<boolean> {
  const token = getToken();
  if (!token) return false;

  // Decode JWT payload (no verification — just check expiry client-side)
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    const payload = JSON.parse(atob(parts[1]));
    const expiry = payload.exp * 1000;
    // Refresh if less than 5 minutes remaining
    if (expiry - Date.now() > 5 * 60 * 1000) return true;
  } catch {
    return false;
  }

  const refreshToken = typeof window !== "undefined"
    ? localStorage.getItem(REFRESH_TOKEN_KEY)
    : null;

  if (!refreshToken) return false;

  try {
    const res = await fetch(`${BACKEND_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      clearTokens();
      return false;
    }

    const data = await res.json();
    const user = getUser();
    if (user) {
      saveTokens(data.access_token, refreshToken, user);
    }
    return true;
  } catch {
    return false;
  }
}
