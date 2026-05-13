const BASE = import.meta.env.PROD ? '' : '/api';

export interface Learner {
  id: string;
  name: string;
}

export interface Session {
  id: string;
  status: string;
}

export interface TurnResult {
  utterance: string;
  turn_signal: {
    on_target: boolean;
    matched_markers: string[];
    notes: string;
  };
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const createLearner = (name: string) =>
  post<Learner>('/learners', { name, cohort_tags: ['child'] });

export const createSession = (learnerId: string) =>
  post<Session>('/sessions', { learner_id: learnerId, program_id: 'elementary-math' });

export const sendTurn = (sessionId: string, text: string) =>
  post<TurnResult>(`/sessions/${sessionId}/turn`, { text });

export const endSession = (sessionId: string) =>
  post<Session>(`/sessions/${sessionId}/end`, {});
