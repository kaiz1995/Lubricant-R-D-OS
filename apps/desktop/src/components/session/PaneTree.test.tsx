import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { insertLeaf, leaves, makeLeaf, useLayoutStore } from "@/lib/layout";
import { PaneTree } from "./PaneTree";

vi.mock("./SessionView", () => ({
  SessionView: ({ onClose, zoom }: { onClose?: () => void; zoom: number }) => (
    <button onClick={onClose} disabled={!onClose} data-zoom={zoom}>
      Request close
    </button>
  ),
}));

/** A pane bound to a session; the fixture below tiles two of them. */
const boundPanes = () => {
  const first = makeLeaf("session-a");
  return insertLeaf(first, first.id, "right", makeLeaf("session-b"));
};

/** What LiveSessionPage renders: every screen mounted, the active one shown. */
function Screens() {
  const groups = useLayoutStore((s) => s.groups);
  const activeGroupId = useLayoutStore((s) => s.activeGroupId);
  return (
    <>
      {groups.map((g) => (
        <div key={g.id} hidden={g.id !== activeGroupId}>
          <PaneTree group={g} active={g.id === activeGroupId} laidOut />
        </div>
      ))}
    </>
  );
}

describe("PaneTree panel close", () => {
  beforeEach(() => {
    const tree = boundPanes();
    const first = leaves(tree)[0];
    useLayoutStore.setState({
      groups: [{ id: "screen-a", name: "", tree, focusedLeafId: first.id, zoomedLeafId: null }],
      activeGroupId: "screen-a",
      tree,
      focusedLeafId: first.id,
      zoomedLeafId: null,
      ephemeralGroupId: null,
    });
  });

  it("keeps a Session panel until the user confirms", async () => {
    render(<Screens />);
    await userEvent.click(screen.getAllByRole("button", { name: "Request close" })[0]);
    expect(screen.getByRole("alertdialog", { name: "Close this panel?" })).toBeInTheDocument();
    expect(leaves(useLayoutStore.getState().tree!)).toHaveLength(2);

    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(leaves(useLayoutStore.getState().tree!)).toHaveLength(1);
  });

  // A split nobody used holds nothing: no session, no unsent line. Asking about
  // it is the same friction the Screen close just lost.
  it("closes an empty split pane on the click", async () => {
    const first = makeLeaf("session-a");
    const withDraft = insertLeaf(first, first.id, "right", makeLeaf(null));
    useLayoutStore.setState({
      groups: [{ id: "screen-a", name: "", tree: withDraft, focusedLeafId: first.id, zoomedLeafId: null }],
      tree: withDraft,
      focusedLeafId: first.id,
    });
    render(<Screens />);

    // The second pane is the unbound one.
    await userEvent.click(screen.getAllByRole("button", { name: "Request close" })[1]);

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(leaves(useLayoutStore.getState().tree!)).toHaveLength(1);
  });
});

describe("PaneTree default zoom", () => {
  const show = (tree: ReturnType<typeof makeLeaf> | ReturnType<typeof insertLeaf>) => {
    const first = leaves(tree)[0];
    useLayoutStore.setState({
      groups: [{ id: "screen-a", name: "", tree, focusedLeafId: first.id, zoomedLeafId: null }],
      activeGroupId: "screen-a",
      tree,
      focusedLeafId: first.id,
      zoomedLeafId: null,
      ephemeralGroupId: null,
    });
    render(<Screens />);
    return screen.getAllByRole("button", { name: "Request close" }).map((b) => b.dataset.zoom);
  };

  it("leaves a lone pane at 100%", () => {
    const one = makeLeaf("session-a");
    expect(show(one)).toEqual(["1"]);
  });

  it("gives two tiled panes 90%", () => {
    expect(show(boundPanes())).toEqual(["0.9", "0.9"]);
  });

  it("gives three or more tiled panes 75%", () => {
    const two = boundPanes();
    const second = leaves(two)[1];
    expect(show(insertLeaf(two, second.id, "bottom", makeLeaf("session-c")))).toEqual(["0.75", "0.75", "0.75"]);
  });

  it("keeps a zoom the user set", () => {
    const two = boundPanes();
    const [a] = leaves(two);
    a.zoom = 1.25;
    expect(show(two)).toEqual(["1.25", "0.9"]);
  });
});
