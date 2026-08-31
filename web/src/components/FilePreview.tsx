import type { FilePreviewData } from "../state/store";

interface FilePreviewProps {
  file: FilePreviewData;
}

export function FilePreview({ file }: FilePreviewProps) {
  const lines = file.text.replace(/\n$/, "").split("\n");
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
            <code>{line || " "}</code>
          </div>
        ))}
      </div>
    </section>
  );
}
