import type { CompletionItem } from "../protocol/types";
import { CloseIcon } from "./icons";

interface CommandGuideProps {
  commands: CompletionItem[];
  onClose: () => void;
  onChoose: (command: string) => void;
}

export function CommandGuide({ commands, onClose, onChoose }: CommandGuideProps) {
  return (
    <section className="command-guide" aria-label="命令说明">
      <header>
        <div>
          <span>COMMAND PALETTE</span>
          <h2>Slash commands</h2>
        </div>
        <button type="button" className="icon-button" aria-label="关闭命令说明" onClick={onClose}>
          <CloseIcon />
        </button>
      </header>
      <div className="command-guide-list">
        {commands.map((command) => (
          <button type="button" key={command.label} onClick={() => onChoose(command.insert_text)}>
            <strong className="mono-label">{command.label}</strong>
            <span>{command.description}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
