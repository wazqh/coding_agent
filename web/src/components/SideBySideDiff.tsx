interface DiffPair {
  left: string;
  right: string;
  kind: "context" | "changed" | "meta";
}

function pairLines(value: string): DiffPair[] {
  const rows: DiffPair[] = [];
  const lines = value.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith("--- ") || line.startsWith("+++ ")) continue;
    if (line.startsWith("@@")) {
      rows.push({ left: line, right: line, kind: "meta" });
      continue;
    }
    if (line.startsWith("-")) {
      const next = lines[index + 1] ?? "";
      if (next.startsWith("+")) {
        rows.push({ left: line.slice(1), right: next.slice(1), kind: "changed" });
        index += 1;
      } else {
        rows.push({ left: line.slice(1), right: "", kind: "changed" });
      }
      continue;
    }
    if (line.startsWith("+")) {
      rows.push({ left: "", right: line.slice(1), kind: "changed" });
      continue;
    }
    const content = line.startsWith(" ") ? line.slice(1) : line;
    rows.push({ left: content, right: content, kind: "context" });
  }
  return rows;
}

export function SideBySideDiff({ value }: { value: string }) {
  return (
    <div className="side-diff-scroll">
      <table className="side-diff" aria-label="并排 Diff">
        <thead><tr><th>修改前</th><th>修改后</th></tr></thead>
        <tbody>
          {pairLines(value).map((row, index) => (
            <tr className={`is-${row.kind}`} key={`${index}:${row.left}:${row.right}`}>
              <td><code>{row.left || " "}</code></td>
              <td><code>{row.right || " "}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
