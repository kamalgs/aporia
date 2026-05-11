import { test, expect } from '@playwright/test';

/**
 * These tests require the backend running locally on port 8000
 * with FakeAgent (default when no LLM env vars are set).
 *
 *   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
 *   cd frontend && npm run dev
 *
 * Then run: BASE_URL=http://localhost:5173 npx playwright test fake-agent
 */
const BASE = process.env.BASE_URL || 'http://localhost:5173';
const IS_LOCAL = BASE.includes('localhost') || BASE.includes('127.0.0.1');

test.describe('FakeAgent deterministic flow', () => {
  test.beforeAll(() => {
    test.skip(!IS_LOCAL, 'FakeAgent tests only run against a local backend (port 8000)');
  });
  test('full session: diagnostic → targeted → mastery → complete', async ({ request }) => {
    // 1. Start
    const startRes = await request.post('/sessions');
    expect(startRes.status()).toBe(200);
    const { session_id, step: s1 } = await startRes.json();
    expect(s1.phase).toBe('diagnostic');

    // 2. Submit wrong answer (omit carry)
    const { a: a1, b: b1 } = s1.question;
    const wrong = (Math.floor(a1 / 10) + Math.floor(b1 / 10)) * 10 + ((a1 % 10) + (b1 % 10)) % 10;

    const r2 = await request.post(`/sessions/${session_id}/answer`, { data: { text: String(wrong) } });
    expect(r2.status()).toBe(200);
    let step = await r2.json();
    expect(step.phase).toBe('targeted');

    // 3. Scaffolded steps: may take 1-4 correct answers to reach mastery
    let turns = 0;
    while (step.phase === 'targeted' && turns < 10) {
      const { a, b } = step.question;
      const next = await request.post(`/sessions/${session_id}/answer`, { data: { text: String(a + b) } });
      expect(next.status()).toBe(200);
      step = await next.json();
      turns += 1;
    }
    expect(step.phase).toBe('mastery');

    // 4. Correct mastery answer → complete
    const { a: a3, b: b3 } = step.question;
    const r4 = await request.post(`/sessions/${session_id}/answer`, { data: { text: String(a3 + b3) } });
    expect(r4.status()).toBe(200);
    const s4 = await r4.json();
    expect(s4.phase).toBe('complete');
    expect(s4.question).toBeNull();
  });

  test('direct mastery path: diagnostic correct → mastery → complete', async ({ request }) => {
    const startRes = await request.post('/sessions');
    const { session_id, step: s1 } = await startRes.json();
    const correct = s1.question.a + s1.question.b;

    const r2 = await request.post(`/sessions/${session_id}/answer`, { data: { text: String(correct) } });
    const s2 = await r2.json();
    expect(s2.phase).toBe('mastery');

    const r3 = await request.post(`/sessions/${session_id}/answer`, { data: { text: String(s2.question.a + s2.question.b) } });
    const s3 = await r3.json();
    expect(s3.phase).toBe('complete');
  });
});
