import { useState } from 'react';

type Problem = { operation: 'add'; a: number; b: number };
type Evaluation = { is_correct: boolean; misconceptions: string[]; hint: string };
type TutorStep = { feedback: string; evaluation: Evaluation; question: Problem | null; phase: string };
type SessionCreated = { session_id: string; step: TutorStep };

const API_BASE = '/api';

const questionText = (q: Problem) => `What is ${q.a} + ${q.b}?`;

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [step, setStep] = useState<TutorStep | null>(null);
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<{ role: 'tutor' | 'student'; text: string }[]>([]);

  const start = async () => {
    const res = await fetch(`${API_BASE}/sessions`, { method: 'POST' });
    if (!res.ok) {
      alert('Failed to start session');
      return;
    }
    const data: SessionCreated = await res.json();
    setSessionId(data.session_id);
    setStep(data.step);
    setHistory([{ role: 'tutor', text: `${data.step.feedback} ${data.step.question ? questionText(data.step.question) : ''}`.trim() }]);
  };

  const submit = async () => {
    if (!sessionId || !step) return;
    const value = parseInt(input, 10);
    if (Number.isNaN(value)) return;

    setHistory((h) => [...h, { role: 'student', text: String(value) }]);
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    });
    if (!res.ok) {
      alert('Submit failed');
      return;
    }
    const next: TutorStep = await res.json();
    setStep(next);
    setHistory((h) => [...h, { role: 'tutor', text: `${next.feedback} ${next.question ? questionText(next.question) : ''}`.trim() }]);
    setInput('');
  };

  if (!step) {
    return (
      <main>
        <h1>Socratic Arithmetic Tutor</h1>
        <button onClick={start}>Start Session</button>
      </main>
    );
  }

  return (
    <main>
      <h1>Socratic Arithmetic Tutor</h1>
      <section aria-label="conversation">
        {history.map((m, i) => (
          <p key={i}>
            <strong>{m.role === 'tutor' ? 'Tutor' : 'Student'}:</strong> {m.text}
          </p>
        ))}
      </section>
      {step.phase !== 'complete' && (
        <section aria-label="answer">
          <label>
            Your answer:{' '}
            <input type="number" value={input} onChange={(e) => setInput(e.target.value)} />
          </label>
          <button onClick={submit}>Submit</button>
        </section>
      )}
      {step.phase === 'complete' && <p>All done! Session complete.</p>}
    </main>
  );
}

export default App;
