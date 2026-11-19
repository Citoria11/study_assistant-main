import { useState, useEffect, useCallback } from "react";

function shuffle(array) {
  const arr = [...array];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function buildDeck(pairs) {
  const cards = [];
  pairs.forEach((pair) => {
    cards.push({
      uid: `${pair.id}-ref`,
      pairId: pair.id,
      type: "reference",
      content: pair.reference,
    });
    cards.push({
      uid: `${pair.id}-txt`,
      pairId: pair.id,
      type: "text",
      content: pair.text,
    });
  });
  return shuffle(cards);
}

export default function Memorama({ pairs, onNewGame, onComplete }) {
  const [deck, setDeck] = useState([]);
  const [flipped, setFlipped] = useState([]); // indices of currently face-up cards (max 2)
  const [matched, setMatched] = useState(new Set());
  const [moves, setMoves] = useState(0);
  const [locked, setLocked] = useState(false); // prevent clicking while checking pair
  const [won, setWon] = useState(false);

  const init = useCallback(() => {
    setDeck(buildDeck(pairs));
    setFlipped([]);
    setMatched(new Set());
    setMoves(0);
    setLocked(false);
    setWon(false);
  }, [pairs]);

  useEffect(() => {
    init();
  }, [init]);

  // Check for win
  useEffect(() => {
    if (matched.size > 0 && matched.size === pairs.length) {
      setWon(true);
      onComplete?.({ pairs: pairs.length, moves });
    }
  }, [matched, pairs.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFlip = (index) => {
    if (locked) return;
    if (flipped.includes(index)) return;
    if (matched.has(deck[index].pairId)) return;

    const newFlipped = [...flipped, index];
    setFlipped(newFlipped);

    if (newFlipped.length === 2) {
      setMoves((m) => m + 1);
      setLocked(true);

      const [a, b] = newFlipped;
      if (deck[a].pairId === deck[b].pairId) {
        // Match found
        setTimeout(() => {
          setMatched((prev) => new Set([...prev, deck[a].pairId]));
          setFlipped([]);
          setLocked(false);
        }, 600);
      } else {
        // No match — flip back
        setTimeout(() => {
          setFlipped([]);
          setLocked(false);
        }, 1000);
      }
    }
  };

  const isFaceUp = (index) =>
    flipped.includes(index) || matched.has(deck[index]?.pairId);

  const isMatched = (index) => matched.has(deck[index]?.pairId);

  return (
    <div className="memorama-wrapper">
      <div className="memorama-header">
        <h2 className="memorama-title">Memorama</h2>
        <div className="memorama-stats">
          <span>
            Pairs: {matched.size} / {pairs.length}
          </span>
          <span>Moves: {moves}</span>
          <button className="memorama-reset-btn" onClick={onNewGame}>
            New Game
          </button>
        </div>
      </div>

      {won && (
        <div className="memorama-win">
          🎉 You matched all {pairs.length} pairs in {moves} moves!
          <button className="memorama-reset-btn" onClick={onNewGame}>
            Play Again
          </button>
        </div>
      )}

      <div
        className="memorama-grid"
        style={{ gridTemplateColumns: `repeat(auto-fill, minmax(140px, 1fr))` }}
      >
        {deck.map((card, index) => (
          <div
            key={card.uid}
            className={`memorama-card ${isFaceUp(index) ? "face-up" : ""} ${isMatched(index) ? "matched" : ""}`}
            onClick={() => handleFlip(index)}
          >
            <div className="memorama-card-inner">
              <div className="memorama-card-front">✝</div>
              <div className={`memorama-card-back ${card.type}`}>
                {card.content}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
