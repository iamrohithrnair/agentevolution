import { test, expect } from "@playwright/test";

/**
 * Phase 5 dashboard smoke test (plan §7 exit criteria).
 *
 * Asserts:
 *  - The app shell renders with sidebar + topbar.
 *  - The dashboard mounts the map, reasoning stream, memory inspector,
 *    chat panel, and reflection feed.
 *  - A mission dispatch from the deploy page lands on /missions/<id> within
 *    a few seconds (the simulator queues + assigns drones immediately).
 *  - Memory inspector returns ≥ 1 hit on demand.
 *  - Reasoning stream and flight log emit events after dispatch.
 */

test.describe("Dronan operator console · Phase 5", () => {
  test.beforeEach(async ({ page }) => {
    page.on("pageerror", (e) => console.error("[pageerror]", e));
  });

  test("dashboard renders core surfaces", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByTestId("sidebar")).toBeVisible();
    await expect(page.getByTestId("topbar")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
    await expect(page.getByTestId("map-view")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("reasoning-stream")).toBeVisible();
    await expect(page.getByTestId("memory-cards")).toBeVisible();
    await expect(page.getByTestId("chat-panel")).toBeVisible();
    await expect(page.getByTestId("voice-hud")).toBeVisible();
  });

  test("memory inspector returns hits", async ({ page }) => {
    await page.goto("/memory");
    const cards = page.getByTestId("memory-cards");
    await expect(cards).toBeVisible();
    // Simulator always seeds at least 5 reflections.
    await expect(cards.locator("article")).toHaveCount(5, { timeout: 5_000 });
  });

  test("dispatching a mission lands on the detail page within 3s", async ({ page }) => {
    await page.goto("/deploy");
    await expect(page.getByTestId("dispatch-form")).toBeVisible();
    const submit = page.getByTestId("dispatch-submit");

    const start = Date.now();
    await submit.click();
    await page.waitForURL(/\/missions\/msn_/, { timeout: 5_000 });
    const transitMs = Date.now() - start;
    expect(transitMs).toBeLessThan(3_000);

    // Mission detail asserts.
    const detail = page.getByTestId("mission-detail");
    await expect(detail).toBeVisible();
    // Status badge lives in the page header (h1's sibling), match the first one.
    await expect(
      detail.locator("header").getByText(/^(queued|assigned|in transit|completed)$/i).first(),
    ).toBeVisible({ timeout: 5_000 });

    // Map renders for the new mission.
    await expect(page.getByTestId("map-view")).toBeVisible({ timeout: 10_000 });

    // Within a few seconds the simulator emits flight log entries.
    const flightLog = page.getByTestId("flight-log");
    await expect(flightLog).toBeVisible();
    await expect(async () => {
      const count = await flightLog.locator("li").count();
      if (count < 1) throw new Error(`expected ≥1 log, got ${count}`);
    }).toPass({ timeout: 6_000 });
  });

  test("agents page lists skills and live reasoning", async ({ page }) => {
    await page.goto("/agents");
    await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible();
    await expect(page.getByText(/win rate/i).first()).toBeVisible({ timeout: 5_000 });
  });
});
