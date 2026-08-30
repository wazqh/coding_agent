import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  content: string;
  streaming?: boolean;
}

interface HighlightToken {
  content: string;
  color?: string;
  fontStyle?: number;
}

const languageAliases: Record<string, string> = {
  js: "javascript",
  ts: "typescript",
  py: "python",
  sh: "bash",
  shell: "bash",
  ps1: "powershell",
  yml: "yaml",
  md: "markdown",
};
const supportedLanguages = new Set([
  "python",
  "javascript",
  "typescript",
  "tsx",
  "jsx",
  "json",
  "bash",
  "powershell",
  "yaml",
  "toml",
  "markdown",
  "css",
  "html",
  "sql",
  "diff",
]);

function CodeBlock({
  className,
  children,
  streaming,
}: {
  className?: string;
  children: React.ReactNode;
  streaming: boolean;
}) {
  const source = String(children).replace(/\n$/, "");
  const requested = /language-([\w-]+)/.exec(className ?? "")?.[1] ?? "";
  const language = languageAliases[requested] ?? requested;
  const [tokens, setTokens] = useState<HighlightToken[][] | null>(null);

  useEffect(() => {
    let active = true;
    if (streaming || !supportedLanguages.has(language)) {
      setTokens(null);
      return;
    }
    void import("./syntaxHighlighter").then(async ({ highlightCode }) => {
      const result = await highlightCode(source, language);
      if (active) setTokens(result);
    });
    return () => {
      active = false;
    };
  }, [language, source, streaming]);

  if (!tokens) return <code className={className}>{children}</code>;
  return (
    <code className={`${className ?? ""} is-highlighted`}>
      {tokens.map((line, lineIndex) => (
        <span className="code-line" key={`${lineIndex}-${line.map((token) => token.content).join("")}`}>
          {line.map((token, tokenIndex) => (
            <span key={`${tokenIndex}-${token.content}`} style={{ color: token.color }}>
              {token.content}
            </span>
          ))}
          {lineIndex < tokens.length - 1 ? "\n" : null}
        </span>
      ))}
    </code>
  );
}

export function MarkdownMessage({ content, streaming = false }: MarkdownMessageProps) {
  return (
    <div className="markdown-message">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          img: () => null,
          code: ({ className, children }) => (
            <CodeBlock className={className} streaming={streaming}>
              {children}
            </CodeBlock>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              onClick={(event) => {
                event.preventDefault();
                if (href && window.confirm(`是否打开外部链接？\n${href}`)) {
                  window.open(href, "_blank", "noopener,noreferrer");
                }
              }}
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
