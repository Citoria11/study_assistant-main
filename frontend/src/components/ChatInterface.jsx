import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { v4 as uuidv4 } from "uuid";

const API_BASE = import.meta.env.VITE_API_URL || "";

const SUGGESTIONS = [
  "Help me memorize John 3:16",
  "Coach me through Psalm 23",
  "Find verses about faith in Romans",
  "What does Proverbs 3:5-6 say?",
  "I want to memorize the Beatitudes",
  "Show me verses about forgiveness",
  "Memorize Philippians 4:13 with me",
  "Find all verses about love in 1 Corinthians 13",
];

// Thread ID is scoped per user: defaults to their user_id (resumes conversation
// across login/logout), rotates to a new UUID on "Clear" (stored in localStorage).
function getThreadIdForUser(userId) {
  const stored = localStorage.getItem(`thread_id_${userId}`);
  if (stored) return stored;
  // First time: use the user_id itself as the thread so the conversation is
  // immediately tied to the user in Postgres checkpoints.
  return userId;
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ── Verse-reference link renderer ──────────────────────────────────────────
// Matches: optional leading 1/2/3, a capitalised word, optional "of Word",
// optional second capitalised word, then chapter:verse
// e.g. Genesis 1:1 | 1 Samuel 17:4 | Song of Solomon 1:1 | Psalm 23:1
const VERSE_RE =
  /\b((?:(?:1|2|3)\s+)?[A-Z][a-z]+(?:\s+of\s+[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?)\s+(\d+):(\d+)\b/g;

function renderMessage(text, onNavigateToBook) {
  if (!onNavigateToBook || !text) return text;
  const parts = [];
  let lastIndex = 0;
  let match;
  // Reset lastIndex before running
  VERSE_RE.lastIndex = 0;
  while ((match = VERSE_RE.exec(text)) !== null) {
    const [fullMatch, book, chStr, vStr] = match;
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const chapter = parseInt(chStr, 10);
    const verse = parseInt(vStr, 10);
    parts.push(
      <button
        key={match.index}
        className="chat-verse-link"
        onClick={() => onNavigateToBook({ book, chapter, verse })}
        title={`Open ${book} ${chapter}:${verse} in Books`}
      >
        📖 {fullMatch}
      </button>
    );
    lastIndex = match.index + fullMatch.length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  // No refs found — return plain string so nothing changes visually
  return parts.length > 1 ? <>{parts}</> : text;
}

// Parse a standalone verse reference string like "Genesis 1:2" or "1 Samuel 17:4"
function parseVerseRef(str) {
  if (!str) return null;
  const re = /^((?:(?:1|2|3)\s+)?[A-Z][a-z]+(?:\s+of\s+[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?)\s+(\d+):(\d+)$/;
  const m = str.trim().match(re);
  if (!m) return null;
  return { book: m[1], chapter: parseInt(m[2], 10), verse: parseInt(m[3], 10) };
}

// ── Flashcard component ──────────────────────────────────────────────────────

function FlashcardSet({ caption, cards, onNavigateToBook, onMarkStudied }) {
  const [flipped, setFlipped] = useState(new Set());
  const [marked, setMarked] = useState(false);

  const toggleFlip = (i) =>
    setFlipped((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  const handleMarkStudied = () => {
    if (marked) return;
    setMarked(true);
    const verses = cards.map((c) => c.front).join(", ");
    onMarkStudied?.(verses, caption);
  };

  return (
    <div className="flashcard-set">
      {caption && (
        <p className="flashcard-caption">
          {renderMessage(caption, onNavigateToBook)}
        </p>
      )}
      <div className="flashcard-row">
        {cards.map((card, i) => {
          const ref = parseVerseRef(card.front);
          return (
            <div key={i} className="flashcard-wrapper">
              <div
                className={`flashcard${flipped.has(i) ? " flipped" : ""}`}
                onClick={() => toggleFlip(i)}
                role="button"
                aria-label={`Card ${i + 1} — tap to flip`}
              >
                <div className="flashcard-inner">
                  <div className="flashcard-face flashcard-front">
                    <span className="flashcard-face-label">tap to reveal</span>
                    <span className="flashcard-face-content">{card.front}</span>
                  </div>
                  <div className="flashcard-face flashcard-back">
                    <span className="flashcard-face-label">tap to flip back</span>
                    <span className="flashcard-face-content">{card.back}</span>
                  </div>
                </div>
              </div>
              {ref && onNavigateToBook && (
                <button
                  className="flashcard-open-btn"
                  onClick={() => onNavigateToBook(ref)}
                  title={`Open ${card.front} in Books`}
                >
                  📖 Open in Books
                </button>
              )}
            </div>
          );
        })}
      </div>
      {onMarkStudied && (
        <div className="flashcard-mark-studied-row">
          {marked ? (
            <span className="flashcard-studied-badge">✓ Logged to Notebook</span>
          ) : (
            <button className="flashcard-mark-studied-btn" onClick={handleMarkStudied}>
              ✓ Mark as Studied
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Verse follow-up actions (shown below each flashcard response) ───────────

const GAME_DEFAULTS = { memorama: 6, trivia: 8 };

// Build a game focus string. Single verse refs (Book Ch:V) are expanded to
// their full chapter so the LLM has enough material to generate the required
// number of pairs/questions.
function buildGameFocus(cards) {
  let expanded = false;
  const parts = cards.map((c) => {
    const ref = parseVerseRef(c.front);
    if (ref) {
      expanded = true;
      return `${ref.book} chapter ${ref.chapter} (especially ${c.front})`;
    }
    return c.front;
  });
  // Deduplicate (multiple verses from the same chapter collapse nicely)
  const unique = [...new Set(parts)];
  return { focus: unique.join(", "), expanded };
}

function VerseActions({ cards, onMemorize, onLaunchGame, token }) {
  const [loadingGame, setLoadingGame] = useState(null); // "memorama" | "trivia" | null
  const [gameError, setGameError] = useState(null);
  const { focus, expanded } = buildGameFocus(cards);
  const plainRefs = cards.map((c) => c.front).join(", ");

  const handleGame = async (gameType) => {
    setLoadingGame(gameType);
    setGameError(null);
    try {
      const res = await axios.post(
        `${API_BASE}/api/games/generate`,
        { game_type: gameType, focus, count: GAME_DEFAULTS[gameType] },
        token ? { headers: { Authorization: `Bearer ${token}` } } : {},
      );
      onLaunchGame({ gameType, gameData: res.data, expanded });
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Generation failed.";
      setGameError(typeof detail === "string" ? detail : JSON.stringify(detail));
      console.error("[VerseActions] game generate error:", err);
    } finally {
      setLoadingGame(null);
    }
  };

  return (
    <div className="verse-actions">
      <span className="verse-actions-label">What would you like to do?</span>
      {expanded && (
        <span className="verse-actions-notice">
          ℹ️ Game will use the full chapter for variety, not just the single verse.
        </span>
      )}
      <div className="verse-actions-row">
        <button
          className="verse-action-btn verse-action-memorize"
          onClick={() => onMemorize(cards.map((c) => c.front).join(", "))}
        >
          🧠 Memorize this
        </button>
        <button
          className="verse-action-btn verse-action-game"
          onClick={() => handleGame("memorama")}
          disabled={!!loadingGame}
        >
          {loadingGame === "memorama" ? "Generating…" : "🃏 Memorama"}
        </button>
        <button
          className="verse-action-btn verse-action-game"
          onClick={() => handleGame("trivia")}
          disabled={!!loadingGame}
        >
          {loadingGame === "trivia" ? "Generating…" : "❓ Trivia Quiz"}
        </button>
      </div>
      {gameError && (
        <span className="verse-actions-error">⚠ {gameError}</span>
      )}
    </div>
  );
}

export default function ChatInterface({ userId, token, onNavigateToBook, onLaunchGame, onAchievementLogged }) {
  const WELCOME = {
    id: "welcome",
    role: "assistant",
    type: "text",
    content:
      "Welcome! Ask me to look up a verse or passage — or say you want to memorize something and I'll coach you through it.",
    cards: [],
    time: formatTime(new Date()),
  };

  const [messages, setMessages] = useState([WELCOME]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reciteMode, setReciteMode] = useState(false);
  const [reciteReady, setReciteReady] = useState(false);
  const threadId = useRef(getThreadIdForUser(userId));
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const logAchievement = async (data) => {
    try {
      await axios.post(
        `${API_BASE}/api/notebook/achievement`,
        data,
        token ? { headers: { Authorization: `Bearer ${token}` } } : {},
      );
      onAchievementLogged?.();
    } catch (e) {
      console.error("[achievement] failed to log:", e);
    }
  };

  // Restore conversation history from the LangGraph checkpoint on mount
  useEffect(() => {
    axios
      .get(`${API_BASE}/api/agent/history/${threadId.current}`)
      .then((r) => {
        const hist = r.data.messages;
        if (hist && hist.length > 0) {
          setMessages(
            hist.map((m) => ({
              id: uuidv4(),
              role: m.role,
              type: m.type || "text",
              content: m.content,
              cards: m.cards || [],
              time: "",   // timestamps not stored server-side
            }))
          );
        }
      })
      .catch(() => {
        // Silently keep the welcome message if history can't be loaded
      })
      .finally(() => setHistoryLoaded(true));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const hasUserMessages = messages.some((m) => m.role === "user");

  const sendMessage = async (text = input) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    const resolvedText = trimmed;
    // Exit recite mode the moment the user sends their attempt
    setReciteMode(false);
    setReciteReady(false);

    const userMsg = {
      id: uuidv4(),
      role: "user",
      type: "text",
      content: resolvedText,
      cards: [],
      time: formatTime(new Date()),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const response = await axios.post(`${API_BASE}/api/agent/invoke`, {
        message: resolvedText,
        thread_id: threadId.current,
      });

      const assistantMsg = {
        id: uuidv4(),
        role: "assistant",
        type: response.data.type || "text",
        content: response.data.text,
        cards: response.data.cards || [],
        verseDisplay: response.data.verse_display || "",
        reciteMode: response.data.recite_mode || false,
        route: response.data.route || "bible_search",
        time: formatTime(new Date()),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      if (response.data.recite_mode) { setReciteMode(true); setReciteReady(false); }

      // Auto-log achievement if the study_coach detected session completion
      if (response.data.achievement) {
        const a = response.data.achievement;
        logAchievement({
          achievement_type: "memorization",
          topic: a.topic,
          technique: a.technique,
          summary: a.summary,
        });
      }
    } catch (err) {
      const detail =
        err.response?.data?.detail || err.message || "Unknown error";
      setError(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  };

  const clearConversation = async () => {
    if (!window.confirm("Clear this conversation and start fresh?")) return;
    try {
      await axios.delete(
        `${API_BASE}/api/agent/checkpointer/${threadId.current}`,
      );
    } catch {
      // Ignore errors on clear — still reset UI
    }
    // Rotate to a new thread scoped to this user
    const newId = uuidv4();
    localStorage.setItem(`thread_id_${userId}`, newId);
    threadId.current = newId;
    setMessages([{ ...WELCOME, id: uuidv4(), content: "Conversation cleared. How can I help you?" }]);
    setError(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-toolbar">
        <button className="clear-btn" onClick={clearConversation}>
          Clear
        </button>
      </div>

      <div className="chat-toolbar-label">📖 Bible Study</div>

      <div className="messages-area">
        {(() => {
          const lastReciteIdx = messages.reduce((acc, m, i) => (m.reciteMode ? i : acc), -1);
          return messages.map((msg, index) => {
            const isReciteTarget = reciteMode && index === lastReciteIdx;
            const shouldBlur = isReciteTarget && reciteReady;
            return (
              <div key={msg.id} className={`message ${msg.role}`}>
                {msg.role === "assistant" && msg.cards && msg.cards.length > 0 ? (
                  <>
                    <FlashcardSet
                      caption={msg.content}
                      cards={msg.cards}
                      onNavigateToBook={onNavigateToBook}
                      onMarkStudied={msg.route !== "study_coach" ? (verses, caption) =>
                        logAchievement({
                          achievement_type: "memorization",
                          topic: verses,
                          technique: "flashcards",
                          summary: caption || "",
                        }) : undefined
                      }
                    />
                    {onLaunchGame && msg.route !== "study_coach" && (
                      <VerseActions
                        cards={msg.cards}
                        token={token}
                        onMemorize={(refs) => sendMessage(`Help me memorize ${refs}`)}
                        onLaunchGame={onLaunchGame}
                      />
                    )}
                    {isReciteTarget && !reciteReady && (
                      <button className="recite-ready-btn" onClick={() => setReciteReady(true)}>
                        ✅ I'm ready — hide and let me recite
                      </button>
                    )}
                  </>
                ) : (
                  <>
                    {msg.verseDisplay && (
                      <div className={`verse-display-block${shouldBlur ? " recite-blur" : ""}`}>{msg.verseDisplay}</div>
                    )}
                    <div className={`message-bubble${shouldBlur ? " recite-blur" : ""}`}>
                      {renderMessage(msg.content, onNavigateToBook)}
                    </div>
                    {isReciteTarget && !reciteReady && (
                      <button className="recite-ready-btn" onClick={() => setReciteReady(true)}>
                        ✅ I'm ready — hide and let me recite
                      </button>
                    )}
                  </>
                )}
                <span className="message-time">{msg.time}</span>
              </div>
            );
          });
        })()}
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
          <p className="mnemonics-suggestions-label">Explore a topic:</p>
          <div className="mnemonics-chips">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                className="mnemonics-chip"
                onClick={() => sendMessage(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {reciteReady && (
        <div className="recite-banner">
          <span>🙈 Verse hidden — type it from memory below</span>
          <button className="recite-cancel" onClick={() => setReciteReady(false)}>Show verse</button>
        </div>
      )}

      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          className="chat-input"
          rows={1}
          placeholder="Ask a question about Scripture…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
