import { useState, useCallback, useEffect } from "react";

function shuffle(array) {
  const arr = [...array];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export default function TriviaQuiz({ questions: rawQuestions, onNewGame, onComplete }) {
  const [questions] = useState(() => shuffle(rawQuestions));
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState(null); // option the user clicked
  const [score, setScore] = useState(0);
  const [finished, setFinished] = useState(false);

  const question = questions[current];
  const isCorrect = selected === question?.answer;
  const answered = selected !== null;

  const handleSelect = (option) => {
    if (answered) return;
    setSelected(option);
    if (option === question.answer) setScore((s) => s + 1);
  };

  const handleNext = useCallback(() => {
    if (current + 1 >= questions.length) {
      setFinished(true);
    } else {
      setCurrent((c) => c + 1);
      setSelected(null);
    }
  }, [current, questions.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fire onComplete after finished so score state is fully committed
  useEffect(() => {
    if (!finished) return;
    const total = questions.length;
    const pct = Math.round((score / total) * 100);
    onComplete?.({ score, total, pct });
  }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRestart = () => {
    setCurrent(0);
    setSelected(null);
    setScore(0);
    setFinished(false);
  };

  if (finished) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div className="trivia-wrapper">
        <div className="trivia-result">
          <div className="trivia-result-icon">
            {pct >= 80 ? "🏆" : pct >= 50 ? "📖" : "🙏"}
          </div>
          <h2>Quiz Complete!</h2>
          <p className="trivia-result-score">
            {score} / {questions.length} correct ({pct}%)
          </p>
          <p className="trivia-result-msg">
            {pct === 100
              ? "Perfect score! Outstanding knowledge of Scripture!"
              : pct >= 80
                ? "Excellent! Keep studying God's Word."
                : pct >= 50
                  ? "Good effort! There's always more to discover in Scripture."
                  : "Keep reading — God's Word has treasures waiting for you."}
          </p>
          <button className="trivia-btn primary" onClick={onNewGame}>
            Play Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="trivia-wrapper">
      <div className="trivia-header">
        <span className="trivia-progress">
          Question {current + 1} of {questions.length}
        </span>
        <span className="trivia-score">Score: {score}</span>
      </div>

      <div className="trivia-progress-bar">
        <div
          className="trivia-progress-fill"
          style={{ width: `${(current / questions.length) * 100}%` }}
        />
      </div>

      <div className="trivia-card">
        <p className="trivia-question">{question.question}</p>

        <div className="trivia-options">
          {question.options.map((opt) => {
            let cls = "trivia-option";
            if (answered) {
              if (opt === question.answer) cls += " correct";
              else if (opt === selected) cls += " wrong";
            }
            return (
              <button
                key={opt}
                className={cls}
                onClick={() => handleSelect(opt)}
                disabled={answered}
              >
                {opt}
              </button>
            );
          })}
        </div>

        {answered && (
          <div className={`trivia-feedback ${isCorrect ? "correct" : "wrong"}`}>
            <strong>{isCorrect ? "✓ Correct!" : "✗ Incorrect."}</strong>{" "}
            {question.explanation}
          </div>
        )}

        {answered && (
          <button
            className="trivia-btn primary trivia-next"
            onClick={handleNext}
          >
            {current + 1 >= questions.length
              ? "See Results"
              : "Next Question →"}
          </button>
        )}
      </div>
    </div>
  );
}
