import { useState } from "react";
import { IconChevronDownOutlineRegular } from "@/components/icons/dsh";
import { useTranslation } from "react-i18next";
import { fmtDuration } from "./ToolGroup";
import css from "./TurnWork.module.css";

/**
 * A finished turn's work, folded behind one line.
 *
 * `Took 59m 3s ⌄` (DeepSeek Harness's turn-process line) — the ask and the answer stay, an hour of narration and
 * commands goes behind it, and a click brings it back. It is the fold Codex puts
 * between a question and its result, and the reason a long session reads as a
 * conversation instead of a log.
 *
 * Only finished work folds. While a turn runs, its narration and its activity
 * lines are the only sign of progress there is, so `TurnWork` renders them
 * plainly and adds no chrome at all — see `isTurnDone`.
 *
 * Manual expansion is per component instance, which outlives every re-render and
 * every Screen switch (inactive screens stay mounted). So a turn the reader
 * opened stays open for as long as they are looking at that conversation, and a
 * reload starts it folded again — which is the right default for work that is
 * already done.
 */
export function TurnWork({
  done,
  durationMs,
  children,
}: {
  done: boolean;
  durationMs: number | null;
  children: React.ReactNode;
}) {
  const { t } = useTranslation(["session", "common"]);
  const [open, setOpen] = useState(false);

  if (!done) return <>{children}</>;

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        data-open={open || undefined}
        className={css.root}
      >
        <span className={css.label}>
          {durationMs === null
            ? t("turn.worked")
            : t("turn.workedFor", { duration: fmtDuration(durationMs) })}
        </span>
        <IconChevronDownOutlineRegular className={css.chevron} />
      </button>
      {open && <div className="flex flex-col gap-4">{children}</div>}
    </div>
  );
}
