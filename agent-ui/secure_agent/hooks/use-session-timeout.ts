"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, invalidateSessionOnServer } from "@/lib/auth";

const WARNING_LEAD_MINUTES = 2;

export function useSessionTimeout(timeoutMinutes: number | undefined) {
  const router = useRouter();
  const lastActivityRef = useRef(Date.now());
  const [showWarning, setShowWarning] = useState(false);

  const touch = useCallback(() => {
    lastActivityRef.current = Date.now();
    setShowWarning(false);
  }, []);

  useEffect(() => {
    if (!timeoutMinutes || timeoutMinutes <= 0) return;

    const timeoutMs = timeoutMinutes * 60 * 1000;
    const warningMs = Math.max(timeoutMs - WARNING_LEAD_MINUTES * 60 * 1000, 0);

    const onActivity = () => touch();
    const events = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;
    events.forEach((event) => window.addEventListener(event, onActivity, { passive: true }));

    const interval = window.setInterval(async () => {
      const idleMs = Date.now() - lastActivityRef.current;
      if (idleMs >= timeoutMs) {
        await invalidateSessionOnServer();
        clearTokens();
        router.push("/login?reason=session_expired");
        return;
      }
      if (warningMs > 0 && idleMs >= warningMs) {
        setShowWarning(true);
      }
    }, 30_000);

    return () => {
      events.forEach((event) => window.removeEventListener(event, onActivity));
      window.clearInterval(interval);
    };
  }, [timeoutMinutes, router, touch]);

  return { showWarning, touch, warningMinutes: WARNING_LEAD_MINUTES };
}
