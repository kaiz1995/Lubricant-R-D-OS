import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Command, defaultFilter } from "cmdk";
import { useNavigate } from "react-router-dom";
import { Folder, LayoutGrid, MessageSquare, Plus, Terminal as TerminalIcon } from "lucide-react";
import { DEFAULT_PROJECT, selectActiveProjectId, useLayoutStore } from "@/lib/layout";
import { draftKeyFor, useRuntimeStore } from "@/lib/runtime";
import { jumpEntries, type JumpEntry, type JumpSection } from "@/lib/jumpEntries";
import { useIsMobile } from "@/lib/useIsMobile";
import { isGatewayWeb } from "@/lib/webMode";

const isMac = typeof navigator !== "undefined" && navigator.userAgent.includes("Mac");

/** ⌘J on macOS; Ctrl+Shift+J elsewhere, as in Orca — a bare Ctrl+J is a line
 *  feed, which a terminal must keep receiving. Exported so the terminal can
 *  leave the chord to the app. */
export function isJumpChord(e: KeyboardEvent): boolean {
  if (e.key.toLowerCase() !== "j" || e.altKey) return false;
  return isMac ? e.metaKey && !e.ctrlKey && !e.shiftKey : e.ctrlKey && e.shiftKey && !e.metaKey;
}

const SECTIONS: JumpSection[] = ["actions", "projects", "screens", "panes", "sessions"];

/** Match on what the row SAYS — its label and where it lives — not on its
 *  value, which is an internal id ("pane:p12") that would match anything. */
const matchShown = (_value: string, search: string, keywords?: string[]) =>
  defaultFilter((keywords ?? []).join(" "), search);

/**
 * ⌘J: jump to any project, Screen, open pane or session by typing its name —
 * Orca's worktree jump palette (MIT), in this app's Project → Screens → panes
 * shape. ⌘K stays the command palette; this one is about WHERE to go.
 */
export function JumpPalette() {
  const { t } = useTranslation(["nav", "session"]);
  const navigate = useNavigate();
  const [open, setOpenState] = useState(false);
  // Read synchronously by the key handler: whether Esc is ours has to be known
  // while the event is still being dispatched, or it also reaches the session
  // page and interrupts a running turn.
  const openRef = useRef(false);
  const setOpen = (next: boolean) => {
    openRef.current = next;
    setOpenState(next);
  };
  // Screens are a desktop surface; web and phone show a single pane.
  const enabled = !useIsMobile() && !isGatewayWeb;

  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (isJumpChord(e)) {
        e.preventDefault();
        setOpen(!openRef.current);
      } else if (e.key === "Escape" && openRef.current) {
        // Consume Esc only while open, so it does not also interrupt a turn.
        e.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);

  const groups = useLayoutStore((s) => s.groups);
  const activeGroupId = useLayoutStore((s) => s.activeGroupId);
  const sessions = useRuntimeStore((s) => s.sessions);
  const projects = useRuntimeStore((s) => s.projects);

  const entries = useMemo(
    () =>
      open
        ? jumpEntries({
            groups,
            activeGroupId,
            sessions,
            projects,
            labels: {
              defaultProject: t("session:group.defaultProject"),
              terminal: t("session:terminal.title"),
              files: t("nav:items.files"),
              session: t("nav:jump.sections.sessions"),
              screen: (n) => t("session:group.defaultName", { n }),
              newSession: (project) => t("nav:jump.actions.newSession", { project }),
              newTerminal: (project) => t("nav:jump.actions.newTerminal", { project }),
              newScreen: (project) => t("nav:jump.actions.newScreen", { project }),
            },
          })
        : [],
    [open, groups, activeGroupId, sessions, projects, t],
  );

  if (!open) return null;
  const close = () => setOpen(false);

  const run = async (entry: JumpEntry) => {
    close();
    const layout = useLayoutStore.getState();
    const target = entry.target;
    switch (target.kind) {
      case "project":
        layout.setActiveProject(target.projectId);
        navigate("/live");
        return;
      case "screen":
        layout.setActiveGroup(target.groupId);
        navigate("/live");
        return;
      case "pane":
        layout.setActiveGroup(target.groupId);
        layout.focusLeaf(target.leafId);
        navigate(target.sessionId ? `/live/${target.sessionId}` : "/live");
        return;
      case "session":
        layout.openSessionEphemeral(target.sessionId, target.projectId);
        navigate(`/live/${target.sessionId}`);
        return;
      case "action": {
        const runtime = useRuntimeStore.getState();
        const projectId = selectActiveProjectId(layout);
        const project = runtime.projects.find((p) => p.id === projectId);
        const path = project?.path ?? runtime.workspace ?? undefined;
        if (target.action === "newScreen") layout.addGroup();
        // eslint-disable-next-line i18next/no-literal-string -- PaneContent kind, not UI copy
        else if (target.action === "newTerminal") layout.addGroup({ kind: "terminal", cwd: path });
        else if (projectId !== DEFAULT_PROJECT && project) {
          // A new session IN the project: its draft is aimed at the project's
          // folder, the same as the sidebar's "+" on a project.
          const leafId = layout.openInNewGroup(null, project.id);
          await runtime.startDraftInWorkspace(project.path, draftKeyFor(leafId));
        } else {
          layout.openInNewGroup(null);
          runtime.startDraft();
        }
        navigate("/live");
        return;
      }
    }
  };

  const icon = (entry: JumpEntry) => {
    switch (entry.target.kind) {
      case "action":
        return <Plus size={15} />;
      case "project":
        return <Folder size={15} />;
      case "screen":
        return <LayoutGrid size={15} />;
      case "pane":
        return entry.target.sessionId ? <MessageSquare size={15} /> : <TerminalIcon size={15} />;
      case "session":
        return <MessageSquare size={15} />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/20 pt-[14vh]" onClick={close}>
      {/* A dialog, so an Esc a running turn would take for an interrupt is
          recognised as the palette's whichever listener runs first. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("nav:jump.ariaLabel")}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl"
      >
        <Command label={t("nav:jump.ariaLabel")} filter={matchShown} className="overflow-hidden rounded-card border border-border bg-surface shadow-pop">
          <Command.Input
            autoFocus
            placeholder={t("nav:jump.placeholder")}
            className="w-full border-b border-border bg-transparent px-4 py-3 text-sm text-text outline-none placeholder:text-muted"
          />
          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="px-3 py-6 text-center text-sm text-muted">{t("nav:jump.noResults")}</Command.Empty>
            {SECTIONS.map((section) => {
              const rows = entries.filter((e) => e.section === section);
              if (rows.length === 0) return null;
              return (
                <Command.Group
                  key={section}
                  heading={t(`nav:jump.sections.${section}`)}
                  className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-muted"
                >
                  {rows.map((entry) => (
                    <Command.Item
                      key={entry.id}
                      value={entry.id}
                      keywords={[entry.label, entry.detail ?? ""]}
                      onSelect={() => void run(entry)}
                      className="flex cursor-pointer items-center gap-3 rounded-input px-3 py-2 text-sm text-text data-[selected=true]:bg-surface-2"
                    >
                      <span className="shrink-0 text-muted">{icon(entry)}</span>
                      <span className="min-w-0 flex-1 truncate">{entry.label}</span>
                      {entry.detail && <span className="max-w-[45%] shrink-0 truncate text-xs text-muted">{entry.detail}</span>}
                    </Command.Item>
                  ))}
                </Command.Group>
              );
            })}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
