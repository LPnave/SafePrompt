/**
 * Chat API Route - Proxy to Python Backend
 *
 * Flow:
 * 1. Frontend sends messages to this route
 * 2. This route forwards to Python backend
 * 3. Python backend sanitizes and calls Gemini
 * 4. This route parses the stream and forwards sanitization metadata
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_SANITIZER_API_URL || "http://localhost:8003";

interface Message {
  role: string;
  content: string;
}

interface ChatRequest {
  messages: Message[];
}

export async function POST(req: Request) {
  try {
    const { messages }: ChatRequest = await req.json();

    console.log(`[Chat] Received ${messages.length} messages`);

    // Forward to Python backend (which handles sanitization + Gemini)
    const response = await fetch(`${BACKEND_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messages: messages,
        // Don't override security_level - use backend's global setting
        stream: true,
      }),
    });

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
      console.error("[Chat] Backend error:", error);

      // Extract error message properly
      const errorMessage =
        error.detail || error.error || "Failed to get response from AI";

      // Return error in data stream protocol format
      const encoder = new TextEncoder();
      const errorStream = new ReadableStream({
        start(controller) {
          // Send error as text delta
          controller.enqueue(
            encoder.encode(`0:${JSON.stringify(errorMessage)}\n`),
          );
          // Send finish with error reason
          controller.enqueue(
            encoder.encode(`e:${JSON.stringify({ finishReason: "error" })}\n`),
          );
          controller.close();
        },
      });

      return new Response(errorStream, {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "X-Vercel-AI-Data-Stream": "v1",
        },
      });
    }

    // Get the stream from Python backend
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error("No response body from backend");
    }

    // Create a properly formatted stream for assistant-ui
    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        try {
          let buffer = "";
          // let sanitizationData: any;
          let sanitizationData: {
            is_safe?: boolean;
            warnings?: string[];
          } | null = null;

          // Read the stream from Python backend
          while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || ""; // Keep incomplete line in buffer

            for (const line of lines) {
              if (!line.trim()) continue;

              // Parse each line (format: "code:data")
              const colonIndex = line.indexOf(":");
              if (colonIndex === -1) continue;

              const code = line.substring(0, colonIndex);
              const data = line.substring(colonIndex + 1);

              if (code === "8") {
                // Sanitization metadata - just log it, don't display to avoid [object Object] issue
                try {
                  const metadata = JSON.parse(data);
                  sanitizationData = metadata[0]; // Get first item from array
                  console.log(
                    "[Chat Proxy] Sanitization applied:",
                    sanitizationData,
                  );

                  // Don't send as annotation to avoid [object Object] display issue
                  // The sanitization already happened, user doesn't need to see internal metadata
                } catch (e) {
                  console.error(
                    "[Chat Proxy] Failed to parse sanitization metadata:",
                    e,
                  );
                }
              } else if (code === "0") {
                // Text delta - forward as-is
                controller.enqueue(encoder.encode(line + "\n"));
              } else if (code === "d") {
                // Finish message - convert to 'e' format for assistant-ui
                try {
                  const finishData = JSON.parse(data);
                  controller.enqueue(
                    encoder.encode(`e:${JSON.stringify(finishData)}\n`),
                  );
                } catch {
                  // If parse fails, send default finish
                  controller.enqueue(
                    encoder.encode(
                      `e:${JSON.stringify({ finishReason: "stop" })}\n`,
                    ),
                  );
                }
              }
            }
          }

          controller.close();
          console.log("[Chat Proxy] Stream completed");
        } catch (error) {
          console.error("[Chat Proxy] Error:", error);
          controller.error(error);
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Vercel-AI-Data-Stream": "v1",
      },
    });
  } catch (error) {
    console.error("[Chat] Error:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        message: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}
