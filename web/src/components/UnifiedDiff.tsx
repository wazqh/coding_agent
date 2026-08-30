import { Diff, Hunk, parseDiff } from "react-diff-view";
import "react-diff-view/style/index.css";

interface UnifiedDiffProps {
  value: string;
  className?: string;
}

export function UnifiedDiff({ value, className = "" }: UnifiedDiffProps) {
  const files = parseDiff(value);
  return (
    <div className={`diff-scroll${className ? ` ${className}` : ""}`} data-testid="diff-scroll">
      {files.length ? (
        files.map((file, index) => (
          <Diff
            key={`${file.oldRevision}-${file.newRevision}-${index}`}
            viewType="unified"
            diffType={file.type}
            hunks={file.hunks}
          >
            {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
          </Diff>
        ))
      ) : (
        <pre>{value}</pre>
      )}
    </div>
  );
}
