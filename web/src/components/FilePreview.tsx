import type { FilePreviewData } from "../state/store";

interface FilePreviewProps {
  file: FilePreviewData;
}

export function FilePreview({ file }: FilePreviewProps) {
  return (
    <section className="file-preview" aria-label={`${file.path} 文件预览`}>
      <div className="file-preview-heading">
        <span className="mono-label">{file.path}</span>
        <small>{file.language} · {file.size.toLocaleString()} B · 只读</small>
      </div>
      <pre><code>{file.text}</code></pre>
    </section>
  );
}
