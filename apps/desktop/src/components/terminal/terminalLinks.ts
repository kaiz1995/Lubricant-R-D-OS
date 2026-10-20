import type { IBufferLine, ILink, Terminal } from "@xterm/xterm";
import { activateLink, linkCandidates, resolveLink } from "@/lib/links";

/** One row's text, with the cell each UTF-16 unit of it sits in. A wide (CJK)
 *  character takes two cells, so a string index is not a column. */
export function rowText(line: Pick<IBufferLine, "length" | "getCell">): {
  text: string;
  cells: { x: number; width: number }[];
} {
  let text = "";
  const cells: { x: number; width: number }[] = [];
  for (let x = 0; x < line.length; x++) {
    const cell = line.getCell(x);
    if (!cell) break;
    const width = cell.getWidth();
    if (width === 0) continue; // the second half of a wide character
    const chars = cell.getChars() || " ";
    for (let i = 0; i < chars.length; i++) cells.push({ x, width });
    text += chars;
  }
  return { text, cells };
}

/**
 * URLs and existing local paths in a terminal become links (see lib/links):
 * xterm underlines one under the pointer, and a click opens the link menu.
 * `cwd` is read at hover time — the shell moves — so relative paths resolve
 * where the user is now.
 */
export function registerTerminalLinks(term: Terminal, cwd: () => string | null) {
  return term.registerLinkProvider({
    provideLinks(y, callback) {
      const line = term.buffer.active.getLine(y - 1);
      if (!line) return callback(undefined);
      const { text, cells } = rowText(line);
      const spans = linkCandidates(text);
      if (spans.length === 0) return callback(undefined);
      const from = { cwd: cwd() };
      void Promise.all(
        spans.map(async (span): Promise<ILink | null> => {
          const target = await resolveLink(span.text, from);
          if (!target) return null;
          const first = cells[span.start];
          const last = cells[span.end - 1];
          return {
            // 1-based, end inclusive — the last cell of the last character.
            range: { start: { x: first.x + 1, y }, end: { x: last.x + last.width, y } },
            text: span.text,
            decorations: { underline: true, pointerCursor: true },
            activate: (event) => activateLink(target, event),
          };
        }),
      ).then((links) => {
        const found = links.filter((l): l is ILink => l !== null);
        callback(found.length ? found : undefined);
      });
    },
  });
}
