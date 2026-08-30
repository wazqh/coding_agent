import { useEffect, useMemo, useState } from "react";

import { ChevronIcon, FolderIcon, PlusIcon, SearchIcon } from "./icons";
import type { ProjectSummary, SessionSummary } from "../state/store";

interface SessionRailProps {
  productName: string;
  workspaceName: string;
  busy: boolean;
  open: boolean;
  sessions: SessionSummary[];
  projects?: ProjectSummary[];
  activeSessionId: string | null;
  collapsed?: boolean;
  addingProject?: boolean;
  projectFeedback?: string;
  onToggleCollapsed?: () => void;
  onNewSession: () => void;
  onResumeSession: (sessionId: string) => void;
  onOpenProject?: (projectPath: string, sessionId?: string) => void;
  onAddProject?: () => void;
}

export function SessionRail({
  productName,
  workspaceName,
  busy,
  open,
  sessions,
  projects = [],
  activeSessionId,
  collapsed = false,
  addingProject = false,
  projectFeedback = "",
  onToggleCollapsed = () => undefined,
  onNewSession,
  onResumeSession,
  onOpenProject = () => undefined,
  onAddProject = () => undefined,
}: SessionRailProps) {
  const fallbackProjects: ProjectSummary[] = projects.length
    ? projects
    : [{ name: workspaceName, path: "", current: true, sessions }];
  const [query, setQuery] = useState("");
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    () => new Set(fallbackProjects.filter((project) => project.current).map((project) => project.path)),
  );

  useEffect(() => {
    setExpandedProjects((current) => {
      const next = new Set(current);
      for (const project of fallbackProjects) {
        if (project.current) next.add(project.path);
      }
      return next;
    });
  }, [projects]);

  const visibleProjects = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return fallbackProjects;
    return fallbackProjects
      .map((project) => ({
        ...project,
        sessions: project.sessions.filter((session) =>
          session.title.toLocaleLowerCase().includes(normalized),
        ),
      }))
      .filter(
        (project) =>
          project.name.toLocaleLowerCase().includes(normalized) || project.sessions.length > 0,
      );
  }, [fallbackProjects, query]);

  return (
    <nav
      aria-label="项目与对话"
      className={`session-rail${open ? " is-open" : ""}${collapsed ? " is-collapsed" : ""}`}
    >
      <div className="rail-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">F</span>
          <span className="brand-name">{productName}</span>
        </div>
        <button
          type="button"
          className="rail-collapse-button"
          aria-label={collapsed ? "展开会话栏" : "折叠会话栏"}
          onClick={onToggleCollapsed}
        >
          <ChevronIcon />
        </button>
      </div>

      <button className="new-task-button" type="button" disabled={busy} onClick={onNewSession}>
        <PlusIcon />
        <span>新对话</span>
      </button>

      <label className="session-search">
        <SearchIcon />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索对话"
          aria-label="搜索项目与对话"
        />
        <kbd>Ctrl K</kbd>
      </label>

      <section className="project-tree-section">
        <div className="project-tree-heading">
          <h2>项目</h2>
          <button
            type="button"
            aria-label={addingProject ? "正在添加项目" : "添加项目"}
            aria-busy={addingProject}
            disabled={busy || addingProject}
            onClick={onAddProject}
          >
            <PlusIcon />
          </button>
        </div>
        {projectFeedback ? <div className="project-feedback" role="status">{projectFeedback}</div> : null}
        <div className="project-tree" role="tree" aria-label="项目与对话列表">
          {visibleProjects.map((project) => {
            const expanded = Boolean(query) || expandedProjects.has(project.path);
            return (
              <div className={`project-node${project.current ? " is-current" : ""}`} key={project.path || project.name}>
                <div className="project-row">
                  <button
                    type="button"
                    className="project-toggle"
                    aria-label={`${expanded ? "折叠" : "展开"} ${project.name}`}
                    onClick={() => {
                      setExpandedProjects((current) => {
                        const next = new Set(current);
                        if (expanded && !query) next.delete(project.path);
                        else next.add(project.path);
                        return next;
                      });
                    }}
                  >
                    <ChevronIcon className={expanded ? "is-expanded" : ""} />
                  </button>
                  <button
                    type="button"
                    role="treeitem"
                    aria-expanded={expanded}
                    className="project-open"
                    disabled={busy}
                    onClick={() => {
                      if (project.current) {
                        setExpandedProjects((current) => new Set(current).add(project.path));
                      } else {
                        onOpenProject(project.path);
                      }
                    }}
                  >
                    <FolderIcon />
                    <strong>{project.name}</strong>
                  </button>
                </div>
                {expanded ? (
                  <div role="group" className="project-sessions">
                    {project.sessions.map((session) => (
                      <button
                        key={session.id}
                        type="button"
                        role="treeitem"
                        className={`session-row${session.id === activeSessionId ? " is-current" : ""}`}
                        disabled={busy}
                        aria-current={session.id === activeSessionId ? "page" : undefined}
                        aria-label={session.title || "未命名任务"}
                        onClick={() => {
                          if (project.current) onResumeSession(session.id);
                          else onOpenProject(project.path, session.id);
                        }}
                      >
                        <span className="session-title">{session.title || "未命名任务"}</span>
                      </button>
                    ))}
                    {!project.sessions.length ? <div className="empty-project">暂无对话</div> : null}
                  </div>
                ) : null}
              </div>
            );
          })}
          {!visibleProjects.length ? <div className="empty-sessions">没有匹配的项目或对话</div> : null}
        </div>
      </section>
    </nav>
  );
}
