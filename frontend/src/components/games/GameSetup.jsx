import { useState } from "react";
import axios from "axios";

const GAME_META = {
  memorama: {
    icon: "🃏",
    title: "Memorama",
    description: "Match verse references to their text",
    countLabel: "Number of pairs",
    countOptions: [4, 6, 8],
    defaultCount: 6,
    placeholder:
      "e.g. Psalms 23, John 3, the Sermon on the Mount, the life of David…",
  },
  trivia: {
    icon: "❓",
    title: "Bible Trivia",
    description: "Multiple-choice questions on Bible knowledge",
    countLabel: "Number of questions",
    countOptions: [5, 8, 10],
    defaultCount: 8,
    placeholder:
      "e.g. Genesis 1-11, the apostle Paul, miracles of Jesus, the prophets…",
  },
};

export default function GameSetup({ gameType, token, onGenerated }) {
  const meta = GAME_META[gameType];
  const [focus, setFocus] = useState("");
  const [count, setCount] = useState(meta.defaultCount);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGenerate = async () => {
    const trimmed = focus.trim();
    if (!trimmed) {
      setError("Please describe what to focus on.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await axios.post(
        "http://localhost:8000/api/games/generate",
        { game_type: gameType, focus: trimmed, count },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      onGenerated(res.data);
    } catch (err) {
      const msg =
        err.response?.data?.detail || "Generation failed. Please try again.";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="game-setup">
      <div className="game-setup-header">
        <span className="game-setup-icon">{meta.icon}</span>
        <div>
          <h2 className="game-setup-title">{meta.title}</h2>
          <p className="game-setup-subtitle">{meta.description}</p>
        </div>
      </div>

      <div className="game-setup-form">
        <label className="game-setup-label">
          What should the game focus on?
          <textarea
            className="game-setup-textarea"
            rows={3}
            placeholder={meta.placeholder}
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            disabled={loading}
          />
        </label>

        <label className="game-setup-label">
          {meta.countLabel}
          <div className="game-setup-count-row">
            {meta.countOptions.map((n) => (
              <button
                key={n}
                className={`game-setup-count-btn${count === n ? " active" : ""}`}
                onClick={() => setCount(n)}
                disabled={loading}
              >
                {n}
              </button>
            ))}
          </div>
        </label>

        {error && <p className="game-setup-error">{error}</p>}

        <button
          className="game-setup-generate-btn"
          onClick={handleGenerate}
          disabled={loading || !focus.trim()}
        >
          {loading ? (
            <span className="game-setup-loading">
              <span className="game-setup-spinner" />
              Generating with AI…
            </span>
          ) : (
            "✨ Generate Game"
          )}
        </button>

        {loading && (
          <p className="game-setup-hint">
            The AI is crafting your personalized game — this takes a few
            seconds.
          </p>
        )}
      </div>
    </div>
  );
}
