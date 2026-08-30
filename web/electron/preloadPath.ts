import path from "node:path";

export function resolvePreloadPath(currentDirectory: string): string {
  return path.join(currentDirectory, "preload.cjs");
}
