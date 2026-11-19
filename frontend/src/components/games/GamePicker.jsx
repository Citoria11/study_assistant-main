const GAMES = [
  {
    id: "memorama",
    title: "Memorama",
    icon: "🃏",
    description:
      "Match Bible verse references to their text. Flip cards and find all pairs!",
    tag: "Memory",
  },
  {
    id: "trivia",
    title: "Bible Trivia",
    icon: "❓",
    description:
      "Test your knowledge of Bible characters, events, and teachings.",
    tag: "Quiz",
  },
];

export default function GamePicker({ onSelect }) {
  return (
    <div className="game-picker">
      <h2 className="game-picker-title">Choose a Game</h2>
      <div className="game-picker-grid">
        {GAMES.map((game) => (
          <button
            key={game.id}
            className="game-card"
            onClick={() => onSelect(game.id)}
          >
            <span className="game-card-icon">{game.icon}</span>
            <span className="game-card-tag">{game.tag}</span>
            <h3 className="game-card-title">{game.title}</h3>
            <p className="game-card-desc">{game.description}</p>
            <span className="game-card-play">Play →</span>
          </button>
        ))}
      </div>
    </div>
  );
}
