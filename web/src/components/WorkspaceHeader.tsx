import { MenuIcon } from "./icons";

interface WorkspaceHeaderProps {
  taskTitle: string;
  projectName: string;
  onToggleRail: () => void;
}

export function WorkspaceHeader({
  taskTitle,
  projectName,
  onToggleRail,
}: WorkspaceHeaderProps) {
  const normalizedTitle = taskTitle.trim() || "新对话";
  const compactTitle =
    normalizedTitle.length > 28 ? `${normalizedTitle.slice(0, 28)}…` : normalizedTitle;

  return (
    <header className="workspace-header">
      <button
        type="button"
        className="icon-button rail-toggle"
        aria-label="切换会话栏"
        onClick={onToggleRail}
      >
        <MenuIcon />
      </button>
      <div className="task-heading">
        <h1 title={normalizedTitle}>{compactTitle}</h1>
        <span>{projectName}</span>
      </div>
    </header>
  );
}
