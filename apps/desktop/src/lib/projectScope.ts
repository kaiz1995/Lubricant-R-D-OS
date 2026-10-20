// Which project a session, a folder or a Screen belongs to.
//
// The runtime files sessions under a project by folder (a session's
// `directory` IS the project's path); the layout files Screens under a
// project by id. These are the few rules that connect the two. They take the
// lists as arguments, so they are testable without either store; only
// `sessionProject` reads the live runtime.
import { DEFAULT_PROJECT, leaves, type LayoutGroup } from "./layout";
import { pathKey } from "./workspacePath";
import { useRuntimeStore } from "./runtime";

interface ProjectRef {
  id: string;
  path: string;
}

interface SessionRef {
  id: string;
  directory?: string | null;
}

/** The project whose folder is `dir`, or contains it — a terminal that `cd`ed
 *  into a subfolder is still working in that project. The deepest match wins,
 *  for a project nested inside another. */
export function projectIdForPath(dir: string | null | undefined, projects: ProjectRef[]): string {
  if (!dir) return DEFAULT_PROJECT;
  const key = pathKey(dir);
  let best: { id: string; depth: number } | null = null;
  for (const p of projects) {
    const base = pathKey(p.path);
    if (key !== base && !key.startsWith(base.endsWith("/") ? base : `${base}/`)) continue;
    if (!best || base.length > best.depth) best = { id: p.id, depth: base.length };
  }
  return best?.id ?? DEFAULT_PROJECT;
}

/** The project a session is filed under: exactly its folder, as the sidebar
 *  files it. */
export function projectIdForSession(
  sessionId: string,
  sessions: SessionRef[],
  projects: ProjectRef[],
): string {
  const dir = sessions.find((s) => s.id === sessionId)?.directory;
  if (!dir) return DEFAULT_PROJECT;
  const key = pathKey(dir);
  return projects.find((p) => pathKey(p.path) === key)?.id ?? DEFAULT_PROJECT;
}

/** Where a Screen belongs, judged by what it holds: its first conversation's
 *  project, else the first folder one of its surfaces is working in. */
export function projectIdForGroup(
  group: LayoutGroup,
  sessions: SessionRef[],
  projects: ProjectRef[],
): string {
  if (!group.tree) return DEFAULT_PROJECT;
  const all = leaves(group.tree);
  for (const leaf of all) {
    if (leaf.content || !leaf.sessionId) continue;
    const id = projectIdForSession(leaf.sessionId, sessions, projects);
    if (id !== DEFAULT_PROJECT) return id;
  }
  for (const leaf of all) {
    const c = leaf.content;
    const dir = c?.kind === "terminal" ? c.cwd : c?.kind === "files" ? c.path : undefined;
    const id = projectIdForPath(dir, projects);
    if (id !== DEFAULT_PROJECT) return id;
  }
  return DEFAULT_PROJECT;
}

/** `projectIdForSession` against the live runtime store. */
export function sessionProject(sessionId: string): string {
  const { sessions, projects } = useRuntimeStore.getState();
  return projectIdForSession(sessionId, sessions, projects);
}
