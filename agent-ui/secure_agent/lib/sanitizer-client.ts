/**
 * Client for communicating with the Python sanitization backend
 */

export interface SanitizeRequest {
  prompt: string;
  security_level?: "low" | "medium" | "high";
  return_details?: boolean;
}

export interface SanitizeResponse {
  is_safe: boolean;
  sanitized_prompt: string;
  original_prompt: string;
  warnings: string[];
  blocked_patterns: string[];
  confidence: number;
  modifications_made: boolean;
  sanitization_details?: {
    // classifications: any;
    classifications: Record<string, unknown>;
    sanitization_applied: Record<string, string[]>;
  };
  processing_time_ms: number;
}

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  uptime_seconds: number;
  version: string;
}

export interface StatsResponse {
  security_level: string;
  model_info: {
    model_name: string;
    model_type: string;
    device: string;
    spacy_model: string;
  };
  request_stats: {
    total_requests: number;
    average_latency_ms: number;
    total_processing_time_ms: number;
    uptime_seconds: number;
  };
  capabilities: string[];
}

class SanitizerClient {
  private baseUrl: string;
  private timeout: number;
  private enabled: boolean;

  constructor() {
    this.baseUrl =
      process.env.NEXT_PUBLIC_SANITIZER_API_URL || "http://localhost:8003";
    this.timeout = parseInt(
      process.env.NEXT_PUBLIC_SANITIZER_TIMEOUT_MS || "5000",
    );
    this.enabled = process.env.NEXT_PUBLIC_SANITIZER_ENABLED !== "false";
  }

  /**
   * Sanitize a single prompt
   */
  async sanitizePrompt(
    prompt: string,
    securityLevel?: "low" | "medium" | "high",
    returnDetails: boolean = false,
  ): Promise<SanitizeResponse> {
    if (!this.enabled) {
      // If sanitization is disabled, return the prompt as-is
      return {
        is_safe: true,
        sanitized_prompt: prompt,
        original_prompt: prompt,
        warnings: [],
        blocked_patterns: [],
        confidence: 1.0,
        modifications_made: false,
        processing_time_ms: 0,
      };
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeout);

      const response = await fetch(`${this.baseUrl}/api/sanitize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt,
          security_level: securityLevel,
          return_details: returnDetails,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(
          error.detail || `Sanitization failed: ${response.statusText}`,
        );
      }

      return await response.json();
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          console.error("Sanitization request timed out");
          throw new Error("Sanitization service timeout");
        }
        console.error("Sanitization error:", error.message);
        throw error;
      }
      throw new Error("Unknown sanitization error");
    }
  }

  /**
   * Sanitize multiple prompts in batch
   */
  async sanitizeBatch(
    prompts: string[],
    securityLevel?: "low" | "medium" | "high",
    returnDetails: boolean = false,
  ): Promise<{
    results: SanitizeResponse[];
    total_processed: number;
    total_time_ms: number;
  }> {
    if (!this.enabled) {
      return {
        results: prompts.map((prompt) => ({
          is_safe: true,
          sanitized_prompt: prompt,
          original_prompt: prompt,
          warnings: [],
          blocked_patterns: [],
          confidence: 1.0,
          modifications_made: false,
          processing_time_ms: 0,
        })),
        total_processed: prompts.length,
        total_time_ms: 0,
      };
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout * 2);

    try {
      const response = await fetch(`${this.baseUrl}/api/sanitize/batch`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompts,
          security_level: securityLevel,
          return_details: returnDetails,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Batch sanitization failed: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Batch sanitization error:", error);
      throw error;
    }
  }

  /**
   * Check health of sanitization service
   */
  async checkHealth(): Promise<HealthResponse> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      const response = await fetch(`${this.baseUrl}/api/health`, {
        method: "GET",
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error("Health check failed");
      }

      return await response.json();
    } catch (error) {
      console.error("Health check error:", error);
      throw error;
    }
  }

  /**
   * Get statistics from sanitization service
   */
  async getStats(): Promise<StatsResponse> {
    const response = await fetch(`${this.baseUrl}/api/stats`, {
      method: "GET",
    });

    if (!response.ok) {
      throw new Error("Failed to fetch stats");
    }

    return await response.json();
  }

  /**
   * Get current security level
   */
  async getSecurityLevel(): Promise<string> {
    const response = await fetch(`${this.baseUrl}/api/security/level`, {
      method: "GET",
    });

    if (!response.ok) {
      throw new Error("Failed to get security level");
    }

    const data = await response.json();
    return data.level;
  }

  /**
   * Update security level
   */
  async updateSecurityLevel(level: "low" | "medium" | "high"): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/security/level`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ level }),
    });

    if (!response.ok) {
      throw new Error("Failed to update security level");
    }
  }

  /**
   * Check if sanitization is enabled
   */
  isEnabled(): boolean {
    return this.enabled;
  }
}

// Export singleton instance
export const sanitizerClient = new SanitizerClient();
