import { describe, expect, it } from "vitest";
import { rowText } from "./terminalLinks";

/** A fake xterm row: each entry is one cell's characters, "" for the second
 *  half of a wide character. */
function row(cells: string[]) {
  return {
    length: cells.length,
    getCell: (x: number) => {
      const c = cells[x];
      if (c === undefined) return undefined;
      const wide = cells[x + 1] === "";
      return { getChars: () => c, getWidth: () => (c === "" ? 0 : wide ? 2 : 1) } as never;
    },
  };
}

describe("rowText", () => {
  it("maps each character to its cell, wide characters taking two", () => {
    const { text, cells } = rowText(row(["中", "", "a", "/", "b"]));
    expect(text).toBe("中a/b");
    expect(cells).toEqual([
      { x: 0, width: 2 },
      { x: 2, width: 1 },
      { x: 3, width: 1 },
      { x: 4, width: 1 },
    ]);
  });
});
