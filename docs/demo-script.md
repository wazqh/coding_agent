# 120-second demo script

Prepare a disposable repository with one failing date-parser test and a trusted `test-fix` skill.
Use a fresh terminal profile with large readable text. Keep credentials outside the recording frame
and verify the final video is at most two minutes and 200 MB.

| Time | Demonstration |
| --- | --- |
| 0:00–0:12 | Start `coding-agent --cwd demo`; show the scrolling header, model, workspace, and prompt permission mode. |
| 0:12–0:28 | Enter `$test-fix 修复日期解析并补充回归验证`; show skill activation and the visible plan. |
| 0:28–0:48 | Show file search/read cards and the first failing focused test. Keep raw output collapsed. |
| 0:48–1:08 | Show the proposed unified diff and choose one-time approval. Emphasize the workspace-relative path and hash guard. |
| 1:08–1:24 | Let the first attempted fix fail, then show the structured observation and corrected second attempt. |
| 1:24–1:38 | Show the focused and full test suite passing, followed by the completed event and footer. |
| 1:38–1:50 | Run `/memory remember 提交前运行 pytest`; show explicit storage confirmation, then `/memory list`. |
| 1:50–2:00 | Run `/status` and `/diff`; end on the final passing evidence and clean summary. |

Before submission, watch the exported file once, confirm no API key, token, account path, unrelated
personal data, or hidden notification is visible, and archive the exact commit demonstrated.
