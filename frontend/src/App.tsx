import { useState, useRef, useEffect } from 'react';
import './App.css';

type Problem = { operation: 'add'; a: number; b: number };
type Evaluation = { is_correct: boolean; misconceptions: string[]; hint: string };
type TutorStep = { feedback: string; evaluation: Evaluation; question: Problem | null; phase: string };
type SessionCreated = { session_id: string; step: TutorStep };
type Message = {
  id: string;
  role: 'tutor' | 'student';
  text: string;
  time: string;
};

const API_BASE = import.meta.env.PROD ? '' : '/api';

function formatTime(): string {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function questionText(q: Problem): string {
  return `What is ${q.a} + ${q.b}?`;
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const addMessage = (role: 'tutor' | 'student', text: string) => {
    setMessages((m) => [...m, { id: crypto.randomUUID(), role, text, time: formatTime() }]);
  };

  const startSession = async () => {
    const res = await fetch(`${API_BASE}/sessions`, { method: 'POST' });
    if (!res.ok) {
      addMessage('tutor', 'Sorry, I could not start a session. Please try again.');
      return;
    }
    const data: SessionCreated = await res.json();
    setSessionId(data.session_id);
    const text = `${data.step.feedback}\n\n${data.step.question ? questionText(data.step.question) : ''}`.trim();
    addMessage('tutor', text);
  };

  const sendMessage = async () => {
    if (!sessionId || !input.trim() || isSending) return;
    const text = input.trim();
    setInput('');
    setIsSending(true);
    addMessage('student', text);

    const res = await fetch(`${API_BASE}/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      addMessage('tutor', 'Something went wrong. Try again?');
      setIsSending(false);
      return;
    }
    const step: TutorStep = await res.json();
    const feedback = `${step.feedback}${step.question ? `\n\n${questionText(step.question)}` : ''}`.trim();
    addMessage('tutor', feedback);
    setIsSending(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!sessionId) {
    return (
      <div className="chat-container">
        <header className="chat-header">
          <div className="avatar">T</div>
          <div className="header-info">
            <h1>Socratic Tutor</h1>
            <span className="status">Tap to start</span>
          </div>
        </header>
        <main className="chat-empty">
          <p>Learn addition by solving problems together.</p>
          <button className="start-button" onClick={startSession}>Start Session</button>
        </main>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <header className="chat-header">
        <div className="avatar">T</div>
        <div className="header-info">
          <h1>Socratic Tutor</h1>
          <span className="status">online</span>
        </div>
      </header>

      <main className="chat-messages" aria-label="conversation">
        {messages.map((m) => (
          <article key={m.id} className={`message ${m.role}`}>
            <div className="message-bubble">
              <p>{m.text}</p>
            </div>
            <time className="message-time">{m.time}</time>
          </article>
        ))}
        {isSending && (
          <article className="message tutor">
            <div className="message-bubble typing">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </article>
        )}
        <div ref={endRef} />
      </main>

      <footer className="chat-input-bar">
        {messages[messages.length - 1]?.role === 'tutor' &&
         messages[messages.length - 1]?.text.includes('What is') ? (
          <div className="input-wrapper">
            <textarea
              className="chat-textarea"
              rows={1}
              placeholder="Type your answer or reasoning…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSending}
            />
            <button
              className="send-button"
              onClick={sendMessage}
              disabled={isSending || !input.trim()}
              aria-label="Send"
            >
              ➤
            </button>
          </div>
        ) : messages[messages.length - 1]?.text.includes('complete') ? (
          <p className="session-done">Session complete. Great work!</p>
        ) : null}
      </footer>
    </div>
  );
}
