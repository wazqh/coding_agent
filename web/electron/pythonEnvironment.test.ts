import path from "node:path";

import { describe, expect, test } from "vitest";

import { buildGatewayEnvironment } from "./pythonEnvironment.js";

describe("buildGatewayEnvironment", () => {
  test("prepends the checkout src directory when Electron runs from web", async () => {
    const repository = path.resolve("fixtures", "repo");
    const source = path.join(repository, "src");
    const inherited = path.resolve("fixtures", "shared");
    const environment = await buildGatewayEnvironment({
      appPath: path.join(repository, "web"),
      inheritedPythonPath: inherited,
      sourceExists: async (candidate) => candidate === source,
      delimiter: path.delimiter,
    });

    expect(environment).toEqual({ PYTHONPATH: `${source}${path.delimiter}${inherited}` });
  });

  test("leaves Python path untouched for packaged apps without checkout sources", async () => {
    const environment = await buildGatewayEnvironment({
      appPath: path.resolve("Forge", "resources", "app.asar"),
      inheritedPythonPath: path.resolve("shared"),
      sourceExists: async () => false,
      delimiter: path.delimiter,
    });

    expect(environment).toEqual({ PYTHONPATH: path.resolve("shared") });
  });
});
