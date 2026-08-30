from __future__ import annotations


def summarize_diff(
    *,
    change_id: str,
    path: str,
    kind: str,
    diff: str,
) -> dict[str, object]:
    additions = 0
    deletions = 0
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            additions += 1
        elif in_hunk and line.startswith("-"):
            deletions += 1
    return {
        "id": change_id,
        "path": path,
        "kind": kind,
        "additions": additions,
        "deletions": deletions,
        "diff": diff,
    }


def legacy_diff_path(diff: str) -> str:
    old_path: str | None = None
    new_path: str | None = None
    for line in diff.splitlines():
        if line.startswith("@@"):
            break
        if line.startswith("--- "):
            candidate = line[4:].split("\t", 1)[0]
            if candidate != "/dev/null":
                old_path = candidate[2:] if candidate.startswith("a/") else candidate
        elif line.startswith("+++ "):
            candidate = line[4:].split("\t", 1)[0]
            if candidate != "/dev/null":
                new_path = candidate[2:] if candidate.startswith("b/") else candidate
    return new_path or old_path or "unknown"
