interface StructuredToolDetailProps {
  detail: unknown;
  activityKind?: string;
}

const labels: Record<string, string> = {
  name: "工具",
  arguments: "参数",
  code: "结果代码",
  command: "命令",
  path: "文件",
  pattern: "匹配模式",
  query: "搜索内容",
  exit_code: "退出码",
  stdout: "标准输出",
  stderr: "错误输出",
  output: "输出",
  content: "内容",
  data: "结果详情",
  diff: "变更内容",
  change_id: "变更 ID",
  change_kind: "变更类型",
  language: "语言",
  size: "大小",
};

const hiddenKeys = new Set(["ok", "retryable", "truncated", "hard_blocked", "summary"]);
const codeLikeKeys = new Set(["command", "stdout", "stderr", "output", "content", "diff"]);

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function unwrap(detail: unknown): unknown {
  const value = record(detail);
  return "raw" in value ? value.raw : detail;
}

function labelFor(key: string): string {
  return labels[key] ?? key.replaceAll("_", " ");
}

function ScalarValue({ field, value }: { field: string; value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return <span className="structured-empty">无</span>;
  }
  if (typeof value === "boolean") return <span>{value ? "是" : "否"}</span>;
  const text = String(value);
  if (codeLikeKeys.has(field) || text.includes("\n")) {
    return <pre className={field === "stderr" ? "is-error" : ""}><code>{text}</code></pre>;
  }
  return <span className={field.endsWith("id") || field === "code" ? "mono-label" : ""}>{text}</span>;
}

function StructuredFields({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    return (
      <ol className="structured-list">
        {value.map((item, index) => <li key={index}><StructuredFields value={item} depth={depth + 1} /></li>)}
      </ol>
    );
  }
  const values = record(value);
  const entries = Object.entries(values).filter(([key]) => !hiddenKeys.has(key));
  if (!entries.length) return <span className="structured-empty">没有更多详情</span>;
  return (
    <dl className={`structured-fields depth-${Math.min(depth, 2)}`}>
      {entries.map(([key, item]) => {
        const nested = typeof item === "object" && item !== null;
        return (
          <div className="structured-field" key={key}>
            <dt>{labelFor(key)}</dt>
            <dd>{nested ? <StructuredFields value={item} depth={depth + 1} /> : <ScalarValue field={key} value={item} />}</dd>
          </div>
        );
      })}
    </dl>
  );
}

export function StructuredToolDetail({ detail, activityKind }: StructuredToolDetailProps) {
  const value = unwrap(detail);
  const result = record(value);
  const data = record(result.data);
  const blocked = result.code === "DANGEROUS_COMMAND" || data.hard_blocked === true;

  return (
    <div className="activity-friendly-detail">
      {blocked ? (
        <div className="command-safety-note" role="note">
          <strong>安全策略已阻止</strong>
          <p>
            该命令命中不可恢复或可能越出工作区的硬性规则，不能在图形界面中覆盖。
            请让 Agent 改用范围明确、可审阅且可恢复的操作。
          </p>
        </div>
      ) : null}
      <StructuredFields value={value} />
      {activityKind === "command" && !blocked && result.code ? (
        <small className="activity-result-code">命令详情</small>
      ) : null}
    </div>
  );
}
