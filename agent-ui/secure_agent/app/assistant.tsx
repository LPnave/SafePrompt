"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  unstable_useRemoteThreadListRuntime,
} from "@assistant-ui/react";
import { useDataStreamThreadRuntime } from "@/lib/use-data-stream-thread-runtime";
import { Thread } from "@/components/assistant-ui/thread";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { ThreadListSidebar } from "@/components/assistant-ui/threadlist-sidebar";
import { Separator } from "@/components/ui/separator";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import SettingsDialog from "@/components/SettingsDialog";
import { getToken, getUser, logout, updateStoredUser, type AuthUser } from "@/lib/auth";
import {
  getTimeRestriction,
  isWithinTimeWindow,
} from "@/lib/policy-utils";
import { useSessionTimeout } from "@/hooks/use-session-timeout";
import { createSecureMcpThreadListAdapter } from "@/lib/thread-persistence";
import { LogOut, ShieldCheck, User as UserIcon } from "lucide-react";

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-red-500/10 text-red-600 border-red-500/20",
  engineering: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  hr: "bg-green-500/10 text-green-600 border-green-500/20",
  finance: "bg-amber-500/10 text-amber-600 border-amber-500/20",
};

const SECURITY_LEVEL_COLORS: Record<string, string> = {
  low: "bg-green-500/10 text-green-700 border-green-500/20",
  medium: "bg-yellow-500/10 text-yellow-700 border-yellow-500/20",
  high: "bg-red-500/10 text-red-700 border-red-500/20",
};

function PolicyLevelBadge({ level }: { level: string }) {
  const normalized = level.toLowerCase();
  const color =
    SECURITY_LEVEL_COLORS[normalized] ??
    "bg-muted text-muted-foreground border-border";
  const label = normalized.charAt(0).toUpperCase() + normalized.slice(1);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${color}`}
      title="Role policy security level"
    >
      Policy: {label}
    </span>
  );
}

function RoleBadge({ role }: { role: string }) {
  const color =
    ROLE_COLORS[role] ?? "bg-muted text-muted-foreground border-border";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${color}`}
    >
      <ShieldCheck className="w-3 h-3" />
      {role}
    </span>
  );
}

function profileToAuthUser(profile: Record<string, unknown>): AuthUser {
  return {
    id: profile.id as number,
    username: profile.username as string,
    email: profile.email as string,
    role: profile.role as string,
    department: (profile.department as string | null) ?? null,
    is_admin: profile.is_admin as boolean,
    allow_file_uploads: (profile.allow_file_uploads as boolean) ?? false,
    time_restriction_start: (profile.time_restriction_start as string | null) ?? null,
    time_restriction_end: (profile.time_restriction_end as string | null) ?? null,
    session_timeout_minutes: (profile.session_timeout_minutes as number) ?? 60,
    max_conversation_turns: (profile.max_conversation_turns as number) ?? 50,
    security_level: (profile.security_level as AuthUser["security_level"]) ?? "medium",
    max_prompt_length: (profile.max_prompt_length as number) ?? 4000,
    max_requests_per_day: (profile.max_requests_per_day as number) ?? 100,
    requests_today: (profile.requests_today as number) ?? 0,
  };
}

export const Assistant = () => {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [chatAllowed, setChatAllowed] = useState(true);
  const runtimeBodyRef = useRef<{
    session_id: string | null;
    preflight_token: string | null;
  }>({ session_id: null, preflight_token: null });

  const { showWarning: sessionWarning, touch: touchActivity } = useSessionTimeout(
    mounted ? user?.session_timeout_minutes : undefined,
  );

  useEffect(() => {
    setMounted(true);
    const token = getToken();
    const u = getUser();
    if (!u || !token) {
      router.push("/login");
      return;
    }
    setToken(token);
    setUser(u);

    const backendUrl =
      process.env.NEXT_PUBLIC_SANITIZER_API_URL || "http://localhost:8003";
    fetch(`${backendUrl}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((profile) => {
        if (!profile) return;
        const refreshed = profileToAuthUser(profile);
        setUser(refreshed);
        updateStoredUser(refreshed);
      })
      .catch(() => {
        // Keep cached user on network failure
      });
  }, [router]);

  useEffect(() => {
    if (!mounted) return;
    const check = () => {
      setChatAllowed(
        isWithinTimeWindow(
          user?.time_restriction_start,
          user?.time_restriction_end,
        ),
      );
    };
    check();
    const interval = window.setInterval(check, 60_000);
    return () => window.clearInterval(interval);
  }, [mounted, user?.time_restriction_start, user?.time_restriction_end]);

  useEffect(() => {
    if (!mounted) return;
    const token = getToken();
    if (!token) return;

    const refreshProfile = () => {
      const backendUrl =
        process.env.NEXT_PUBLIC_SANITIZER_API_URL || "http://localhost:8003";
      fetch(`${backendUrl}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((profile) => {
          if (!profile) return;
          const refreshed = profileToAuthUser(profile);
          setUser(refreshed);
          updateStoredUser(refreshed);
        })
        .catch(() => {});
    };

    const onFocus = () => refreshProfile();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [mounted]);

  const adapters = useMemo(
    () =>
      user?.allow_file_uploads
        ? {
            attachments: new CompositeAttachmentAdapter([
              new SimpleImageAttachmentAdapter(),
              new SimpleTextAttachmentAdapter(),
            ]),
          }
        : undefined,
    [user?.allow_file_uploads],
  );

  const threadListAdapter = useMemo(
    () =>
      createSecureMcpThreadListAdapter((remoteId) => {
        runtimeBodyRef.current.session_id = remoteId;
      }),
    [],
  );

  const remoteThreadListOptions = useMemo(
    () => ({
      adapter: threadListAdapter,
      runtimeHook: function RuntimeHook() {
        return useDataStreamThreadRuntime({
          api: "/api/chat",
          headers: async () => {
            const token = getToken();
            return token
              ? { Authorization: `Bearer ${token}` }
              : ({} as Record<string, string>);
          },
          adapters,
          body: runtimeBodyRef.current,
        });
      },
    }),
    [threadListAdapter, adapters],
  );

  const runtime = unstable_useRemoteThreadListRuntime(remoteThreadListOptions);

  const timeRestriction = getTimeRestriction(
    user?.time_restriction_start,
    user?.time_restriction_end,
  );

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const setSessionId = (sessionId: string) => {
    runtimeBodyRef.current.session_id = sessionId;
  };

  const setPreflightToken = (token: string | null) => {
    runtimeBodyRef.current.preflight_token = token;
  };

  return (
    <AssistantRuntimeProvider
      key={user?.allow_file_uploads ? "uploads-on" : "uploads-off"}
      runtime={runtime}
    >
      <SidebarProvider>
        <div className="flex h-dvh w-full pr-0.5">
          <ThreadListSidebar />
          <SidebarInset>
            <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
              <SidebarTrigger />
              <Separator orientation="vertical" className="mr-2 h-4" />
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem className="hidden md:block">
                    <span className="text-sm font-medium text-foreground">
                      SecureMCP
                    </span>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator className="hidden md:block" />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Enterprise AI Assistant</BreadcrumbPage>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>

              <div className="ml-auto flex items-center gap-3">
                {mounted && user && (
                  <div className="hidden md:flex items-center gap-2">
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <UserIcon className="w-3.5 h-3.5" />
                      <span className="font-medium text-foreground">
                        {user.username}
                      </span>
                    </div>
                    <RoleBadge role={user.role} />
                    {user.security_level && (
                      <PolicyLevelBadge level={user.security_level} />
                    )}
                    {user.department && (
                      <span className="text-xs text-muted-foreground">
                        · {user.department}
                      </span>
                    )}
                  </div>
                )}

                {mounted && user?.is_admin && (
                  <a
                    href="/admin"
                    className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium
                               hover:bg-accent hover:text-accent-foreground transition"
                  >
                    Admin
                  </a>
                )}

                {mounted && user?.is_admin && <SettingsDialog />}

                <button
                  onClick={handleLogout}
                  title="Sign out"
                  className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium
                             text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Sign out</span>
                </button>
              </div>
            </header>

            {sessionWarning && (
              <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-800 dark:text-amber-200">
                Your session will expire soon due to inactivity.
              </div>
            )}

            <div className="flex-1 overflow-hidden">
              <Thread
                allowFileUploads={mounted && !!user?.allow_file_uploads}
                timeRestriction={timeRestriction}
                chatAllowed={chatAllowed}
                authToken={token}
                setSessionId={setSessionId}
                setPreflightToken={setPreflightToken}
                onUserActivity={touchActivity}
                maxPromptLength={user?.max_prompt_length ?? 4000}
                maxRequestsPerDay={user?.max_requests_per_day ?? 100}
                requestsToday={user?.requests_today ?? 0}
              />
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </AssistantRuntimeProvider>
  );
};
