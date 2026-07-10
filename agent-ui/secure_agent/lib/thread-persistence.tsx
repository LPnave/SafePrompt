"use client";

import {
  RuntimeAdapterProvider,
  useThreadListItem,
  type ThreadHistoryAdapter,
  type ThreadMessage,
  type unstable_RemoteThreadListAdapter,
} from "@assistant-ui/react";
import { useCallback, useMemo, type ReactNode } from "react";
import { getToken } from "@/lib/auth";

const GEMINI_API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY;

async function threadApiFetch<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    throw new Error(
      err instanceof Error ? err.message : "Failed to reach thread API",
    );
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

function extractMessageText(message: ThreadMessage): string {
  return message.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join(" ")
    .trim();
}

async function generateTitleFromMessages(messages: readonly ThreadMessage[]): Promise<string> {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return "New Chat";
  const messageText = extractMessageText(firstUser);
  if (!messageText) return "New Chat";

  if (GEMINI_API_KEY) {
    try {
      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [
              {
                parts: [
                  {
                    text: `Generate a short, descriptive title (max 6 words) for a conversation that starts with: "${messageText.substring(0, 200)}"\n\nRespond with ONLY the title, no quotes or punctuation.`,
                  },
                ],
              },
            ],
            generationConfig: {
              maxOutputTokens: 20,
              temperature: 0.3,
            },
          }),
        },
      );
      if (response.ok) {
        const data = await response.json();
        const title =
          data.candidates?.[0]?.content?.parts?.[0]?.text?.trim() ||
          messageText.substring(0, 50);
        return title;
      }
    } catch {
      // fall through to truncation
    }
  }

  return messageText.substring(0, 50) + (messageText.length > 50 ? "..." : "");
}

type ThreadSummaryResponse = {
  remoteId: string;
  title?: string | null;
  status: string;
  updated_at: string;
  message_count?: number;
};

type InitializeResponse = {
  remoteId: string;
  externalId?: string | null;
  title: string;
};

type MessageRepositoryResponse = {
  headId?: string | null;
  messages: Array<{ message: ThreadMessage; parentId: string | null }>;
};

/** Ensure persisted messages match assistant-ui ThreadMessage shape (metadata required). */
function normalizeLoadedMessage(message: ThreadMessage): ThreadMessage {
  if (message.role === "assistant") {
    const meta = message.metadata as
      | {
          unstable_state?: unknown;
          unstable_annotations?: unknown[];
          unstable_data?: unknown[];
          steps?: unknown[];
          custom?: Record<string, unknown>;
        }
      | undefined;
    return {
      ...message,
      status: { type: "complete", reason: "stop" },
      metadata: {
        unstable_state: meta?.unstable_state ?? null,
        unstable_annotations: meta?.unstable_annotations ?? [],
        unstable_data: meta?.unstable_data ?? [],
        steps: meta?.steps ?? [],
        custom: meta?.custom ?? {},
      },
    } as ThreadMessage;
  }

  if (message.role === "user") {
    const meta = message.metadata as { custom?: Record<string, unknown> } | undefined;
    return {
      ...message,
      attachments: message.attachments ?? [],
      metadata: { custom: meta?.custom ?? {} },
    } as ThreadMessage;
  }

  const meta = message.metadata as { custom?: Record<string, unknown> } | undefined;
  return {
    ...message,
    metadata: { custom: meta?.custom ?? {} },
  } as ThreadMessage;
}

export function createSecureMcpThreadListAdapter(
  onRemoteId?: (remoteId: string) => void,
): unstable_RemoteThreadListAdapter {
  const ThreadHistoryProvider = function Provider({
    children,
  }: {
    children?: ReactNode;
  }) {
    const threadListItem = useThreadListItem();
    const remoteId = threadListItem.remoteId;

    const history = useMemo<ThreadHistoryAdapter>(
      () => ({
        async load() {
          if (!remoteId) {
            return { messages: [] };
          }
          const data = await threadApiFetch<MessageRepositoryResponse>(
            `/api/threads/${remoteId}/messages`,
          );
          return {
            headId: data.headId,
            messages: data.messages.map((item) => ({
              ...item,
              message: normalizeLoadedMessage(item.message),
            })),
          };
        },
        async append() {
          // Backend persists completed turns in chat_service; load() restores history.
          return;
        },
      }),
      [remoteId],
    );

    const adapters = useMemo(() => ({ history }), [history]);

    return (
      <RuntimeAdapterProvider adapters={adapters}>
        {children}
      </RuntimeAdapterProvider>
    );
  };

  return {
    async list() {
      const rows = await threadApiFetch<ThreadSummaryResponse[]>("/api/threads");
      return {
        threads: rows.map((t) => ({
          status: t.status === "archived" ? ("archived" as const) : ("regular" as const),
          remoteId: t.remoteId,
          title: t.title ?? "New Chat",
          externalId: undefined,
        })),
      };
    },

    async initialize(threadId: string) {
      const created = await threadApiFetch<InitializeResponse>("/api/threads", {
        method: "POST",
        body: JSON.stringify({ id: threadId }),
      });
      onRemoteId?.(created.remoteId);
      return {
        remoteId: created.remoteId,
        externalId: created.externalId ?? undefined,
      };
    },

    async rename(remoteId: string, newTitle: string) {
      await threadApiFetch(`/api/threads/${remoteId}`, {
        method: "PATCH",
        body: JSON.stringify({ title: newTitle }),
      });
    },

    async archive(remoteId: string) {
      await threadApiFetch(`/api/threads/${remoteId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "archived" }),
      });
    },

    async unarchive(remoteId: string) {
      await threadApiFetch(`/api/threads/${remoteId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "active" }),
      });
    },

    async delete(remoteId: string) {
      await threadApiFetch(`/api/threads/${remoteId}`, { method: "DELETE" });
    },

    async generateTitle(remoteId: string, messages: readonly ThreadMessage[]) {
      const title = await generateTitleFromMessages(messages);
      await threadApiFetch(`/api/threads/${remoteId}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      return new ReadableStream();
    },

    unstable_Provider: ThreadHistoryProvider,
  };
}

export const secureMcpThreadListAdapter = createSecureMcpThreadListAdapter();
