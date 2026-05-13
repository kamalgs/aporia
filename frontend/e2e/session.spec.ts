import { test, expect } from '@playwright/test';

/**
 * Happy-path E2E test for the learner chat UI.
 *
 * Requires:
 *   - Backend running on port 8000 (uvicorn app.main:app)
 *   - Frontend dev server running on port 5173 (npm run dev)
 *
 * These are skipped automatically when not running against localhost.
 */

const BASE = process.env.BASE_URL || 'http://localhost:5173';
const IS_LOCAL = BASE.includes('localhost') || BASE.includes('127.0.0.1');

test.describe('Learner chat session', () => {
  test.beforeAll(() => {
    test.skip(!IS_LOCAL, 'E2E tests only run against a local stack');
  });

  test('welcome screen → start session → see first tutor message', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('h1')).toHaveText('AI Tutor');
    await expect(page.locator('#learner-name')).toBeVisible();

    await page.fill('#learner-name', 'TestLearner');
    await page.click('button:has-text("Start Learning")');

    // Wait for auto-start turn: first tutor message should appear
    const convo = page.locator('[aria-label="conversation"]');
    await expect(convo.locator('article.message.tutor')).toHaveCount(1, { timeout: 30000 });

    // Input bar is now visible
    await expect(page.locator('.chat-textarea')).toBeVisible();
  });

  test('send an answer and get tutor response', async ({ page }) => {
    await page.goto('/');
    await page.fill('#learner-name', 'TestLearner');
    await page.click('button:has-text("Start Learning")');

    const convo = page.locator('[aria-label="conversation"]');
    await expect(convo.locator('article.message.tutor')).toHaveCount(1, { timeout: 30000 });

    const before = await convo.locator('article.message').count();

    await page.fill('.chat-textarea', '42');
    await page.click('.send-button');

    // Learner message appears, then tutor responds
    await expect(async () => {
      const after = await convo.locator('article.message').count();
      expect(after).toBeGreaterThanOrEqual(before + 2);
    }).toPass({ timeout: 30000 });
  });

  test('end session shows completion message', async ({ page }) => {
    await page.goto('/');
    await page.fill('#learner-name', 'TestLearner');
    await page.click('button:has-text("Start Learning")');

    const convo = page.locator('[aria-label="conversation"]');
    await expect(convo.locator('article.message.tutor')).toHaveCount(1, { timeout: 30000 });

    await page.click('button:has-text("End")');

    await expect(page.locator('.session-done')).toContainText('Session complete');
    await expect(page.locator('.chat-header .status')).toHaveText('Session ended');
  });
});
