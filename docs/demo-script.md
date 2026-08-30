# 120-second Web demo script

Prepare a disposable repository with one small failing authentication test and one proposed source
change. Use the release-candidate wheel, a clean browser profile at 1920×1080, and readable zoom.
Keep credentials, launch capability, personal paths, notifications, and terminal history outside the
recording frame. The Web UI and TUI share the same local controller; the video should show a real
model/tool/approval/test loop, not the mocked Playwright fixture.

| Time | Demonstration |
| --- | --- |
| 0:00–0:10 | Start `coding-agent web --cwd demo`; cut to the opened browser after the one-time capability has disappeared from the address bar. Show Forge branding, project, model, and Prompt permission mode. |
| 0:10–0:23 | Click **新任务**, enter “修复认证逻辑并运行相关测试”, and send. Show the user task as a distinct surface while the composer changes to Stop. |
| 0:23–0:42 | Let the compact timeline show the plan plus grouped read/search activity. Keep raw tool detail collapsed and the Agent's streamed explanation readable. |
| 0:42–1:02 | Pause on the inline approval card. Expand the proposed Diff, point out the workspace-relative path, then choose **允许一次**. |
| 1:02–1:20 | Show the focused test, one structured failure if available, the correction, and the final green validation card. Do not linger on repetitive tool steps. |
| 1:20–1:35 | Keep the final Markdown answer fully expanded. Show the completed/validation status and concise evidence. |
| 1:35–1:50 | Open **变更**, show the per-change `+/-` summary, rendered Diff, and bounded read-only file preview in the right inspector. |
| 1:50–2:00 | Return to the conversation and briefly state that Web and TUI share the original Python `AgentController`, local tools, approvals, sessions, Memory, Skills, and workspace safety boundary. |

Before submission, watch the exported file once and verify that it is at most two minutes and
200 MB; no API key, token, launch capability, account path, unrelated personal data, hidden
notification, or private chain-of-thought may be visible. Archive the exact commit demonstrated and
keep a TUI recording fallback in case the browser capture environment fails.
