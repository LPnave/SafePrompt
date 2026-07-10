/**
 * Admin API client — typed fetch wrappers for all admin/reporting endpoints.
 *
 * In the browser, uses same-origin URLs proxied by next.config rewrites.
 * On the server, talks to the backend directly.
 */

const BACKEND_URL =
  typeof window !== "undefined"
    ? ""
    : process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_SANITIZER_API_URL ||
      "http://localhost:8003";

function authHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { ...authHeaders(), ...(init?.headers ?? {}) },
    });
  } catch (err) {
    const hint =
      typeof window !== "undefined"
        ? "Check that the Python backend is running on port 8003."
        : "Backend unreachable from Next.js server.";
    throw new Error(
      err instanceof Error ? `${err.message} — ${hint}` : hint,
    );
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function withQuery(path: string, params: URLSearchParams): string {
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
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

export interface AdminThreadSummary {
  id: string;
  title: string | null;
  status: string;
  user_id: number;
  username: string;
  message_count: number;
  updated_at: string;
}

export interface AdminThreadListResponse {
  threads: AdminThreadSummary[];
  total: number;
}

export interface StoredChatMessage {
  message: {
    id: string;
    role: string;
    content: Array<{ type: string; text?: string }>;
    createdAt?: string;
    status?: { type: string };
  };
  parentId: string | null;
}

export interface ThreadMessagesResponse {
  headId?: string | null;
  messages: StoredChatMessage[];
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
      return apiFetch<UsageSummaryItem[]>(withQuery("/api/reports/usage", params));
    },
    threats: (start?: string, end?: string) => {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiFetch<ThreatBreakdownItem[]>(withQuery("/api/reports/threats", params));
    },
    userActivity: (start?: string, end?: string) => {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiFetch<UserActivityItem[]>(withQuery("/api/reports/users", params));
    },
    blocked: (limit = 100) =>
      apiFetch<BlockedEventRecord[]>(`/api/reports/blocked?limit=${limit}`),
  },

  threads: {
    list: (params?: { user_id?: number; username?: string; limit?: number; offset?: number }) => {
      const search = new URLSearchParams();
      if (params?.user_id != null) search.set("user_id", String(params.user_id));
      if (params?.username) search.set("username", params.username);
      if (params?.limit != null) search.set("limit", String(params.limit));
      if (params?.offset != null) search.set("offset", String(params.offset));
      return apiFetch<AdminThreadListResponse>(
        withQuery("/api/admin/threads", search),
      );
    },
    messages: (threadId: string) =>
      apiFetch<ThreadMessagesResponse>(`/api/admin/threads/${threadId}/messages`),
  },
};
