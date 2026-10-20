import { describe, it, expect } from "vitest";
import { jumpEntries, type JumpInput } from "./jumpEntries";
import { projectIdForGroup, projectIdForPath, projectIdForSession } from "./projectScope";
import type { LayoutGroup, PaneNode } from "./layout";

const projects = [
  { id: "P", name: "Protein", path: "/w/protein" },
  { id: "N", name: "Nested", path: "/w/protein/sub" },
];
const sessions = [
  { id: "s1", title: "Fold the thing", directory: "/w/protein", updated: 3 },
  { id: "s2", title: "Loose chat", directory: "/tmp/elsewhere", updated: 2 },
  { id: "s3", title: "Old work", directory: "/w/protein", updated: 1 },
  { id: "child", title: "subagent", directory: "/w/protein", parentId: "s1", updated: 9 },
];
const leaf = (id: string, sessionId: string | null, content?: object): PaneNode =>
  ({ kind: "leaf", id, sessionId, ...(content ? { content } : {}) }) as PaneNode;
const group = (id: string, projectId: string, tree: PaneNode | null, name = ""): LayoutGroup => ({
  id,
  name,
  projectId,
  tree,
  focusedLeafId: null,
  zoomedLeafId: null,
});

describe("which project something belongs to", () => {
  it("a folder belongs to the project that is it or contains it, deepest first", () => {
    expect(projectIdForPath("/w/protein", projects)).toBe("P");
    expect(projectIdForPath("/w/protein/data", projects)).toBe("P");
    expect(projectIdForPath("/w/protein/sub/x", projects)).toBe("N");
    // A sibling whose name merely starts the same is not inside.
    expect(projectIdForPath("/w/protein-old", projects)).toBe("");
    expect(projectIdForPath(null, projects)).toBe("");
  });

  it("a session belongs to exactly its folder's project, as the sidebar files it", () => {
    expect(projectIdForSession("s1", sessions, projects)).toBe("P");
    expect(projectIdForSession("s2", sessions, projects)).toBe("");
    expect(projectIdForSession("missing", sessions, projects)).toBe("");
  });

  it("a Screen goes where its conversation is, else where its terminal is working", () => {
    expect(projectIdForGroup(group("g", "", leaf("a", "s1")), sessions, projects)).toBe("P");
    const term = leaf("t", null, { kind: "terminal", cwd: "/w/protein/sub" });
    expect(projectIdForGroup(group("g", "", term), sessions, projects)).toBe("N");
    expect(projectIdForGroup(group("g", "", leaf("a", "s2")), sessions, projects)).toBe("");
    expect(projectIdForGroup(group("g", "", null), sessions, projects)).toBe("");
  });
});

describe("what ⌘J offers", () => {
  const labels: JumpInput["labels"] = {
    defaultProject: "Default",
    terminal: "Terminal",
    files: "Files",
    session: "Session",
    screen: (n) => `Screen ${n}`,
    newSession: (p) => `New session in ${p}`,
    newTerminal: (p) => `New terminal in ${p}`,
    newScreen: (p) => `New screen in ${p}`,
  };
  const groups = [
    group("d1", "", leaf("a", "s2")),
    group("p1", "P", leaf("t", null, { kind: "terminal", cwd: "/w/protein", name: "build", agent: { kind: "claude", sessionId: "x", running: true } })),
    group("p2", "P", leaf("b", "s1"), "Folding"),
  ];
  const entries = jumpEntries({ groups, activeGroupId: "p2", sessions, projects, labels });
  const bySection = (section: string) => entries.filter((e) => e.section === section);

  it("its actions act on the active project", () => {
    expect(bySection("actions").map((e) => e.label)).toEqual([
      "New session in Protein",
      "New terminal in Protein",
      "New screen in Protein",
    ]);
  });

  it("lists Default and every project", () => {
    expect(bySection("projects").map((e) => e.label)).toEqual(["Default", "Nested", "Protein"]);
  });

  it("lists the active project's Screens first, each saying where it lives", () => {
    expect(bySection("screens").map((e) => [e.label, e.detail])).toEqual([
      ["build · protein · Claude Code", "Protein"],
      ["Folding", "Protein"],
      ["Loose chat", "Default"],
    ]);
  });

  it("finds a terminal by what is running in it", () => {
    const term = bySection("panes").find((e) => e.target.kind === "pane" && e.target.leafId === "t");
    expect(term?.label).toContain("Claude Code");
    expect(term?.target).toMatchObject({ groupId: "p1", sessionId: null });
  });

  it("offers the sessions not open anywhere, newest first, without subagents", () => {
    expect(bySection("sessions").map((e) => [e.label, e.detail])).toEqual([["Old work", "Protein"]]);
  });
});
