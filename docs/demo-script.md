# 120-second Electron desktop demo script

Prepare a disposable repository with one small failing authentication test and one proposed source
change. Launch the release-candidate source build at 1920×1080 and keep credentials, personal paths,
notifications, and terminal history outside the recording frame. The desktop and TUI share the same
local controller; show a real model/tool/approval/test loop, not the mocked Playwright fixture.

| Time | Demonstration |
| --- | --- |
| 0:00–0:10 | Open Forge Coding Agent on the prepared project. Show the project/session tree, active model, permission mode, and task inspector entry. |
| 0:10–0:23 | Click **新对话**, enter “修复认证逻辑并运行相关测试”, and send. Show the user task as a distinct surface and the composer changing to Stop. |
| 0:23–0:42 | Let the visible working receipt show the current step, grouped read/search activity, and the plan progressing from top to bottom. Keep raw tool payloads collapsed. |
| 0:42–1:02 | Pause on the inline approval card. Expand the proposed Diff, identify its workspace-relative path, then choose **允许一次**. |
| 1:02–1:20 | Show the focused test, one structured failure if available, the correction, and the green validation receipt. Do not linger on repetitive tool calls. |
| 1:20–1:35 | Keep the final Markdown answer fully expanded. Show completion and verification evidence without exposing hidden reasoning. |
| 1:35–1:50 | Open **任务检查器 → 变更**, show the per-change summary, rendered Diff, and bounded read-only file preview. |
| 1:50–2:00 | Return to the conversation and state that Electron and TUI share the original Python `AgentController`, local tools, approvals, sessions, Memory, Skills, and workspace boundary. |

Before submission, watch the exported file once and verify that it is at most two minutes and
200 MB. Confirm that no API key, token, account path, unrelated personal data, hidden notification,
or private chain-of-thought is visible. Archive the exact demonstrated commit and keep a TUI capture
fallback in case the desktop recording environment fails.
