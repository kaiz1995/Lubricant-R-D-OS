import { create } from "zustand";
import type { FileRoot } from "@ai4s/shared";
import { isTauri, openExternal } from "@/lib/tauri";
import { openArtifactExternally, resolveArtifactPath } from "@/lib/artifactFile";
import { useLayoutStore } from "@/lib/layout";
import { isGatewayWeb } from "@/lib/webMode";

/**
 * Clickable URLs and local paths in conversations and terminals, as in Orca:
 * a link is underlined on hover, a click opens a small menu (the full target
 * and what can be done with it), ⌘-click takes the first action at once and
 * ⇧⌘-click opens a file in its default app.
 *
 * Only what can actually be opened is a link: a path is drawn as one after it
 * has been found on disk.
 */
export type LinkTarget =
  | { kind: "url"; url: string }
  /** `path` is relative to `root`; `display` is what the user clicked. */
  | { kind: "path"; path: string; root: FileRoot; isDir: boolean; display: string };

// CJK punctuation (\u3000-\u303f, \uff00-\uffef) ends a URL or a path: prose
// runs straight into them with no space.
const URL_RE = /\bhttps?:\/\/[^\s<>"'`)\]}\u3000-\u303f\uff00-\uffef]+/g;
/** A path-like token: absolute, `~/`, `./`, `../`, a relative path with a
 *  slash, or a bare name with an extension. Trailing `:line:col` and sentence
 *  punctuation are trimmed by `cleanPath`. */
const NAME = String.raw`[\w.@+\-\u00c0-\u2fff\u3040-\ufeff]`;
const PATH_RE = new RegExp(String.raw`(?:~|\.{1,2})?\/?${NAME}+(?:\/${NAME}*)*`, "g");

/** A URL, trimmed of the punctuation that closes the sentence around it. */
export function cleanUrl(raw: string): string {
  return raw.replace(/[.,;:!?]+$/, "");
}

/** A printed path without its `:12:3` position or trailing punctuation. */
export function cleanPath(raw: string): string {
  return raw.replace(/(?::\d+){1,2}$/, "").replace(/[.,;:!?]+$/, "");
}

/** Could `text` name a file? A slash, or a name with an extension — not every
 *  word of a line is worth a disk lookup. */
export function looksLikePath(text: string): boolean {
  if (text.length < 2 || /^\d+(\.\d+)*$/.test(text)) return false;
  return text.includes("/") || new RegExp(String.raw`^${NAME}+\.[A-Za-z]\w{0,7}$`).test(text);
}

export interface LinkSpan {
  start: number;
  end: number;
  text: string;
  kind: "url" | "path";
}

/** URL and path candidates in one line of text, left to right, not
 *  overlapping (a URL wins over the path-looking pieces inside it). */
export function linkCandidates(line: string): LinkSpan[] {
  const spans: LinkSpan[] = [];
  for (const m of line.matchAll(URL_RE)) {
    const text = cleanUrl(m[0]);
    spans.push({ start: m.index, end: m.index + text.length, text, kind: "url" });
  }
  const taken = (i: number) => spans.some((s) => i >= s.start && i < s.end);
  for (const m of line.matchAll(PATH_RE)) {
    if (taken(m.index)) continue;
    const text = cleanPath(m[0]);
    if (!looksLikePath(text)) continue;
    spans.push({ start: m.index, end: m.index + text.length, text, kind: "path" });
  }
  return spans.sort((a, b) => a.start - b.start);
}

interface LocalPath {
  rel: string;
  is_dir: boolean;
}

/** Lookups are cached: a terminal asks again every time the pointer crosses a
 *  line. A miss is remembered briefly only — the file may be written a moment
 *  later, and the next hover should find it. */
const cache = new Map<string, { at: number; value: Promise<LocalPath | null> }>();
const MISS_TTL_MS = 5_000;

function locateLocal(path: string, cwd?: string): Promise<LocalPath | null> {
  const key = `${cwd ?? ""}\n${path}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < MISS_TTL_MS) return hit.value;
  const value = (async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<LocalPath | null>("locate_local_path", { path, cwd });
  })().catch(() => null);
  cache.set(key, { at: Date.now(), value });
  void value.then((found) => {
    // Found things stay found.
    if (found) cache.set(key, { at: Number.POSITIVE_INFINITY, value });
  });
  return value;
}

/**
 * The link a clicked-at string stands for, or null when there is nothing to
 * open. Absolute and `~/` paths are looked up on disk under home. A relative
 * one is looked up against `from`: a terminal's directory (`{ cwd }`, null
 * while unknown — then only absolute paths link), or by default the session
 * workspace, the way file mentions in answers are.
 */
export async function resolveLink(
  text: string,
  from: { cwd: string | null } | "workspace" = "workspace",
): Promise<LinkTarget | null> {
  const url = cleanUrl(text);
  if (/^https?:\/\//.test(url)) return { kind: "url", url };
  // Local files exist only on the machine the app runs on.
  if (!isTauri || isGatewayWeb) return null;
  const path = cleanPath(text);
  if (!looksLikePath(path)) return null;
  const absolute = path.startsWith("/") || path.startsWith("~/") || /^[A-Za-z]:[\\/]/.test(path);
  const cwd = from === "workspace" ? undefined : (from.cwd ?? undefined);
  if (absolute || from !== "workspace") {
    if (!absolute && !cwd) return null;
    const found = await locateLocal(path, cwd);
    return found
      ? { kind: "path", path: found.rel, root: "home", isDir: found.is_dir, display: path }
      : null;
  }
  const inWorkspace = await resolveArtifactPath(path).catch(() => null);
  return inWorkspace
    ? { kind: "path", path: inWorkspace, root: "workspace", isDir: false, display: path }
    : null;
}

/** Open a file in its own Screen — a new tab showing its contents. */
export function openInApp(target: Extract<LinkTarget, { kind: "path" }>): void {
  const kind = target.path.toLowerCase().endsWith(".ipynb") ? "notebook" : "editor";
  useLayoutStore.getState().addGroup({ kind, path: target.path, root: target.root });
}

export function openWithDefaultApp(target: LinkTarget): void {
  if (target.kind === "url") void openExternal(target.url);
  else void openArtifactExternally(target.path, target.root);
}

/** What a click does, by modifier: ⌘ → the first action, ⇧⌘ → the default
 *  app, a plain click → the menu at the pointer. */
export function activateLink(
  target: LinkTarget,
  event: Pick<MouseEvent, "clientX" | "clientY" | "metaKey" | "ctrlKey" | "shiftKey">,
): void {
  const mod = event.metaKey || event.ctrlKey;
  if (mod && (event.shiftKey || target.kind === "url" || target.isDir)) {
    openWithDefaultApp(target);
  } else if (mod && target.kind === "path") {
    openInApp(target);
  } else {
    useLinkMenu.getState().show(target, event.clientX, event.clientY);
  }
}

interface LinkMenuState {
  open: { target: LinkTarget; x: number; y: number } | null;
  show: (target: LinkTarget, x: number, y: number) => void;
  hide: () => void;
}

export const useLinkMenu = create<LinkMenuState>((set) => ({
  open: null,
  show: (target, x, y) => set({ open: { target, x, y } }),
  hide: () => set({ open: null }),
}));
