import bash from "@shikijs/langs/bash";
import css from "@shikijs/langs/css";
import diff from "@shikijs/langs/diff";
import html from "@shikijs/langs/html";
import javascript from "@shikijs/langs/javascript";
import json from "@shikijs/langs/json";
import jsx from "@shikijs/langs/jsx";
import markdown from "@shikijs/langs/markdown";
import powershell from "@shikijs/langs/powershell";
import python from "@shikijs/langs/python";
import sql from "@shikijs/langs/sql";
import toml from "@shikijs/langs/toml";
import tsx from "@shikijs/langs/tsx";
import typescript from "@shikijs/langs/typescript";
import yaml from "@shikijs/langs/yaml";
import githubDarkDefault from "@shikijs/themes/github-dark-default";
import { createHighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";

const highlighter = createHighlighterCore({
  themes: [githubDarkDefault],
  langs: [
    python,
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
    sql,
    diff,
  ],
  engine: createJavaScriptRegexEngine(),
});

export async function highlightCode(source: string, language: string) {
  const instance = await highlighter;
  return instance.codeToTokens(source, {
    lang: language,
    theme: "github-dark-default",
  }).tokens;
}
