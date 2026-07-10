"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, MessagesSquare } from "lucide-react";
import { adminApi, AdminThreadSummary, StoredChatMessage } from "@/lib/admin-api";

function messageText(msg: StoredChatMessage["message"]): string {
  return msg.content
    .map((part) => (part.type === "text" ? part.text ?? "" : ""))
    .join(" ")
    .trim();
}

export default function ChatHistoryPage() {
  const [users, setUsers] = useState<Array<{ id: number; username: string }>>([]);
  const [selectedUserId, setSelectedUserId] = useState<number | "">("");
  const [threads, setThreads] = useState<AdminThreadSummary[]>([]);
  const [selectedThread, setSelectedThread] = useState<AdminThreadSummary | null>(null);
  const [messages, setMessages] = useState<StoredChatMessage[]>([]);
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchThreads = useCallback(async (userId?: number) => {
    setLoadingThreads(true);
    setError(null);
    try {
      const res = await adminApi.threads.list({
        user_id: userId,
        limit: 100,
      });
      setThreads(res.threads);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load threads");
    } finally {
      setLoadingThreads(false);
    }
  }, []);

  useEffect(() => {
    adminApi.users
      .list()
      .then((list) => setUsers(list.map((u) => ({ id: u.id, username: u.username }))))
      .catch(() => {});
    fetchThreads();
  }, [fetchThreads]);

  useEffect(() => {
    if (selectedUserId === "") {
      fetchThreads();
    } else {
      fetchThreads(Number(selectedUserId));
    }
    setSelectedThread(null);
    setMessages([]);
  }, [selectedUserId, fetchThreads]);

  async function openThread(thread: AdminThreadSummary) {
    setSelectedThread(thread);
    setLoadingMessages(true);
    setError(null);
    try {
      const res = await adminApi.threads.messages(thread.id);
      setMessages(res.messages);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load messages");
      setMessages([]);
    } finally {
      setLoadingMessages(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <MessagesSquare className="w-6 h-6" />
          Chat History
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Read-only view of stored conversations (sanitized user messages and assistant responses).
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted-foreground" htmlFor="user-filter">
          Filter by user
        </label>
        <select
          id="user-filter"
          value={selectedUserId}
          onChange={(e) =>
            setSelectedUserId(e.target.value === "" ? "" : Number(e.target.value))
          }
          className="rounded-lg border border-input bg-background px-3 py-2 text-sm"
        >
          <option value="">All users</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-500/10 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 min-h-[28rem]">
        <div className="rounded-xl border bg-card overflow-hidden">
          <div className="border-b px-4 py-3 text-sm font-medium">Threads</div>
          {loadingThreads ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading…
            </div>
          ) : threads.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              No stored threads yet.
            </div>
          ) : (
            <ul className="divide-y max-h-[32rem] overflow-y-auto">
              {threads.map((thread) => (
                <li key={thread.id}>
                  <button
                    type="button"
                    onClick={() => openThread(thread)}
                    className={`w-full text-left px-4 py-3 hover:bg-muted/50 transition ${
                      selectedThread?.id === thread.id ? "bg-muted" : ""
                    }`}
                  >
                    <div className="font-medium text-sm truncate">
                      {thread.title || "New Chat"}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1 flex flex-wrap gap-x-2">
                      <span>{thread.username}</span>
                      <span>·</span>
                      <span>{thread.message_count} messages</span>
                      <span>·</span>
                      <span>{new Date(thread.updated_at).toLocaleString()}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-xl border bg-card overflow-hidden flex flex-col">
          <div className="border-b px-4 py-3 text-sm font-medium">
            {selectedThread
              ? `${selectedThread.title || "New Chat"} — ${selectedThread.username}`
              : "Transcript"}
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4 max-h-[32rem]">
            {!selectedThread && (
              <p className="text-sm text-muted-foreground text-center py-12">
                Select a thread to view its transcript.
              </p>
            )}
            {selectedThread && loadingMessages && (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                Loading messages…
              </div>
            )}
            {selectedThread && !loadingMessages &&
              messages.map((item) => (
                <div
                  key={item.message.id}
                  className={`rounded-lg px-3 py-2 text-sm ${
                    item.message.role === "user"
                      ? "bg-primary/10 ml-8"
                      : "bg-muted mr-8"
                  }`}
                >
                  <div className="text-xs font-medium text-muted-foreground mb-1 capitalize">
                    {item.message.role}
                  </div>
                  <div className="whitespace-pre-wrap break-words">
                    {messageText(item.message)}
                  </div>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
