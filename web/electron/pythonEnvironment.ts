import path from "node:path";

export interface GatewayEnvironmentOptions {
  appPath: string;
  inheritedPythonPath?: string | undefined;
  sourceExists: (candidate: string) => Promise<boolean>;
  delimiter?: string;
}

export async function buildGatewayEnvironment(
  options: GatewayEnvironmentOptions,
): Promise<Record<string, string>> {
  const candidate = path.resolve(options.appPath, "..", "src");
  const inherited = options.inheritedPythonPath?.trim();
  if (!(await options.sourceExists(candidate))) {
    return inherited ? { PYTHONPATH: inherited } : {};
  }
  const delimiter = options.delimiter ?? path.delimiter;
  return { PYTHONPATH: inherited ? `${candidate}${delimiter}${inherited}` : candidate };
}
