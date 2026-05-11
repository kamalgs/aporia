import { test, expect } from '@playwright/test';

test.describe('Deployed site smoke tests', () => {
  test('front page loads and API starts a session', async ({ page, request }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toHaveText('Socratic Arithmetic Tutor');

    // The start button exists and is clickable
    await page.click('button:has-text("Start Session")');

    // After clicking, the tutor asks a question
    const convo = page.locator('section[aria-label="conversation"]');
    await expect(convo).toContainText('Tutor:', { timeout: 15000 });
    await expect(convo).toContainText('What is', { timeout: 15000 });
    await expect(page.locator('input[type="number"]')).toBeVisible();
  });

  test('API returns a valid structured TutorStep', async ({ request }) => {
    const res = await request.post('/sessions');
    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body).toHaveProperty('session_id');
    expect(body).toHaveProperty('step');
    expect(body.step).toHaveProperty('feedback');
    expect(body.step).toHaveProperty('evaluation');
    expect(body.step).toHaveProperty('question');
    expect(body.step).toHaveProperty('phase');
    expect(body.step.phase).toBe('diagnostic');
    expect(body.step.question.operation).toBe('add');
    expect(typeof body.step.question.a).toBe('number');
    expect(typeof body.step.question.b).toBe('number');
  });

  test('submitting a number advances the conversation', async ({ page }) => {
    await page.goto('/');
    await page.click('button:has-text("Start Session")');

    await expect(page.locator('section[aria-label="conversation"]')).toContainText('What is', { timeout: 15000 });

    // Submit any number — the tutor must respond
    const before = await page.locator('section[aria-label="conversation"] p').count();
    await page.fill('input[type="number"]', '99');
    await page.click('button:has-text("Submit")');

    // Wait for the tutor's feedback + next question to appear
    await expect(async () => {
      const after = await page.locator('section[aria-label="conversation"] p').count();
      expect(after).toBeGreaterThan(before);
    }).toPass({ timeout: 20000 });
  });
});
