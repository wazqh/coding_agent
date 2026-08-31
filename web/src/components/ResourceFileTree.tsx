import { useMemo, useState, type CSSProperties } from "react";

import { ChevronIcon, FileIcon, FolderIcon } from "./icons";

export type ResourceFileStatus = "created" | "modified" | "read";

interface ResourceFileTreeProps {
  paths: string[];
  statuses: ReadonlyMap<string, ResourceFileStatus>;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

interface ResourceTreeNode {
  name: string;
  path: string;
  kind: "directory" | "file";
  children: ResourceTreeNode[];
}

interface MutableDirectory {
  name: string;
  path: string;
  directories: Map<string, MutableDirectory>;
  files: Map<string, ResourceTreeNode>;
}

const statusLabels: Record<ResourceFileStatus, string> = {
  created: "新建",
  modified: "已修改",
  read: "已读取",
};

function normalizePath(path: string): string {
  return path.replaceAll("\\", "/").replace(/^\.\//, "");
}

function sortNodes(nodes: ResourceTreeNode[]): ResourceTreeNode[] {
  return nodes.sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "directory" ? -1 : 1;
    return left.name.localeCompare(right.name);
  });
}

function finalizeDirectory(directory: MutableDirectory): ResourceTreeNode[] {
  const directories = [...directory.directories.values()].map((child) => ({
    name: child.name,
    path: child.path,
    kind: "directory" as const,
    children: finalizeDirectory(child),
  }));
  return sortNodes([...directories, ...directory.files.values()]);
}

export function buildResourceTree(paths: string[]): ResourceTreeNode[] {
  const root: MutableDirectory = {
    name: "",
    path: "",
    directories: new Map(),
    files: new Map(),
  };

  for (const rawPath of paths) {
    const path = normalizePath(rawPath);
    const parts = path.split("/").filter(Boolean);
    if (!parts.length) continue;
    let directory = root;
    for (const [index, part] of parts.entries()) {
      const childPath = parts.slice(0, index + 1).join("/");
      if (index === parts.length - 1) {
        directory.files.set(childPath, {
          name: part,
          path: childPath,
          kind: "file",
          children: [],
        });
        continue;
      }
      let child = directory.directories.get(part);
      if (!child) {
        child = {
          name: part,
          path: childPath,
          directories: new Map(),
          files: new Map(),
        };
        directory.directories.set(part, child);
      }
      directory = child;
    }
  }

  return finalizeDirectory(root);
}

export function ResourceFileTree({ paths, statuses, selectedPath, onSelect }: ResourceFileTreeProps) {
  const nodes = useMemo(() => buildResourceTree(paths), [paths]);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const renderNode = (node: ResourceTreeNode, depth: number) => {
    const style = { "--tree-depth": depth } as CSSProperties;
    if (node.kind === "directory") {
      const expanded = !collapsed.has(node.path);
      return (
        <div className="resource-tree-branch" key={node.path}>
          <button
            type="button"
            role="treeitem"
            aria-label={`${node.name} 文件夹`}
            aria-expanded={expanded}
            className="resource-tree-row is-directory"
            style={style}
            onClick={() => {
              setCollapsed((current) => {
                const next = new Set(current);
                if (next.has(node.path)) next.delete(node.path);
                else next.add(node.path);
                return next;
              });
            }}
          >
            <ChevronIcon className={expanded ? "is-expanded" : ""} />
            <FolderIcon />
            <span>{node.name}</span>
            <small>{node.children.length}</small>
          </button>
          {expanded ? (
            <div role="group">
              {node.children.map((child) => renderNode(child, depth + 1))}
            </div>
          ) : null}
        </div>
      );
    }

    const status = statuses.get(node.path) ?? "read";
    const statusLabel = statusLabels[status];
    return (
      <button
        type="button"
        role="treeitem"
        aria-label={`${node.name} ${statusLabel}`}
        aria-selected={selectedPath === node.path}
        className={`resource-tree-row is-file${selectedPath === node.path ? " is-selected" : ""}`}
        style={style}
        key={node.path}
        onClick={() => onSelect(node.path)}
      >
        <span className="resource-tree-spacer" aria-hidden="true" />
        <FileIcon />
        <span>{node.name}</span>
        <small className={`resource-file-status is-${status}`}>{statusLabel}</small>
      </button>
    );
  };

  return (
    <div className="resource-file-tree" role="tree" aria-label="会话文件">
      {nodes.map((node) => renderNode(node, 0))}
    </div>
  );
}
