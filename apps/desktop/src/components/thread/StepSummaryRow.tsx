import { memo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { StepSummaryBlock } from "@ai4s/shared";
import {
  IconChevronDownOutlineRegular,
  IconChevronUpOutlineRegular,
  IconSparkleRegular,
} from "@/components/icons/dsh";
import css from "./ToolGroup.module.css";

/** A run of steps summarised in one line — drawn as DeepSeek Harness's
 *  process row (see ToolGroup.module.css): icon slot that gives way to the
 *  chevron, secondary text, the step count trailing. */
export const StepSummaryRow = memo(function StepSummaryRow({ block }: { block: StepSummaryBlock }) {
  const { t } = useTranslation(["session", "common"]);
  const [open, setOpen] = useState(false);
  const hasDetails = (block.details?.length ?? 0) > 0;
  return (
    <div>
      <button
        type="button"
        className={css.title}
        onClick={() => hasDetails && setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className={css.leading} aria-hidden="true">
          <span className={css.activityIcon}>
            <IconSparkleRegular size={14} />
          </span>
          <span className={css.chevron}>
            {open ? <IconChevronUpOutlineRegular /> : <IconChevronDownOutlineRegular />}
          </span>
        </span>
        <span className={css.label}>{block.summary}</span>
        <span className="ml-auto shrink-0 text-xs text-muted">{t("stepSummary.steps", { count: block.steps })}</span>
      </button>
      {open && hasDetails && (
        <ul className="space-y-1 pl-[22px] text-sm text-muted">
          {block.details!.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
});
