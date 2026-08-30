import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

const initialSession = "a".repeat(24);
const newSession = "b".repeat(24);

async function installDemoRuntime(page: Page) {
  let seq = 0;
  let sessionId = initialSession;
  let turnCount = 0;
  let socket: WebSocketRoute | undefined;

  const emit = (type: string, data: Record<string, unknown>, turnId: string | null = null) => {
    seq += 1;
    socket?.send(
      JSON.stringify({
        protocol_version: 2,
        type,
        seq,
        session_id: sessionId,
        turn_id: turnId,
        data,
      }),
    );
  };

  await page.route("http://127.0.0.1:4173/", async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace("__FORGE_PRODUCT_NAME__", "Forge Coding Agent");
    await route.fulfill({ response, body });
  });
  await page.route("**/api/bootstrap", (route) => route.fulfill({ status: 204 }));
  await page.routeWebSocket("**/ws", (webSocket) => {
    socket = webSocket;
    webSocket.onMessage((message) => {
      if (typeof message !== "string") return;
      const request = JSON.parse(message) as Record<string, unknown>;
      if (request.type === "initialize") {
        emit("snapshot", {
          workspace_name: "HammerTest",
          workspace_path: "D:/codes/HammerTest",
          model: "gemini-3.7-flash",
          permissions: "prompt",
          context_window: 128000,
          busy: false,
          sessions: [
            {
              id: initialSession,
              title: "修复登录流程并补充测试",
              updated_at: "2026-08-29T18:12:00+08:00",
              model: "gemini-3.7-flash",
            },
          ],
        });
        return;
      }
      if (request.type === "session.create") {
        sessionId = newSession;
        emit("snapshot", {
          workspace_name: "HammerTest",
          workspace_path: "D:/codes/HammerTest",
          model: "gemini-3.7-flash",
          permissions: "prompt",
          context_window: 128000,
          busy: false,
          replace_timeline: true,
          sessions: [],
        });
        return;
      }
      if (request.type === "turn.start") {
        turnCount += 1;
        const turnId = `turn-${turnCount}`;
        emit("turn.started", { task: request.task }, turnId);
        if (turnCount > 1) return;
        emit("message.delta", { delta: "我会先检查相关文件，" }, turnId);
        emit("message.delta", { delta: "然后运行验证。" }, turnId);
        emit(
          "activity.upsert",
          {
            activity_id: "read-auth",
            kind: "read",
            title: "读取认证实现",
            summary: "src/auth.py · 1 个文件",
            status: "completed",
          },
          turnId,
        );
        emit(
          "approval.requested",
          {
            approval_id: "approval-demo",
            request: {
              action: "run_command",
              subject: "python -m pytest tests/test_auth.py -q",
              summary: "运行认证回归测试",
              diff: "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-old = False\n+fixed = True\n",
            },
          },
          turnId,
        );
        return;
      }
      if (request.type === "approval.resolve") {
        emit(
          "approval.resolved",
          { approval_id: request.approval_id, decision: request.decision },
          "turn-1",
        );
        emit(
          "activity.upsert",
          {
            activity_id: "validate-auth",
            kind: "validation",
            title: "验证认证测试",
            summary: "4 passed",
            status: "completed",
          },
          "turn-1",
        );
        emit(
          "message.final",
          { role: "assistant", content: "已完成修复，并通过 **4 项认证测试**。" },
          "turn-1",
        );
        emit(
          "turn.finished",
          { status: "completed", reason: "任务和验证均已完成" },
          "turn-1",
        );
        return;
      }
      if (request.type === "changes.list") {
        emit("changes.updated", {
          changes: [
            {
              id: "change-1",
              path: "src/auth.py",
              additions: 1,
              deletions: 1,
              diff: "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-old = False\n+fixed = True\n",
            },
          ],
        });
        return;
      }
      if (request.type === "file.preview") {
        emit("file.previewed", {
          path: "src/auth.py",
          language: "python",
          size: 13,
          text: "fixed = True\n",
        });
        return;
      }
      if (request.type === "turn.cancel") {
        emit("turn.finished", { status: "cancelled", reason: "用户停止任务" }, "turn-2");
      }
    });
  });
}

test("completes the polished two-minute demo path without page overflow", async ({ page }) => {
  await installDemoRuntime(page);
  await page.goto("/#capability=e2e-capability");

  await expect(page.getByText("Forge Coding Agent")).toBeVisible();
  await expect(page.getByText("HammerTest").first()).toBeVisible();
  await page.getByRole("button", { name: "新对话" }).click();

  const composer = page.getByRole("textbox", { name: "任务输入" });
  await composer.fill("修复认证逻辑并运行测试");
  await composer.press("Enter");
  await expect(page.getByText("然后运行验证。")).toBeVisible();
  await expect(page.getByText("读取认证实现")).toBeVisible();
  await expect(page.getByText("需要批准")).toBeVisible();
  await page.getByRole("button", { name: "查看拟议变更" }).click();
  await expect(page.getByText("fixed = True")).toBeVisible();
  await expect(page.locator(".approval-diff-content .diff-code-insert")).toBeVisible();
  await page.getByRole("button", { name: "允许一次" }).click();

  await expect(page.getByText("已完成修复，并通过")).toBeVisible();
  await expect(page.getByText("完成 · 验证通过")).toBeVisible();
  await page.getByRole("button", { name: "任务检查器" }).click();
  await page.getByRole("tab", { name: "变更" }).click();
  await expect(page.getByText("Agent 修改 1 处")).toBeVisible();
  await page.getByRole("button", { name: /src\/auth\.py/ }).click();
  const inspector = page.getByRole("complementary", { name: "任务检查器" });
  await expect(inspector.getByRole("cell", { name: "fixed = True" })).toBeVisible();
  await page.getByRole("button", { name: "查看文件" }).click();
  await expect(page.getByText("13 B")).toBeVisible();

  await page.getByRole("button", { name: "关闭检查器" }).click();
  await composer.fill("启动一个可取消的长任务");
  await composer.press("Enter");
  await expect(page.getByRole("button", { name: "停止任务" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("已停止 · 未运行验证")).toBeVisible();

  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
});

test("shows one composer focus treatment without an inner textarea outline", async ({ page }) => {
  await installDemoRuntime(page);
  await page.goto("/");

  const input = page.getByRole("textbox", { name: "任务输入" });
  await input.focus();

  await expect(input).toBeFocused();
  expect(await input.evaluate((element) => getComputedStyle(element).outlineStyle)).toBe("none");
  await expect(input.locator("xpath=..")).toHaveCSS("border-top-style", "solid");
});

test("fills the inspector surface at overlay widths", async ({ page }) => {
  await installDemoRuntime(page);
  await page.setViewportSize({ width: 1240, height: 800 });
  await page.goto("/");

  await page.getByRole("button", { name: "任务检查器" }).click();
  const drawer = page.locator(".context-drawer");
  const content = page.locator(".drawer-content");
  await expect(drawer).toBeVisible();

  const remainingSpace = await drawer.evaluate((element) => {
    const drawerBox = element.getBoundingClientRect();
    const contentBox = element.querySelector(".drawer-content")!.getBoundingClientRect();
    return Math.round(drawerBox.bottom - contentBox.bottom);
  });
  expect(remainingSpace).toBeLessThanOrEqual(2);
  expect(await drawer.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(776);
  await expect(content).toHaveCSS("overflow-y", "auto");
});

test("keeps collapsed conversations inside a centered readable width", async ({ page }) => {
  await installDemoRuntime(page);
  await page.goto("/");

  await page.locator(".rail-collapse-button").click();
  const composer = page.getByRole("textbox", { name: "任务输入" });
  await composer.fill("check the workspace");
  await composer.press("Enter");

  await expect(page.locator(".timeline")).toBeVisible();
  const timelineWidth = await page.locator(".timeline").evaluate(
    (element) => element.getBoundingClientRect().width,
  );
  expect(timelineWidth).toBeLessThanOrEqual(1240);
});
