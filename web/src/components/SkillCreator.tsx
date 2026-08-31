import { useEffect, useMemo, useState } from "react";

import type { SkillsState } from "../state/store";

type SkillTemplate = "custom" | "review" | "testing" | "documentation";
type SkillScope = "user" | "repo";

interface SkillCreateInput {
  scope: SkillScope;
  name: string;
  description: string;
  instructions: string;
}

interface SkillCreatorProps {
  busy: boolean;
  draft: SkillsState["draft"];
  items: Array<Record<string, unknown>>;
  onDraft: (requirement: string, template: SkillTemplate) => boolean | void;
  onCreate: (input: SkillCreateInput) => boolean | void;
}

const templates: Array<{ id: SkillTemplate; label: string }> = [
  { id: "custom", label: "自定义" },
  { id: "review", label: "代码审查" },
  { id: "testing", label: "测试修复" },
  { id: "documentation", label: "文档维护" },
];

function yamlValue(value: string): string {
  return JSON.stringify(value);
}

export function SkillCreator({ busy, draft, items, onDraft, onCreate }: SkillCreatorProps) {
  const [open, setOpen] = useState(Boolean(draft));
  const [requirement, setRequirement] = useState("");
  const [template, setTemplate] = useState<SkillTemplate>("custom");
  const [name, setName] = useState(draft?.name ?? "");
  const [description, setDescription] = useState(draft?.description ?? "");
  const [instructions, setInstructions] = useState(draft?.instructions ?? "");
  const [scope, setScope] = useState<SkillScope>("user");
  const [generating, setGenerating] = useState(false);
  const [creatingName, setCreatingName] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    if (!draft) return;
    setOpen(true);
    setName(draft.name);
    setDescription(draft.description);
    setInstructions(draft.instructions);
    setGenerating(false);
    setFeedback("");
  }, [draft]);

  useEffect(() => {
    if (!creatingName) return;
    const created = items.some((item) => item.name === creatingName);
    if (!created) return;
    setFeedback(`已创建 $${creatingName}`);
    setCreatingName("");
    setOpen(false);
    setShowPreview(false);
  }, [creatingName, items]);

  const duplicate = items.some((item) => item.name === name.trim());
  const validName = /^[a-z0-9][a-z0-9_-]{0,63}$/.test(name.trim());
  const canCreate = validName && Boolean(description.trim()) && Boolean(instructions.trim()) && !duplicate;
  const preview = useMemo(
    () => `---\nname: ${name.trim()}\ndescription: ${yamlValue(description.trim())}\n---\n\n${instructions.trim()}\n`,
    [description, instructions, name],
  );

  if (!open) {
    return (
      <div className="skill-create-launcher">
        <div>
          <strong>自定义 Skill</strong>
          <small>用自然语言描述工作流，生成后再确认写入</small>
        </div>
        <button type="button" className="primary-small" disabled={busy} onClick={() => { setOpen(true); setFeedback(""); }}>
          新建 Skill
        </button>
        {feedback ? <div className="setting-feedback" role="status">{feedback}</div> : null}
      </div>
    );
  }

  return (
    <section className="skill-creator" aria-label="创建 Skill">
      <div className="skill-creator-heading">
        <div><strong>新建 Skill</strong><small>草稿不会直接写入；请先审阅并修改</small></div>
        <button type="button" className="text-action" onClick={() => { setOpen(false); setGenerating(false); }}>取消</button>
      </div>

      {!draft || generating ? (
        <div className="skill-requirement-stage">
          <label>
            <span>您希望这个 Skill 如何工作？</span>
            <textarea
              aria-label="Skill 需求"
              rows={4}
              value={requirement}
              disabled={busy || generating}
              placeholder="例如：审查文件访问是否越过工作区边界，并给出按风险排序的修改建议。"
              onChange={(event) => setRequirement(event.target.value)}
            />
          </label>
          <div className="skill-template-picker" aria-label="Skill 模板">
            {templates.map((item) => (
              <button
                type="button"
                key={item.id}
                className={template === item.id ? "is-active" : ""}
                disabled={busy || generating}
                onClick={() => setTemplate(item.id)}
              >{item.label}</button>
            ))}
          </div>
          <button
            type="button"
            className="primary-wide"
            disabled={busy || generating || !requirement.trim()}
            onClick={() => {
              const accepted = onDraft(requirement.trim(), template);
              if (accepted === false) { setFeedback("本地运行时未连接，无法生成草稿"); return; }
              setGenerating(true);
              setFeedback("正在生成草稿…");
            }}
          >生成可编辑草稿</button>
          {feedback ? <div className="setting-feedback" role="status">{feedback}</div> : null}
        </div>
      ) : (
        <div className="skill-draft-stage">
          <div className="skill-draft-origin">
            {draft.generated_by === "model" ? "模型生成，可在创建前完整修改" : "模型暂不可用，已使用本地安全模板"}
          </div>
          <label><span>名称</span><input aria-label="Skill 名称" className="mono-label" value={name} onChange={(event) => setName(event.target.value)} /></label>
          {!validName && name ? <small className="field-error">仅使用小写字母、数字、连字符或下划线</small> : null}
          {duplicate ? <small className="field-error">同名 Skill 已存在，请修改名称</small> : null}
          <label><span>说明</span><input aria-label="Skill 说明" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <label><span>完整指令</span><textarea aria-label="Skill 指令" rows={10} value={instructions} onChange={(event) => setInstructions(event.target.value)} /></label>
          <div className="skill-scope-picker" aria-label="保存位置">
            <button type="button" className={scope === "user" ? "is-active" : ""} onClick={() => setScope("user")}>个人 Skills</button>
            <button type="button" className={scope === "repo" ? "is-active" : ""} onClick={() => setScope("repo")}>当前项目</button>
          </div>
          <small className="skill-scope-note">{scope === "repo" ? "写入当前受信任项目的 .agents/skills。" : "保存到本机个人 Skills，可在其他项目复用。"}</small>
          <button type="button" className="secondary-wide" aria-expanded={showPreview} onClick={() => setShowPreview((value) => !value)}>
            {showPreview ? "收起 SKILL.md 预览" : "预览 SKILL.md"}
          </button>
          {showPreview ? <pre className="skill-source-preview">{preview}</pre> : null}
          <button
            type="button"
            className="primary-wide"
            disabled={busy || !canCreate || Boolean(creatingName)}
            onClick={() => {
              const trimmedName = name.trim();
              const accepted = onCreate({ scope, name: trimmedName, description: description.trim(), instructions: instructions.trim() });
              if (accepted === false) { setFeedback("本地运行时未连接，尚未创建 Skill"); return; }
              setCreatingName(trimmedName);
              setFeedback("正在创建…");
            }}
          >创建 Skill</button>
          {feedback ? <div className="setting-feedback" role="status">{feedback}</div> : null}
        </div>
      )}
    </section>
  );
}
