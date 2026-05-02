/**
 * Admin API client — typed fetch wrappers for all admin/reporting endpoints.
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_SANITIZER_API_URL || "http://localhost:8003";

function authHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserRecord {
  id: number;
  username: string;
  email: string;
  role: string;
  department: string | null;
  is_active: boolean;
  created_at: string;
}

export interface RolePolicyRecord {
  id: number;
  role_id: number;
  security_level: string;
  max_prompt_length: number;
  max_requests_per_day: number;
  system_prompt: string | null;
  allowed_topics: string[] | null;
  blocked_topics: string[] | null;
  enforce_topic_restrictions: boolean;
  response_filter_enabled: boolean;
  max_conversation_turns: number;
  session_timeout_minutes: number;
  allow_file_uploads: boolean;
  time_restriction_start: string | null;
  time_restriction_end: string | null;
  updated_at: string;
}

export interface RoleRecord {
  id: number;
  name: string;
  description: string | null;
  is_admin: boolean;
  policy: RolePolicyRecord | null;
}

export interface UsageSummaryItem {
  day: string;
  role: string;
  total: number;
  blocked: number;
  sanitized: number;
}

export interface ThreatBreakdownItem {
  role: string;
  action: string;
  count: number;
}

export interface UserActivityItem {
  user_id: number | null;
  role: string | null;
  department: string | null;
  total_prompts: number;
  blocked: number;
  avg_latency_ms: number;
}

export interface BlockedEventRecord {
  id: string;
  timestamp: string;
  user_id: number | null;
  user_role: string | null;
  department: string | null;
  prompt_length: number;
  block_reason: string | null;
  threats_detected: string[] | null;
  security_level_used: string | null;
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export const adminApi = {
  users: {
    list: () => apiFetch<UserRecord[]>("/api/admin/users"),
    create: (data: {
      username: string;
      email: string;
      password: string;
      role: string;
      department?: string;
    }) => apiFetch<UserRecord>("/api/admin/users", { method: "POST", body: JSON.stringify(data) }),
    update: (id: number, data: Partial<{ role_name: string; department: string; is_active: boolean }>) =>
      apiFetch<UserRecord>(`/api/admin/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deactivate: (id: number) =>
      fetch(`${BACKEND_URL}/api/admin/users/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      }),
  },

  roles: {
    list: () => apiFetch<RoleRecord[]>("/api/admin/roles"),
    create: (data: { name: string; description?: string; is_admin?: boolean }) =>
      apiFetch<RoleRecord>("/api/admin/roles", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (
      id: number,
      data: Partial<{ name: string; description: string; is_admin: boolean }>
    ) =>
      apiFetch<RoleRecord>(`/api/admin/roles/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      fetch(`${BACKEND_URL}/api/admin/roles/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      }),
    updatePolicy: (roleId: number, data: Partial<RolePolicyRecord>) =>
      apiFetch<RolePolicyRecord>(`/api/admin/policies/${roleId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    createPolicy: (roleId: number) =>
      apiFetch<RolePolicyRecord>(`/api/admin/policies/${roleId}`, {
        method: "POST",
      }),
  },

  reports: {
    usage: (start?: string, end?: string) => {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiFetch<UsageSummaryItem[]>(`/api/reports/usage?${params}`);
    },
    threats: (start?: string, end?: string) => {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiFetch<ThreatBreakdownItem[]>(`/api/reports/threats?${params}`);
    },
    userActivity: (start?: string, end?: string) => {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiFetch<UserActivityItem[]>(`/api/reports/users?${params}`);
    },
    blocked: (limit = 100) =>
      apiFetch<BlockedEventRecord[]>(`/api/reports/blocked?limit=${limit}`),
  },
};
