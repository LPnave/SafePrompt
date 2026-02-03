"use client";

import { useEffect, useRef } from "react";
import { useThread } from "@assistant-ui/react";

const GEMINI_API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY;

/**
 * Automatically generates and sets a chat title after the first message
 * 
 * Note: This uses a simple approach that works with the data-stream runtime.
 * For full persistence, you would need a persistence adapter.
 */
export function AutoTitleGenerator() {
  const thread = useThread();
  const hasGeneratedTitle = useRef(false);
  const threadIdRef = useRef<string | null>(null);

  useEffect(() => {
    const messages = thread.messages;
    const currentThreadId = thread.threadId;

    // Reset if we switched to a different thread
    if (threadIdRef.current !== currentThreadId) {
      threadIdRef.current = currentThreadId;
      hasGeneratedTitle.current = false;
    }

    // Only run once per thread
    if (hasGeneratedTitle.current) return;
    
    // Check if we have at least one user message and one assistant message
    if (messages.length < 2) return;
    
    const firstUserMessage = messages.find((m) => m.role === "user");
    const firstAssistantMessage = messages.find((m) => m.role === "assistant");
    
    // Only generate title after assistant has responded
    if (!firstUserMessage || !firstAssistantMessage) return;

    hasGeneratedTitle.current = true;

    // Generate title from first user message
    generateAndSetTitle(firstUserMessage);
  }, [thread.messages, thread.threadId]);

  return null; // This component doesn't render anything
}

async function generateAndSetTitle(firstUserMessage: any) {
  try {
    // Try to get the original message before sanitization
    const originalText = (window as any).__firstMessageForTitle;
    
    // Extract text from message content (this will be sanitized version as fallback)
    const sanitizedText =
      firstUserMessage.content
        ?.map((part: any) => (part.type === "text" ? part.text : ""))
        .join(" ") || "";

    // Use original text if available, otherwise use sanitized
    const messageText = originalText || sanitizedText;
    
    // Clean up the stored original text
    if (originalText) {
      delete (window as any).__firstMessageForTitle;
    }

    if (!messageText) return;

    console.log("[AutoTitle] Generating title from:", messageText.substring(0, 100));

    let title: string;

    if (GEMINI_API_KEY) {
      // Use Gemini to generate a nice title
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
        title =
          data.candidates?.[0]?.content?.parts?.[0]?.text?.trim() ||
          messageText.substring(0, 50);
      } else {
        throw new Error(`Gemini API error: ${response.status}`);
      }
    } else {
      // Fallback: use first message truncated
      title = messageText.substring(0, 50) + (messageText.length > 50 ? "..." : "");
    }

    console.log(`[AutoTitle] Generated title: "${title}"`);
    
    // Note: To persist and display titles in the sidebar, you would need to:
    // 1. Use Assistant Cloud (cloud persistence)
    // 2. Add a custom backend endpoint to store thread titles
    // 3. Use localStorage for client-side persistence
    // 
    // For now, the title is generated but not persisted.
    // The thread list will still show "New Chat" as fallback.
  } catch (error) {
    console.error("[AutoTitle] Failed to generate title:", error);
  }
}
