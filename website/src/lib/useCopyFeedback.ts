import { useCallback, useEffect, useRef, useState } from "react";

import { copyText } from "./clipboard";

export type CopyState = "idle" | "copied" | "failed";

const COPY_SUCCESS_RESET_MS = 1400;
const COPY_FAILURE_RESET_MS = 1800;

export function useCopyFeedback({
  resetDelay = COPY_SUCCESS_RESET_MS,
  failureResetDelay = COPY_FAILURE_RESET_MS,
}: {
  resetDelay?: number;
  failureResetDelay?: number;
} = {}) {
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const resetTimerRef = useRef<number | null>(null);

  const clearResetTimer = useCallback(() => {
    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current);
      resetTimerRef.current = null;
    }
  }, []);

  useEffect(() => clearResetTimer, [clearResetTimer]);

  const scheduleReset = useCallback(
    (delay: number) => {
      clearResetTimer();
      resetTimerRef.current = window.setTimeout(() => {
        setCopyState("idle");
        resetTimerRef.current = null;
      }, delay);
    },
    [clearResetTimer],
  );

  const copy = useCallback(
    async (text: string) => {
      clearResetTimer();
      try {
        await copyText(text);
        setCopyState("copied");
        scheduleReset(resetDelay);
      } catch {
        setCopyState("failed");
        scheduleReset(failureResetDelay);
      }
    },
    [clearResetTimer, failureResetDelay, resetDelay, scheduleReset],
  );

  return { copy, copyState };
}
