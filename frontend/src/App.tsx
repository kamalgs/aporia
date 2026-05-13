import { useState, useRef, useEffect, FormEvent } from 'react';
import './App.css';
import { createLearner, createSession, sendTurn, endSession } from './api';

type Phase = 'welcome' | 'chat' | 'ended';

interface Message {
  id: string;
  role: 'tutor' | 'learner';
  text: string;
  onTarget?: boolean;
  time: string;
}

function now() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function tutorMsg(text: string): Message {
  return { id: crypto.randomUUID(), role: 'tutor', text, time: now() };
}

function learnerMsg(text: string, onTarget?: boolean): Message {
  return { id: crypto.randomUUID(), role: 'learner', text, onTarget, time: now() };
}

export default function App() {
  const [phase, setPhase] = useState<Phase>('welcome');
  const [name, setName] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isWaiting, setIsWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isWaiting]);

  useEffect(() => {
    if (phase === 'chat') inputRef.current?.focus();
  }, [phase]);

  async function handleStart(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setIsWaiting(true);
    setError(null);
    try {
      const learner = await createLearner(trimmed);
      const session = await createSession(learner.id);
      setSessionId(session.id);
      // Auto-send a start signal so the session role fires and the learner sees a problem immediately
      const result = await sendTurn(session.id, "Let's start!");
      setMessages([tutorMsg(result.utterance)]);
      setPhase('chat');
    } catch (err) {
      setError('Could not start session. Is the server running?');
    } finally {
      setIsWaiting(false);
    }
  }

  async function handleSend() {
    if (!sessionId || !input.trim() || isWaiting) return;
    const text = input.trim();
    setInput('');
    setIsWaiting(true);
    setMessages((m) => [...m, learnerMsg(text)]);
    try {
      const result = await sendTurn(sessionId, text);
      setMessages((m) => {
        const updated = [...m];
        const lastLearner = [...updated].reverse().find((x) => x.role === 'learner');
        if (lastLearner) lastLearner.onTarget = result.turn_signal.on_target;
        return [...updated, tutorMsg(result.utterance)];
      });
    } catch {
      setMessages((m) => [...m, tutorMsg('Something went wrong. Please try again.')]);
    } finally {
      setIsWaiting(false);
    }
  }

  async function handleEnd() {
    if (!sessionId) return;
    try {
      await endSession(sessionId);
    } catch {
      // best-effort
    }
    setMessages((m) => [...m, tutorMsg('Great work today! Session complete.')]);
    setPhase('ended');
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (phase === 'welcome') {
    return (
      <div className="chat-container">
        <header className="chat-header">
          <div className="avatar">T</div>
          <div className="header-info">
            <h1>AI Tutor</h1>
            <span className="status">Ready</span>
          </div>
        </header>
        <main className="welcome-view">
          <div className="welcome-card">
            <h2>Welcome!</h2>
            <p>Practice math with your AI tutor.</p>
            <form onSubmit={handleStart} className="welcome-form">
              <label htmlFor="learner-name">What's your name?</label>
              <input
                id="learner-name"
                type="text"
                className="name-input"
                placeholder="Enter your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                disabled={isWaiting}
              />
              {error && <p className="error-msg">{error}</p>}
              <button
                type="submit"
                className="start-button"
                disabled={isWaiting || !name.trim()}
              >
                {isWaiting ? 'Starting…' : 'Start Learning'}
              </button>
            </form>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <header className="chat-header">
        <div className="avatar">{name.charAt(0).toUpperCase() || 'T'}</div>
        <div className="header-info">
          <h1>AI Tutor</h1>
          <span className="status">{phase === 'ended' ? 'Session ended' : 'online'}</span>
        </div>
        {phase === 'chat' && (
          <button className="end-button" onClick={handleEnd} title="End session">
            End
          </button>
        )}
      </header>

      <main className="chat-messages" aria-label="conversation">
        {messages.map((m) => (
          <article key={m.id} className={`message ${m.role}`}>
            <div className="message-bubble">
              <p>{m.text}</p>
            </div>
            <div className="message-footer">
              <time className="message-time">{m.time}</time>
              {m.role === 'learner' && m.onTarget !== undefined && (
                <span className={`on-target-icon ${m.onTarget ? 'correct' : 'incorrect'}`}>
                  {m.onTarget ? '✓' : '✗'}
                </span>
              )}
            </div>
          </article>
        ))}
        {isWaiting && (
          <article className="message tutor">
            <div className="message-bubble typing">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </article>
        )}
        <div ref={endRef} />
      </main>

      <footer className="chat-input-bar">
        {phase === 'ended' ? (
          <p className="session-done">Session complete. Well done, {name}!</p>
        ) : (
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              className="chat-textarea"
              rows={1}
              placeholder="Type your answer…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isWaiting}
            />
            <button
              className="send-button"
              onClick={handleSend}
              disabled={isWaiting || !input.trim()}
              aria-label="Send"
            >
              ➤
            </button>
          </div>
        )}
      </footer>
    </div>
  );
}
