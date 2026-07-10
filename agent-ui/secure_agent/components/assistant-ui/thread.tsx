import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  Clock,
  CopyIcon,
  PencilIcon,
  RefreshCwIcon,
  Square,
  Loader2,
} from "lucide-react";

import {
  ActionBarPrimitive,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAssistantState,
  useComposerRuntime,
  useThreadListItem,
  useThreadRuntime,
} from "@assistant-ui/react";

import type { FC } from "react";
import { useCallback, useState } from "react";
import { LazyMotion, MotionConfig, domAnimation } from "motion/react";
import * as m from "motion/react-m";

import { Button } from "@/components/ui/button";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import {
  ComposerAddAttachment,
  ComposerAttachments,
  UserMessageAttachments,
} from "@/components/assistant-ui/attachment";

import { cn } from "@/lib/utils";
import { formatTimeWindowLocal, type TimeRestriction } from "@/lib/policy-utils";

export interface ThreadProps {
  allowFileUploads?: boolean;
  timeRestriction?: TimeRestriction | null;
  chatAllowed?: boolean;
  authToken?: string | null;
  setSessionId?: (sessionId: string) => void;
  setPreflightToken?: (token: string | null) => void;
  onUserActivity?: () => void;
  maxPromptLength?: number;
  maxRequestsPerDay?: number;
  requestsToday?: number;
}

export const Thread: FC<ThreadProps> = ({
  allowFileUploads = false,
  timeRestriction = null,
  chatAllowed = true,
  authToken = null,
  setSessionId,
  setPreflightToken,
  onUserActivity,
  maxPromptLength = 4000,
  maxRequestsPerDay = 100,
  requestsToday = 0,
}) => {
  return (
    <LazyMotion features={domAnimation}>
      <MotionConfig reducedMotion="user">
        <ThreadPrimitive.Root
          className="aui-root aui-thread-root @container flex h-full flex-col bg-background"
          style={{
            ["--thread-max-width" as string]: "44rem",
          }}
        >
          <ThreadPrimitive.Viewport className="aui-thread-viewport relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll px-4">
            <ThreadPrimitive.If empty>
              <ThreadWelcome />
            </ThreadPrimitive.If>

            <ThreadPrimitive.Messages
              components={{
                UserMessage,
                EditComposer,
                AssistantMessage,
              }}
            />

            <ThreadPrimitive.If empty={false}>
              <div className="aui-thread-viewport-spacer min-h-8 grow" />
            </ThreadPrimitive.If>

            <Composer
              allowFileUploads={allowFileUploads}
              timeRestriction={timeRestriction}
              chatAllowed={chatAllowed}
              authToken={authToken}
              setSessionId={setSessionId}
              setPreflightToken={setPreflightToken}
              onUserActivity={onUserActivity}
              maxPromptLength={maxPromptLength}
              maxRequestsPerDay={maxRequestsPerDay}
              requestsToday={requestsToday}
            />
          </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
      </MotionConfig>
    </LazyMotion>
  );
};

const ThreadScrollToBottom: FC = () => {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <TooltipIconButton
        tooltip="Scroll to bottom"
        variant="outline"
        className="aui-thread-scroll-to-bottom absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible dark:bg-background dark:hover:bg-accent"
      >
        <ArrowDownIcon />
      </TooltipIconButton>
    </ThreadPrimitive.ScrollToBottom>
  );
};

const ThreadWelcome: FC = () => {
  return (
    <div className="aui-thread-welcome-root mx-auto my-auto flex w-full max-w-[var(--thread-max-width)] flex-grow flex-col">
      <div className="aui-thread-welcome-center flex w-full flex-grow flex-col items-center justify-center">
        <div className="aui-thread-welcome-message flex size-full flex-col justify-center px-8">
          <m.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="aui-thread-welcome-message-motion-1 text-2xl font-semibold"
          >
            Hello there!
          </m.div>
          <m.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ delay: 0.1 }}
            className="aui-thread-welcome-message-motion-2 text-2xl text-muted-foreground/65"
          >
            How can I help you today?
          </m.div>
        </div>
      </div>
      <ThreadSuggestions />
    </div>
  );
};

const ThreadSuggestions: FC = () => {
  return (
    <div className="aui-thread-welcome-suggestions grid w-full gap-2 pb-4 @md:grid-cols-2">
      {[
        {
          title: "What's the weather",
          label: "in San Francisco?",
          action: "What's the weather in San Francisco?",
        },
        {
          title: "Explain React hooks",
          label: "like useState and useEffect",
          action: "Explain React hooks like useState and useEffect",
        },
        {
          title: "Write a SQL query",
          label: "to find top customers",
          action: "Write a SQL query to find top customers",
        },
        {
          title: "Create a meal plan",
          label: "for healthy weight loss",
          action: "Create a meal plan for healthy weight loss",
        },
      ].map((suggestedAction, index) => (
        <m.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          transition={{ delay: 0.05 * index }}
          key={`suggested-action-${suggestedAction.title}-${index}`}
          className="aui-thread-welcome-suggestion-display [&:nth-child(n+3)]:hidden @md:[&:nth-child(n+3)]:block"
        >
          <ThreadPrimitive.Suggestion
            prompt={suggestedAction.action}
            asChild
          >
            <Button
              variant="ghost"
              className="aui-thread-welcome-suggestion h-auto w-full flex-1 flex-wrap items-start justify-start gap-1 rounded-3xl border px-5 py-4 text-left text-sm @md:flex-col dark:hover:bg-accent/60"
              aria-label={suggestedAction.action}
            >
              <span className="aui-thread-welcome-suggestion-text-1 font-medium">
                {suggestedAction.title}
              </span>
              <span className="aui-thread-welcome-suggestion-text-2 text-muted-foreground">
                {suggestedAction.label}
              </span>
            </Button>
          </ThreadPrimitive.Suggestion>
        </m.div>
      ))}
    </div>
  );
};

const Composer: FC<{
  allowFileUploads: boolean;
  timeRestriction: TimeRestriction | null;
  chatAllowed: boolean;
  authToken: string | null;
  setSessionId?: (sessionId: string) => void;
  setPreflightToken?: (token: string | null) => void;
  onUserActivity?: () => void;
  maxPromptLength: number;
  maxRequestsPerDay: number;
  requestsToday: number;
}> = ({
  allowFileUploads,
  timeRestriction,
  chatAllowed,
  authToken,
  setSessionId,
  setPreflightToken,
  onUserActivity,
  maxPromptLength,
  maxRequestsPerDay,
  requestsToday,
}) => {
  const [textLength, setTextLength] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const isRunning = useAssistantState(({ thread }) => thread.isRunning);
  const isProcessing = isSending || isRunning;
  const windowLabel =
    timeRestriction &&
    formatTimeWindowLocal(timeRestriction.start, timeRestriction.end);

  return (
    <div className="aui-composer-wrapper sticky bottom-0 mx-auto flex w-full max-w-[var(--thread-max-width)] flex-col gap-4 overflow-visible rounded-t-3xl bg-background pb-4 md:pb-6">
      <ThreadScrollToBottom />
      {!chatAllowed && timeRestriction && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-100">
          <Clock className="size-4 shrink-0" />
          <span>
            Chat is unavailable outside your allowed hours: {windowLabel}
          </span>
        </div>
      )}
      <ComposerPrimitive.Root
        className={cn(
          "aui-composer-root relative flex w-full flex-col rounded-3xl border border-border bg-muted px-1 pt-2 shadow-[0_9px_9px_0px_rgba(0,0,0,0.01),0_2px_5px_0px_rgba(0,0,0,0.06)] dark:border-muted-foreground/15",
          !chatAllowed && "pointer-events-none opacity-60",
          isProcessing && chatAllowed && "opacity-80",
        )}
      >
        <ComposerAttachments />
        <ComposerPrimitive.Input
          placeholder={
            isProcessing
              ? "Processing your prompt…"
              : chatAllowed
                ? "Enter a Prompt"
                : "Chat unavailable outside allowed hours"
          }
          className="aui-composer-input mb-1 max-h-32 min-h-16 w-full resize-none bg-transparent px-3.5 pt-1.5 pb-3 text-base outline-none placeholder:text-muted-foreground focus:outline-primary disabled:cursor-not-allowed disabled:opacity-60"
          rows={1}
          autoFocus={chatAllowed && !isProcessing}
          aria-label="Message input"
          disabled={!chatAllowed || isProcessing}
          onInput={(e) => setTextLength(e.currentTarget.value.length)}
        />
        <div className="flex items-center justify-between px-3.5 pb-1 text-xs text-muted-foreground">
          <span
            className={cn(
              textLength > maxPromptLength * 0.9 && "text-amber-600",
              textLength > maxPromptLength && "text-destructive",
            )}
          >
            {textLength} / {maxPromptLength}
          </span>
          <span
            className={cn(
              requestsToday >= maxRequestsPerDay && "text-destructive",
            )}
          >
            {requestsToday} / {maxRequestsPerDay} requests today
          </span>
        </div>
        <ComposerAction
          allowFileUploads={allowFileUploads && chatAllowed}
          authToken={authToken}
          setSessionId={setSessionId}
          setPreflightToken={setPreflightToken}
          onUserActivity={onUserActivity}
          chatAllowed={chatAllowed}
          maxPromptLength={maxPromptLength}
          maxRequestsPerDay={maxRequestsPerDay}
          requestsToday={requestsToday}
          textLength={textLength}
          isSending={isSending}
          setIsSending={setIsSending}
          isProcessing={isProcessing}
        />
      </ComposerPrimitive.Root>
    </div>
  );
};

const BACKEND_URL = "http://localhost:8003";

const ComposerAction: FC<{
  allowFileUploads: boolean;
  authToken: string | null;
  setSessionId?: (sessionId: string) => void;
  setPreflightToken?: (token: string | null) => void;
  onUserActivity?: () => void;
  chatAllowed: boolean;
  maxPromptLength: number;
  maxRequestsPerDay: number;
  requestsToday: number;
  textLength: number;
  isSending: boolean;
  setIsSending: (value: boolean) => void;
  isProcessing: boolean;
}> = ({
  allowFileUploads,
  authToken,
  setSessionId,
  setPreflightToken,
  onUserActivity,
  chatAllowed,
  maxPromptLength,
  maxRequestsPerDay,
  requestsToday,
  textLength,
  isSending,
  setIsSending,
  isProcessing,
}) => {
  const composer = useComposerRuntime();
  const thread = useThreadRuntime();
  const threadListItem = useThreadListItem({ optional: true });
  const [sendError, setSendError] = useState<string | null>(null);

  const overLength = textLength > maxPromptLength;
  const atDailyQuota = requestsToday >= maxRequestsPerDay;
  const sendDisabled =
    !chatAllowed || overLength || atDailyQuota || isProcessing;

  const handleSanitizedSend = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (sendDisabled || isSending) return;

      onUserActivity?.();
      setSendError(null);
      setPreflightToken?.(null);

      const state = composer.getState();
      const text = state.text || "";
      const hasAttachments = state.attachments.length > 0;

      if (!text.trim() && !hasAttachments) return;

      setIsSending(true);
      try {
        const threadState = thread.getState();
        const sessionId = threadListItem?.remoteId ?? threadState.threadId;
        setSessionId?.(sessionId);

        let sanitizedText = text;
        if (text.trim() || hasAttachments) {
          const sanitizeResponse = await fetch(`${BACKEND_URL}/api/sanitize`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
            },
            body: JSON.stringify({
              prompt: text,
              session_id: sessionId,
              has_attachments: hasAttachments,
            }),
          });

          if (sanitizeResponse.status === 401) {
            const err = await sanitizeResponse.json().catch(() => ({}));
            if ((err as { detail?: string }).detail === "Session expired") {
              window.location.href = "/login?reason=session_expired";
              return;
            }
          }

          if (!sanitizeResponse.ok) {
            const err = await sanitizeResponse.json().catch(() => ({}));
            const message =
              (err as { detail?: string }).detail || "Request blocked by policy";
            setSendError(message);
            return;
          }

          const sanitizeData = await sanitizeResponse.json();
          sanitizedText = sanitizeData.sanitized_prompt || text;
          setPreflightToken?.(sanitizeData.preflight_token ?? null);
        }

        composer.setText(sanitizedText);
        await composer.send();
      } catch (error) {
        console.error("[SanitizingComposer] Error:", error);
        setSendError(
          error instanceof Error ? error.message : "Failed to send message",
        );
      } finally {
        setIsSending(false);
      }
    },
    [
      authToken,
      composer,
      sendDisabled,
      isSending,
      setIsSending,
      onUserActivity,
      setPreflightToken,
      setSessionId,
      thread,
      threadListItem?.remoteId,
    ],
  );

  return (
    <div className="aui-composer-action-wrapper relative mx-1 mt-2 mb-2 flex flex-col gap-2">
      {sendError && (
        <p className="text-xs text-destructive px-1">{sendError}</p>
      )}
      <div className="flex items-center justify-between">
      {allowFileUploads ? <ComposerAddAttachment /> : <div className="size-[34px]" />}

      <ThreadPrimitive.If running={false}>
        <TooltipIconButton
          tooltip={isSending ? "Processing…" : "Send message"}
          side="bottom"
          type="button"
          variant="default"
          size="icon"
          className="aui-composer-send size-[34px] rounded-full p-1"
          aria-label={isSending ? "Processing message" : "Send message"}
          onClick={handleSanitizedSend}
          disabled={sendDisabled}
        >
          {isSending ? (
            <Loader2 className="aui-composer-send-icon size-5 animate-spin" />
          ) : (
            <ArrowUpIcon className="aui-composer-send-icon size-5" />
          )}
        </TooltipIconButton>
      </ThreadPrimitive.If>

      <ThreadPrimitive.If running>
        <ComposerPrimitive.Cancel asChild>
          <Button
            type="button"
            variant="default"
            size="icon"
            className="aui-composer-cancel size-[34px] rounded-full border border-muted-foreground/60 hover:bg-primary/75 dark:border-muted-foreground/90"
            aria-label="Stop generating"
          >
            <Square className="aui-composer-cancel-icon size-3.5 fill-white dark:fill-black" />
          </Button>
        </ComposerPrimitive.Cancel>
      </ThreadPrimitive.If>
      </div>
    </div>
  );
};

const MessageError: FC = () => {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive dark:bg-destructive/5 dark:text-red-200">
        <ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};

const AssistantMessage: FC = () => {
  return (
    <MessagePrimitive.Root asChild>
      <div
        className="aui-assistant-message-root relative mx-auto w-full max-w-[var(--thread-max-width)] animate-in py-4 duration-150 ease-out fade-in slide-in-from-bottom-1 last:mb-24"
        data-role="assistant"
      >
        <div className="aui-assistant-message-content mx-2 leading-7 break-words text-foreground">
          <MessagePrimitive.Parts
            components={{
              Text: MarkdownText,
              tools: { Fallback: ToolFallback },
            }}
          />
          <MessageError />
        </div>

        <div className="aui-assistant-message-footer mt-2 ml-2 flex">
          <BranchPicker />
          <AssistantActionBar />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

const AssistantActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      autohideFloat="single-branch"
      className="aui-assistant-action-bar-root col-start-3 row-start-2 -ml-1 flex gap-1 text-muted-foreground data-floating:absolute data-floating:rounded-md data-floating:border data-floating:bg-background data-floating:p-1 data-floating:shadow-sm"
    >
      <ActionBarPrimitive.Copy asChild>
        <TooltipIconButton tooltip="Copy">
          <MessagePrimitive.If copied>
            <CheckIcon />
          </MessagePrimitive.If>
          <MessagePrimitive.If copied={false}>
            <CopyIcon />
          </MessagePrimitive.If>
        </TooltipIconButton>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.Reload asChild>
        <TooltipIconButton tooltip="Refresh">
          <RefreshCwIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Reload>
    </ActionBarPrimitive.Root>
  );
};

const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root asChild>
      <div
        className="aui-user-message-root mx-auto grid w-full max-w-[var(--thread-max-width)] animate-in auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] gap-y-2 px-2 py-4 duration-150 ease-out fade-in slide-in-from-bottom-1 first:mt-3 last:mb-5 [&:where(>*)]:col-start-2"
        data-role="user"
      >
        <UserMessageAttachments />

        <div className="aui-user-message-content-wrapper relative col-start-2 min-w-0">
          <div className="aui-user-message-content rounded-3xl bg-muted px-5 py-2.5 break-words text-foreground">
            <MessagePrimitive.Parts />
          </div>
          <div className="aui-user-action-bar-wrapper absolute top-1/2 left-0 -translate-x-full -translate-y-1/2 pr-2">
            <UserActionBar />
          </div>
        </div>

        <BranchPicker className="aui-user-branch-picker col-span-full col-start-1 row-start-3 -mr-1 justify-end" />
      </div>
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-user-action-bar-root flex flex-col items-end"
    >
      <ActionBarPrimitive.Edit asChild>
        <TooltipIconButton tooltip="Edit" className="aui-user-action-edit p-4">
          <PencilIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
};

const EditComposer: FC = () => {
  return (
    <div className="aui-edit-composer-wrapper mx-auto flex w-full max-w-[var(--thread-max-width)] flex-col gap-4 px-2 first:mt-4">
      <ComposerPrimitive.Root className="aui-edit-composer-root ml-auto flex w-full max-w-7/8 flex-col rounded-xl bg-muted">
        <ComposerPrimitive.Input
          className="aui-edit-composer-input flex min-h-[60px] w-full resize-none bg-transparent p-4 text-foreground outline-none"
          autoFocus
        />

        <div className="aui-edit-composer-footer mx-3 mb-3 flex items-center justify-center gap-2 self-end">
          <ComposerPrimitive.Cancel asChild>
            <Button variant="ghost" size="sm" aria-label="Cancel edit">
              Cancel
            </Button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <Button size="sm" aria-label="Update message">
              Update
            </Button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </div>
  );
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
  className,
  ...rest
}) => {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn(
        "aui-branch-picker-root mr-2 -ml-2 inline-flex items-center text-xs text-muted-foreground",
        className,
      )}
      {...rest}
    >
      <BranchPickerPrimitive.Previous asChild>
        <TooltipIconButton tooltip="Previous">
          <ChevronLeftIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Next">
          <ChevronRightIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};
