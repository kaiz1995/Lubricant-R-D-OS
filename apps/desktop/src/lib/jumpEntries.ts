// What ⌘J can jump to — Orca's worktree jump palette (MIT), in this app's
// shape: Project → Screens → panes.
//
// One list, searched as you type: the active project's quick actions, every
// project, every Screen, every open pane (conversations and terminals), and
// the sessions that are not open anywhere. Built here, pure, so what the
// palette offers is testable without rendering it.
import {
  DEFAULT_PROJECT,
  leaves,
  projectGroups,
  projectOf,
  selectActiveProjectId,
  type LayoutGroup,
  type PaneLeaf,
} from "./layout";
import { projectIdForSession } from "./projectScope";

export type JumpSection = "actions" | "projects" | "screens" | "panes" | "sessions";

export type JumpTarget =
  | { kind: "action"; action: "newSession" | "newTerminal" | "newScreen" }
  | { kind: "project"; projectId: string }
  | { kind: "screen"; groupId: string }
  | { kind: "pane"; groupId: string; leafId: string; sessionId: string | null }
  | { kind: "session"; sessionId: string; projectId: string };

export interface JumpEntry {
  /** Unique across the list; also what the palette matches against. */
  id: string;
  section: JumpSection;
  label: string;
  /** Where it lives, e.g. "Project · Screen 2". */
  detail?: string;
  target: JumpTarget;
}

export interface JumpInput {
  groups: LayoutGroup[];
  activeGroupId: string;
  sessions: { id: string; title: string; directory?: string | null; parentId?: string | null; updated?: number }[];
  projects: { id: string; name: string; path: string }[];
  labels: {
    defaultProject: string;
    terminal: string;
    files: string;
    session: string;
    screen: (n: number) => string;
    newSession: (project: string) => string;
    newTerminal: (project: string) => string;
    newScreen: (project: string) => string;
  };
}

/** Sessions not open anywhere, most recent first — enough to reach recent
 *  work by name; the rest is on the History page. */
const SESSION_LIMIT = 100;

const basename = (path: string): string => path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || path;

export function jumpEntries(input: JumpInput): JumpEntry[] {
  const { groups, sessions, projects, labels } = input;
  const projectName = (id: string) =>
    id === DEFAULT_PROJECT ? labels.defaultProject : (projects.find((p) => p.id === id)?.name ?? labels.defaultProject);
  const activeProject = selectActiveProjectId(input);
  const activeName = projectName(activeProject);
  const titleOf = (sessionId: string) => sessions.find((s) => s.id === sessionId)?.title || labels.session;

  const paneLabel = (leaf: PaneLeaf): string => {
    const c = leaf.content;
    if (!c) return leaf.artifact?.filename ?? (leaf.sessionId ? titleOf(leaf.sessionId) : labels.session);
    switch (c.kind) {
      case "terminal": {
        const where = c.cwd ? ` · ${basename(c.cwd)}` : "";
        const agent = c.agent?.running ? ` · ${c.agent.kind === "claude" ? "Claude Code" : "Codex"}` : "";
        return `${c.name || labels.terminal}${where}${agent}`;
      }
      case "files":
        return labels.files;
      case "notebook":
      case "editor":
        return basename(c.path);
    }
  };

  const screenLabel = (g: LayoutGroup): string => {
    const named = g.name.trim();
    if (named) return named;
    const first = g.tree ? leaves(g.tree)[0] : undefined;
    if (first) return paneLabel(first);
    const n = projectGroups(groups, projectOf(g)).findIndex((x) => x.id === g.id) + 1;
    return labels.screen(n);
  };

  const entries: JumpEntry[] = [
    { id: "action:newSession", section: "actions", label: labels.newSession(activeName), target: { kind: "action", action: "newSession" } },
    { id: "action:newTerminal", section: "actions", label: labels.newTerminal(activeName), target: { kind: "action", action: "newTerminal" } },
    { id: "action:newScreen", section: "actions", label: labels.newScreen(activeName), target: { kind: "action", action: "newScreen" } },
  ];

  entries.push({
    id: "project:default",
    section: "projects",
    label: labels.defaultProject,
    target: { kind: "project", projectId: DEFAULT_PROJECT },
  });
  for (const p of [...projects].sort((a, b) => a.name.localeCompare(b.name))) {
    entries.push({ id: `project:${p.id}`, section: "projects", label: p.name, detail: p.path, target: { kind: "project", projectId: p.id } });
  }

  // The active project's Screens first: they are the likeliest destination.
  const ordered = [
    ...groups.filter((g) => projectOf(g) === activeProject),
    ...groups.filter((g) => projectOf(g) !== activeProject),
  ];
  const open = new Set<string>();
  for (const g of ordered) {
    const where = projectName(projectOf(g));
    const screen = screenLabel(g);
    entries.push({ id: `screen:${g.id}`, section: "screens", label: screen, detail: where, target: { kind: "screen", groupId: g.id } });
    if (!g.tree) continue;
    for (const leaf of leaves(g.tree)) {
      if (leaf.sessionId && !leaf.content) open.add(leaf.sessionId);
      entries.push({
        id: `pane:${leaf.id}`,
        section: "panes",
        label: paneLabel(leaf),
        detail: `${where} · ${screen}`,
        target: { kind: "pane", groupId: g.id, leafId: leaf.id, sessionId: leaf.content ? null : leaf.sessionId },
      });
    }
  }

  const closed = sessions
    .filter((s) => !s.parentId && !open.has(s.id))
    .sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0))
    .slice(0, SESSION_LIMIT);
  for (const s of closed) {
    const projectId = projectIdForSession(s.id, sessions, projects);
    const name = projectName(projectId);
    entries.push({
      id: `session:${s.id}`,
      section: "sessions",
      label: s.title || labels.session,
      detail: name,
      target: { kind: "session", sessionId: s.id, projectId },
    });
  }
  return entries;
}
