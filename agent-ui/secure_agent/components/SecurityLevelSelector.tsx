"use client";

import { useState, useEffect } from "react";
import { sanitizerClient } from "@/lib/sanitizer-client";
import { Shield, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

export default function SecurityLevelSelector() {
  const [level, setLevel] = useState<"low" | "medium" | "high">("medium");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    // Load current level on mount
    loadCurrentLevel();
  }, []);

  const loadCurrentLevel = async () => {
    try {
      const currentLevel = await sanitizerClient.getSecurityLevel();
      setLevel(currentLevel as "low" | "medium" | "high");
    } catch (err) {
      console.error("Failed to load security level:", err);
      setError("Could not load current security level");
    }
  };

  const handleChange = async (newLevel: "low" | "medium" | "high") => {
    if (newLevel === level) return;

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      await sanitizerClient.updateSecurityLevel(newLevel);
      setLevel(newLevel);
      setSuccess(true);

      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(false), 3000);

      console.log("✅ Security level updated to:", newLevel);
    } catch (err) {
      console.error("Failed to update security level:", err);
      setError("Failed to update security level. Is the backend running?");
      // Revert to previous level
      await loadCurrentLevel();
    } finally {
      setLoading(false);
    }
  };

  const getLevelInfo = (lvl: "low" | "medium" | "high") => {
    const info = {
      low: {
        icon: "🟢",
        color: "text-green-600 dark:text-green-400",
        bg: "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800",
        title: "Low",
        subtitle: "Development/Testing",
        description:
          "Warns but never blocks. Higher thresholds, fewer false positives.",
      },
      medium: {
        icon: "🟡",
        color: "text-yellow-600 dark:text-yellow-400",
        bg: "bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800",
        title: "Medium",
        subtitle: "Production Default",
        description:
          "Balanced protection. Blocks high-confidence threats (0.8+).",
      },
      high: {
        icon: "🔴",
        color: "text-red-600 dark:text-red-400",
        bg: "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800",
        title: "High",
        subtitle: "Maximum Security",
        description:
          "Aggressive detection. Blocks medium+ confidence threats (0.6+).",
      },
    };
    return info[lvl];
  };

  const currentInfo = getLevelInfo(level);

  return (
    <div className="security-level-selector space-y-4">
      {/* Current Status */}
      <div className={`rounded-lg border-2 p-4 ${currentInfo.bg}`}>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className={`h-5 w-5 ${currentInfo.color}`} />
            <h3 className={`font-semibold ${currentInfo.color}`}>
              Current Level: {currentInfo.icon} {currentInfo.title}
            </h3>
          </div>
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        </div>
        <p className="text-sm text-muted-foreground">
          {currentInfo.description}
        </p>
      </div>

      {/* Level Options */}
      <div className="space-y-3">
        <label className="text-sm font-medium text-foreground">
          Select Security Level
        </label>

        {(["low", "medium", "high"] as const).map((lvl) => {
          const info = getLevelInfo(lvl);
          const isActive = level === lvl;

          return (
            <button
              key={lvl}
              onClick={() => handleChange(lvl)}
              disabled={loading || isActive}
              className={`w-full rounded-lg border-2 p-4 text-left transition-all ${
                isActive
                  ? `${info.bg} cursor-default`
                  : "border-border hover:border-primary/50 hover:bg-accent"
              } ${loading && !isActive ? "cursor-not-allowed opacity-50" : "cursor-pointer"} `}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-xl">{info.icon}</span>
                    <h4
                      className={`font-semibold ${isActive ? info.color : "text-foreground"}`}
                    >
                      {info.title}
                    </h4>
                    <span className="text-xs text-muted-foreground">
                      {info.subtitle}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {info.description}
                  </p>
                </div>
                {isActive && (
                  <CheckCircle2
                    className={`h-5 w-5 ${info.color} ml-2 flex-shrink-0`}
                  />
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Status Messages */}
      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-600 dark:border-green-800 dark:bg-green-950/30 dark:text-green-400">
          <CheckCircle2 className="h-4 w-4" />
          <span>Security level updated successfully!</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-600 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
          <AlertCircle className="h-4 w-4" />
          <span>{error}</span>
        </div>
      )}

      {/* Info */}
      <div className="rounded-lg border border-border bg-muted/50 p-3">
        <p className="text-xs text-muted-foreground">
          <strong>Note:</strong> Changes apply immediately to all new prompts.
          Restart is not required.
        </p>
      </div>
    </div>
  );
}
