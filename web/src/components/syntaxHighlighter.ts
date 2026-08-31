import bash from "@shikijs/langs/bash";
import css from "@shikijs/langs/css";
import c from "@shikijs/langs/c";
import cpp from "@shikijs/langs/cpp";
import diff from "@shikijs/langs/diff";
import html from "@shikijs/langs/html";
import go from "@shikijs/langs/go";
import java from "@shikijs/langs/java";
import javascript from "@shikijs/langs/javascript";
import json from "@shikijs/langs/json";
import jsx from "@shikijs/langs/jsx";
import markdown from "@shikijs/langs/markdown";
import powershell from "@shikijs/langs/powershell";
import python from "@shikijs/langs/python";
import rust from "@shikijs/langs/rust";
import sql from "@shikijs/langs/sql";
import toml from "@shikijs/langs/toml";
import tsx from "@shikijs/langs/tsx";
import typescript from "@shikijs/langs/typescript";
import yaml from "@shikijs/langs/yaml";
import xml from "@shikijs/langs/xml";
import githubDarkDefault from "@shikijs/themes/github-dark-default";
import githubLightDefault from "@shikijs/themes/github-light-default";
import { createHighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";

const highlighter = createHighlighterCore({
  themes: [githubDarkDefault, githubLightDefault],
  langs: [
    python,
    c,
    cpp,
    go,
    java,
    rust,
    javascript,
    typescript,
    tsx,
    jsx,
    json,
    bash,
    powershell,
    yaml,
    toml,
    markdown,
    css,
    html,
    xml,
    sql,
    diff,
  ],
  engine: createJavaScriptRegexEngine(),
});

export async function highlightCode(
  source: string,
  language: string,
  theme: "github-dark-default" | "github-light-default" = "github-dark-default",
) {
  const instance = await highlighter;
  return instance.codeToTokens(source, {
    lang: language,
    theme,
  }).tokens;
}
