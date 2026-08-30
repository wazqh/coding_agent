import path from "node:path";

function commandLineValue(argv: readonly string[], name: string): string | null {
  const index = argv.indexOf(name);
  const value = index >= 0 ? argv[index + 1] : undefined;
  return value?.trim() ? value : null;
}

export function resolveConfiguredWorkspace(
  argv: readonly string[],
  environment: Readonly<Record<string, string | undefined>>,
  currentDirectory: string,
): string {
  const configured =
    commandLineValue(argv, "--cwd") ?? environment.FORGE_WORKSPACE?.trim() ?? currentDirectory;
  return path.resolve(configured || currentDirectory);
}
