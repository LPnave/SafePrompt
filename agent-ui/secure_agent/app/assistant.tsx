"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useDataStreamRuntime } from "@assistant-ui/react-data-stream";
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
import { getToken, getUser, logout, type AuthUser } from "@/lib/auth";
import { LogOut, ShieldCheck, User as UserIcon } from "lucide-react";

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-red-500/10 text-red-600 border-red-500/20",
  engineering: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  hr: "bg-green-500/10 text-green-600 border-green-500/20",
  finance: "bg-amber-500/10 text-amber-600 border-amber-500/20",
};

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

export const Assistant = () => {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const token = getToken();

  useEffect(() => {
    const u = getUser();
    if (!u || !token) {
      router.push("/login");
      return;
    }
    setUser(u);
  }, [router, token]);

  // Pass the Bearer token in every chat request header
  const runtime = useDataStreamRuntime({
    api: "/api/chat",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <AssistantRuntimeProvider runtime={runtime}>
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

              {/* Right side — user info + actions */}
              <div className="ml-auto flex items-center gap-3">
                {user && (
                  <div className="hidden md:flex items-center gap-2">
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <UserIcon className="w-3.5 h-3.5" />
                      <span className="font-medium text-foreground">
                        {user.username}
                      </span>
                    </div>
                    <RoleBadge role={user.role} />
                    {user.department && (
                      <span className="text-xs text-muted-foreground">
                        · {user.department}
                      </span>
                    )}
                  </div>
                )}

                {/* Admin panel link — admin role only */}
                {user?.is_admin && (
                  <a
                    href="/admin"
                    className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium
                               hover:bg-accent hover:text-accent-foreground transition"
                  >
                    Admin
                  </a>
                )}

                <SettingsDialog />

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

            <div className="flex-1 overflow-hidden">
              <Thread />
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </AssistantRuntimeProvider>
  );
};
