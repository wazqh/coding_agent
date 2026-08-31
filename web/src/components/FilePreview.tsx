import { useEffect, useState } from "react";

import type { FilePreviewData } from "../state/store";

interface HighlightToken {
  content: string;
  color?: string;
}

const highlightedLanguages = new Set([
  "bash", "c", "cpp", "css", "go", "html", "java", "javascript", "json", "jsx",
  "markdown", "powershell", "python", "rust", "sql", "toml", "tsx", "typescript", "xml",
  "yaml",
]);

const languageAliases: Record<string, string> = { shell: "bash" };

interface FilePreviewProps {
  file: FilePreviewData;
}

export function FilePreview({ file }: FilePreviewProps) {
  const lines = file.text.replace(/\n$/, "").split("\n");
  const language = languageAliases[file.language] ?? file.language;
  const [tokens, setTokens] = useState<HighlightToken[][] | null>(null);

  useEffect(() => {
    let active = true;
    if (!highlightedLanguages.has(language) || file.text.length > 250_000) {
      setTokens(null);
      return;
    }
    void import("./syntaxHighlighter")
      .then(({ highlightCode }) => highlightCode(
        file.text.replace(/\n$/, ""),
        language,
        "github-light-default",
      ))
      .then((result) => {
        if (active) setTokens(result);
      })
      .catch(() => {
        if (active) setTokens(null);
      });
    return () => {
      active = false;
    };
  }, [file.text, language]);

  return (
    <section className="file-preview" aria-label={`${file.path} 文件预览`}>
      <div className="file-preview-heading">
        <span className="mono-label">{file.path}</span>
        <small>{file.language} · {file.size.toLocaleString()} B · 只读</small>
      </div>
      <div className="file-preview-code" role="region" aria-label={`${file.path} 内容`}>
        {lines.map((line, index) => (
          <div className="file-preview-line" key={`${index}-${line}`}>
            <span aria-hidden="true">{index + 1}</span>
            <code>
              {tokens?.[index]?.length
                ? tokens[index].map((token, tokenIndex) => (
                    <span
                      className="syntax-token"
                      key={`${tokenIndex}-${token.content}`}
                      style={{ color: token.color }}
                    >
                      {token.content}
                    </span>
                  ))
                : line || " "}
            </code>
          </div>
        ))}
      </div>
    </section>
  );
}
