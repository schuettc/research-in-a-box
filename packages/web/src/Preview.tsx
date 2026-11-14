import { useEffect, useState } from "react";

/** How much of a file the preview reads: the first 64 KiB. */
export const PREVIEW_BYTES = 65536;
const ROWS = 20;

/** Split CSV text into rows of fields, honouring quoted fields with commas, quotes and newlines. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += ch;
  }
  if (field || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/**
 * The first rows of a CSV, read by range through the file's link: only the first 64 KiB, with
 * the last line dropped when the file goes on past them, since it is cut partway.
 */
export async function readHead(url: string, size: number): Promise<string[][]> {
  const response = await fetch(url, { headers: { Range: `bytes=0-${PREVIEW_BYTES - 1}` } });
  if (!response.ok) throw new Error(`the file answered ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer()).subarray(0, PREVIEW_BYTES);
  let text = new TextDecoder().decode(bytes);
  if (size > bytes.length) text = text.slice(0, text.lastIndexOf("\n") + 1);
  return parseCsv(text).slice(0, ROWS + 1);
}

/** A table's first rows, its header row first. */
export function Preview({ url, size }: { url: string; size: number }) {
  const [rows, setRows] = useState<string[][] | "failed" | null>(null);
  useEffect(() => {
    let current = true;
    readHead(url, size).then(
      (found) => current && setRows(found),
      () => current && setRows("failed"),
    );
    return () => {
      current = false;
    };
  }, [url, size]);

  if (rows === null) {
    return (
      <p role="status" className="muted">
        Reading the first rows…
      </p>
    );
  }
  if (rows === "failed") return <p role="alert">The file can't be read right now.</p>;
  if (rows.length === 0) return <p className="muted">The file is empty.</p>;
  const [head = [], ...body] = rows;
  return (
    // Focusable, so a keyboard can scroll a wide or long preview.
    <div className="table-scroll preview" tabIndex={0} role="region" aria-label="The first rows">
      <table className="cols">
        <thead>
          <tr>
            {head.map((name, index) => (
              <th key={index} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, index) => (
            <tr key={index}>
              {row.map((value, column) => (
                <td key={column}>{value}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
