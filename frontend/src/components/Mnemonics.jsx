import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { v4 as uuidv4 } from "uuid";

const API_BASE = import.meta.env.VITE_API_URL || "";

const SUGGESTIONS = [
  "Help me memorize John 3:16",
  "Give me a mnemonic for the books of the New Testament",
  "Help me memorize Psalm 23",
  "I need to memorize the 10 Commandments",
  "Help me remember the order of the Gospels",
];

function getOrCreateThreadId(key) {
  let id = localStorage.getItem(key);
  if (!id) {
    id = uuidv4();
    localStorage.setItem(key, id);
  }
  return id;
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Render assistant text with basic markdown-style bold (**text**)
function FormattedText({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <span>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </span>
  );
}

export default function Mnemonics() {
  const [messages, setMessages] = useState([
    {
      id: uuidv4(),
      role: "assistant",
      content:
        "Hello! I'm your Bible Study Coach. Give me a verse, passage, or topic you want to work on — I'll guide you through memorization, build study aids, and coach you step by step. What are we tackling today?",
      time: formatTime(new Date()),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const threadId = useRef(getOrCreateThreadId("mnemonics_thread_id"));
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [
      ...prev,
      {
        id: uuidv4(),
        role: "user",
        content: trimmed,
        time: formatTime(new Date()),
      },
    ]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await axios.post(`${API_BASE}/api/mnemonics/invoke`, {
        message: trimmed,
        thread_id: threadId.current,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          role: "assistant",
          content: res.data.response,
          time: formatTime(new Date()),
        },
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const hasUserMessages = messages.some((m) => m.role === "user");

  return (
    <div className="chat-container">
      <div className="chat-toolbar">
        <span className="mnemonics-toolbar-label">🧠 Study Coach</span>
        <button
          className="clear-btn"
          onClick={() => {
            const newId = uuidv4();
            localStorage.setItem("mnemonics_thread_id", newId);
            threadId.current = newId;
            setMessages([
              {
                id: uuidv4(),
                role: "assistant",
                content:
                  "Session cleared! Give me a verse or passage and I'll create new memory aids for you.",
                time: formatTime(new Date()),
              },
            ]);
            setError(null);
          }}
        >
          Clear
        </button>
      </div>

      <div className="messages-area">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role}`}>
            <div className="message-bubble">
              {msg.role === "assistant" ? (
                <FormattedText text={msg.content} />
              ) : (
                msg.content
              )}
            </div>
            <span className="message-time">{msg.time}</span>
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="typing-indicator">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {!hasUserMessages && (
        <div className="mnemonics-suggestions">
          <p className="mnemonics-suggestions-label">Try one of these:</p>
          <div className="mnemonics-chips">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                className="mnemonics-chip"
                onClick={() => send(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-banner">Error: {error}</div>}

      <div className="chat-input-area">
        <textarea
          className="chat-input"
          rows={1}
          placeholder="Type a verse, passage, or list to memorize…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
