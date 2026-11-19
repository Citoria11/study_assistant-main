import { useState, useEffect } from "react";
import axios from "axios";
import GamePicker from "./games/GamePicker";
import GameSetup from "./games/GameSetup";
import Memorama from "./games/Memorama";
import TriviaQuiz from "./games/TriviaQuiz";

const API_BASE = import.meta.env.VITE_API_URL || "";

function deriveTopic(gameData) {
  if (!gameData) return null;
  if (gameData.pairs?.[0]?.reference) return gameData.pairs[0].reference;
  if (gameData.questions?.[0]?.reference) return gameData.questions[0].reference;
  return null;
}

export default function Games({ token, gameTarget, onGameTargetConsumed, onAchievementLogged }) {
  const [activeGame, setActiveGame] = useState(null); // "memorama" | "trivia" | null
  const [gameData, setGameData] = useState(null); // generated content from LLM
  const [expandedNotice, setExpandedNotice] = useState(false);

  // Auto-start when navigated from Chat with pre-generated game data
  useEffect(() => {
    if (!gameTarget) return;
    setActiveGame(gameTarget.gameType);
    setGameData(gameTarget.gameData);
    setExpandedNotice(gameTarget.expanded || false);
    onGameTargetConsumed?.();
  }, [gameTarget]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleBack = () => {
    setExpandedNotice(false);
    if (gameData) {
      setGameData(null);
    } else {
      setActiveGame(null);
    }
  };

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

  return (
    <div className="games-container">
      {activeGame && (
        <button className="game-back-btn" onClick={handleBack}>
          ← Back
        </button>
      )}

      {expandedNotice && gameData && (
        <div className="game-expanded-notice">
          ℹ️ Content was drawn from the surrounding chapter to provide enough variety for this game.
        </div>
      )}

      {!activeGame && <GamePicker onSelect={setActiveGame} />}

      {activeGame && !gameData && (
        <GameSetup
          gameType={activeGame}
          token={token}
          onGenerated={setGameData}
        />
      )}

      {activeGame === "memorama" && gameData && (
        <Memorama
          pairs={gameData.pairs}
          onNewGame={() => setGameData(null)}
          onComplete={({ pairs, moves }) =>
            logAchievement({
              achievement_type: "memorama",
              topic: deriveTopic(gameData),
              pairs,
              moves,
            })
          }
        />
      )}
      {activeGame === "trivia" && gameData && (
        <TriviaQuiz
          questions={gameData.questions}
          onNewGame={() => setGameData(null)}
          onComplete={({ score, total, pct }) =>
            logAchievement({
              achievement_type: "trivia",
              topic: deriveTopic(gameData),
              score,
              total,
              pct,
            })
          }
        />
      )}
    </div>
  );
}
