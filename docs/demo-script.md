# 120-second Electron desktop demo script

Use a disposable Python repository with a small slug/date/authentication function and one failing
pytest. In the demo Session, import or save a focused `python -m pytest -q` rule rooted at that
project, and add the procedure “修改依赖或测试配置后，重新运行本会话已有测试规则”. Configure the model before
recording, close unrelated windows and notifications, and launch the exact candidate commit at
1920×1080. The recording must use a real model and local tools; the mocked Playwright path is only an
automated renderer check.

```powershell
python -m pip install -e ".[desktop]"
Set-Location web
npm ci
$env:FORGE_WORKSPACE = "D:\path\to\disposable-demo-repo"
npm run desktop:dev
```

| Time | Demonstration |
| --- | --- |
| 0:00–0:10 | Open Forge Coding Agent. Let the connection transition finish, then show the restored project/session, active model, permission mode, and project-organized history. No unnamed Session should be created just by launch. |
| 0:10–0:23 | Start **新对话** and ask: “修复日期解析的边界错误，补回归测试并运行项目验证；不要修改无关文件。” Show `/`, `@file`, or `$skill` completion briefly without sending completion text to the model. |
| 0:23–0:42 | Let the visible execution trace show the plan and grouped read/search/symbol-navigation activity. Keep routine details collapsed; mutation, failure, and validation rows remain individually visible. |
| 0:42–1:02 | Pause at the inline edit approval. Expand the proposed colored Diff, identify the workspace-relative path, and choose **允许一次**. Mention that workspace escape and hard-destructive commands are blocked before approval. |
| 1:02–1:22 | Open **Run → Verification**. Show the current Session mode, procedure, and the Agent-registered rule's source, covered path, relative project root, command, and timeout—or explicitly add a detected focused suggestion. Explain that saving authorizes only this exact command/root pair, while hard safety still runs first, then show the deterministic receipt. If the first test fails, use **Repair** to show the bounded evidence-fed repair cycle. Briefly contrast this with a read-only turn, which ends as complete without an irrelevant Verify button. Do not claim validation that is not visible. |
| 1:22–1:38 | Keep the final Markdown answer expanded. Show the concise completion evidence and confirm that plans/actions/results are visible while hidden chain-of-thought is neither requested nor rendered. |
| 1:38–1:53 | Open **任务检查器 → 变更**, select the changed file, and switch once between unified and side-by-side review. Open **资源** and show the adjacent workspace-confined read-only file preview with line numbers. Do not trigger Undo in the recorded candidate. |
| 1:53–2:00 | State: “Electron 只负责呈现与受限管理；自研 Python AgentController、本地工具、审批、会话、Memory、Skills 和工作区安全边界全部保留在本地运行时。” |

Before submission, watch the exported file from start to finish. Require MP4, duration at most two
minutes, size at most 200 MB, legible text, and no API key, token, credential dialog, account path,
private repository content, unrelated personal data, notification, raw protocol JSON, or hidden
chain-of-thought. Archive the exact demonstrated commit and exported video outside Git.
