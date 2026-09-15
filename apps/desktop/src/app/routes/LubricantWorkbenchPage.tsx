/* eslint-disable i18next/no-literal-string */
import { useEffect } from "react";
import { useRuntimeStore } from "@/lib/runtime";
import { LiveSessionPage } from "./LiveSessionPage";

/**
 * Lubricant R&D Copilot Surface.
 * Keeps left pane (Sidebar) and middle pane (Live conversation & composer) 100%
 * identical to native Open Science, and auto-opens the dedicated LubricantStagePane
 * on the right side.
 */
export function LubricantWorkbenchPage() {
  const setShowLubricant = useRuntimeStore((s) => s.setShowLubricant);

  useEffect(() => {
    // Open the Lubricant stage pane automatically when entering this route
    setShowLubricant(true);
  }, [setShowLubricant]);

  return <LiveSessionPage />;
}

