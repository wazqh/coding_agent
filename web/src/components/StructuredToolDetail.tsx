import { UnifiedDiff } from "./UnifiedDiff";

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
  verification_check: "验证规则",
  created_files: "本轮新建文件",
  created_directories: "本轮新建目录",
  target_paths: "覆盖路径",
  cwd: "工作目录",
  timeout_seconds: "超时（秒）",
  source: "来源",
  label: "名称",
  kind: "类型",
  enabled: "已启用",
};

const hiddenKeys = new Set([
  "ok",
  "retryable",
  "truncated",
  "hard_blocked",
  "summary",
  "sha256",
  "change_id",
  "change_kind",
  "reversible",
]);
const codeLikeKeys = new Set(["command", "stdout", "stderr", "output", "content", "diff"]);

const verificationStatusLabels: Record<string, string> = {
  passed: "验证通过",
  test_failed: "测试未通过",
  configuration_error: "验证配置有误",
  approval_denied: "验证未获授权",
  timed_out: "验证超时",
  cancelled: "验证已取消",
};

const checkKindLabels: Record<string, string> = {
  test: "测试",
  build: "构建",
  lint: "代码检查",
  typecheck: "类型检查",
  custom: "自定义",
};

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function unwrap(detail: unknown): unknown {
  const value = record(detail);
  return "raw" in value ? value.raw : detail;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function HighlightedCommand({ command, matchedText }: { command: string; matchedText: string }) {
  const index = matchedText ? command.toLocaleLowerCase().indexOf(matchedText.toLocaleLowerCase()) : -1;
  if (index < 0) return <>{command}</>;
  return (
    <>
      {command.slice(0, index)}
      <mark>{command.slice(index, index + matchedText.length)}</mark>
      {command.slice(index + matchedText.length)}
    </>
  );
}

function BlockedCommandDetail({ result }: { result: Record<string, unknown> }) {
  const data = record(result.data);
  const command = stringValue(data.command, "未提供命令文本");
  const matchedText = stringValue(data.matched_text);
  const riskLabel = stringValue(data.risk_label, "高风险命令");
  const guidance = stringValue(
    data.guidance,
    "请让 Agent 改用范围明确、可审阅且可恢复的操作。",
  );

  return (
    <div className="activity-friendly-detail is-safety-detail">
      <section className="command-safety-card" aria-label="已阻止的高风险命令">
        <header>
          <span className="command-safety-badge">硬安全规则</span>
          <div>
            <strong>已阻止高风险操作</strong>
            <p>{riskLabel}</p>
          </div>
        </header>
        <div className="command-safety-group">
          <span>尝试执行</span>
          <pre className="safety-command"><code>
            <HighlightedCommand command={command} matchedText={matchedText} />
          </code></pre>
        </div>
        <div className="command-safety-guidance">
          <strong>建议的安全做法</strong>
          <p>{guidance}</p>
        </div>
        <small>命令已在执行前停止，未对工作区产生改动。</small>
      </section>
    </div>
  );
}

function readableResultStatus(result: Record<string, unknown>, data: Record<string, unknown>): string {
  const verificationStatus = stringValue(data.verification_status);
  if (verificationStatusLabels[verificationStatus]) return verificationStatusLabels[verificationStatus];
  if (result.code === "OK") return data.verification === true ? "验证通过" : "执行成功";
  if (result.code === "COMMAND_FAILED") return data.verification === true ? "测试未通过" : "命令执行失败";
  if (result.code === "TIMEOUT") return "执行超时";
  if (result.code === "APPROVAL_DENIED") return "未获执行授权";
  if (result.code === "CANCELLED") return "执行已取消";
  return result.code ? "执行未完成" : "执行结果";
}

function OutputSection({ label, value, error = false }: { label: string; value: unknown; error?: boolean }) {
  const output = typeof value === "string" ? value.trimEnd() : "";
  if (!output) return null;
  return (
    <section className={`command-result-output${error ? " is-error" : ""}`}>
      <span>{label}</span>
      <pre><code>{output}</code></pre>
    </section>
  );
}

function CommandResultDetail({
  result,
  activityKind,
}: {
  result: Record<string, unknown>;
  activityKind?: string;
}) {
  const data = record(result.data);
  const check = record(data.verification_check);
  const command = stringValue(data.command);
  const cwd = stringValue(data.cwd, ".");
  const summary = stringValue(result.summary);
  const checkLabel = stringValue(check.label, stringValue(check.id));
  const checkKind = stringValue(check.kind);
  const timeout = typeof check.timeout_seconds === "number" ? check.timeout_seconds : null;
  const isVerification = activityKind === "validation" || data.verification === true;

  return (
    <div
      className="activity-friendly-detail is-command-result"
      role="group"
      aria-label={isVerification ? "验证结果详情" : "命令执行详情"}
    >
      <header className={`command-result-overview${result.code === "OK" ? " is-success" : " is-failed"}`}>
        <strong>{readableResultStatus(result, data)}</strong>
        {summary ? <span>{summary}</span> : null}
      </header>
      {command ? (
        <section className="command-result-command">
          <span>执行命令</span>
          <pre><code>{command}</code></pre>
        </section>
      ) : null}
      <dl className="command-result-meta">
        <div><dt>工作目录</dt><dd><code>{cwd}</code></dd></div>
        {typeof data.exit_code === "number" ? <div><dt>退出码</dt><dd>{data.exit_code}</dd></div> : null}
      </dl>
      <OutputSection label="标准输出" value={data.stdout} />
      <OutputSection label="错误输出" value={data.stderr} error />
      {checkLabel ? (
        <section className="command-result-rule">
          <span>验证规则</span>
          <div>
            <strong>{checkLabel}</strong>
            <small>
              {[checkKindLabels[checkKind] ?? checkKind, timeout ? `${timeout} 秒超时` : ""]
                .filter(Boolean)
                .join(" · ")}
            </small>
          </div>
        </section>
      ) : null}
    </div>
  );
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
  if (field === "diff") return <div className="structured-diff"><UnifiedDiff value={text} /></div>;
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
          <div className={`structured-field${key === "diff" ? " is-diff" : ""}`} key={key}>
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
  const isCommandResult = (
    activityKind === "command" || activityKind === "validation"
  ) && (
    typeof data.command === "string"
    || typeof data.exit_code === "number"
    || data.verification === true
  );

  if (blocked) return <BlockedCommandDetail result={result} />;
  if (isCommandResult) return <CommandResultDetail result={result} activityKind={activityKind} />;

  return (
    <div className="activity-friendly-detail">
      <StructuredFields value={value} />
      {activityKind === "command" && result.code ? (
        <small className="activity-result-code">命令详情</small>
      ) : null}
    </div>
  );
}
