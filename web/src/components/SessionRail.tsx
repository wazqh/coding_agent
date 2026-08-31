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
  onDeleteSession?: (sessionId: string) => void;
  onOpenProject?: (projectPath: string, sessionId?: string) => void;
  onAddProject?: () => void;
  onRemoveProject?: (projectPath: string) => void;
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
  onDeleteSession = () => undefined,
  onOpenProject = () => undefined,
  onAddProject = () => undefined,
  onRemoveProject = () => undefined,
}: SessionRailProps) {
  const fallbackProjects: ProjectSummary[] = projects.length
    ? projects
    : [{ name: workspaceName, path: "", current: true, sessions }];
  const [query, setQuery] = useState("");
  const [menuSessionId, setMenuSessionId] = useState<string | null>(null);
  const [confirmSessionId, setConfirmSessionId] = useState<string | null>(null);
  const [confirmProjectPath, setConfirmProjectPath] = useState<string | null>(null);
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
                  {!project.current ? (
                    <button
                      type="button"
                      className="project-more"
                      disabled={busy}
                      aria-label={`移除项目 ${project.name}`}
                      onClick={() => setConfirmProjectPath(project.path)}
                    >
                      ···
                    </button>
                  ) : null}
                </div>
                {confirmProjectPath === project.path ? (
                  <div className="project-remove-confirm" role="alertdialog" aria-label={`移除项目${project.name}`}>
                    <strong>从 Forge 中移除“{project.name}”？</strong>
                    <p className="mono-label">{project.path}</p>
                    <small>不会删除工作目录、Git 文件、会话或 Memory。</small>
                    <div>
                      <button type="button" onClick={() => setConfirmProjectPath(null)}>取消</button>
                      <button type="button" className="is-danger" onClick={() => { setConfirmProjectPath(null); onRemoveProject(project.path); }}>移除</button>
                    </div>
                  </div>
                ) : null}
                {expanded ? (
                  <div role="group" className="project-sessions">
                    {project.sessions.map((session) => {
                      const title = session.title || "未命名任务";
                      const menuOpen = menuSessionId === session.id;
                      const confirming = confirmSessionId === session.id;
                      return (
                        <div
                          className={`session-entry${session.id === activeSessionId ? " is-current" : ""}`}
                          key={session.id}
                        >
                          <button
                            type="button"
                            role="treeitem"
                            className={`session-row${session.id === activeSessionId ? " is-current" : ""}`}
                            disabled={busy}
                            aria-current={session.id === activeSessionId ? "page" : undefined}
                            aria-label={title}
                            onClick={() => {
                              setMenuSessionId(null);
                              setConfirmSessionId(null);
                              if (project.current) onResumeSession(session.id);
                              else onOpenProject(project.path, session.id);
                            }}
                          >
                            <span className="session-title">{title}</span>
                          </button>
                          {project.current ? (
                            <button
                              type="button"
                              className="session-more"
                              disabled={busy}
                              aria-label={`${title}的更多操作`}
                              aria-expanded={menuOpen || confirming}
                              onClick={() => {
                                setConfirmSessionId(null);
                                setMenuSessionId(menuOpen ? null : session.id);
                              }}
                            >
                              ···
                            </button>
                          ) : null}
                          {menuOpen ? (
                            <div className="session-menu" role="menu">
                              <button
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                  setMenuSessionId(null);
                                  setConfirmSessionId(session.id);
                                }}
                              >
                                删除对话
                              </button>
                            </div>
                          ) : null}
                          {confirming ? (
                            <div
                              className="session-delete-confirm"
                              role="alertdialog"
                              aria-label={`删除${title}`}
                            >
                              <strong>删除“{title}”？</strong>
                              <p>同时删除此对话引入的 Memory。此操作无法撤销。</p>
                              <div>
                                <button type="button" onClick={() => setConfirmSessionId(null)}>
                                  取消
                                </button>
                                <button
                                  type="button"
                                  className="is-danger"
                                  disabled={busy}
                                  aria-label={`确认删除${title}`}
                                  onClick={() => {
                                    setConfirmSessionId(null);
                                    onDeleteSession(session.id);
                                  }}
                                >
                                  删除
                                </button>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
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
