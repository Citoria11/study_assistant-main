import { useState, useEffect } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "";

function getToken() { return localStorage.getItem("auth_token"); }
function authHeaders() { return { Authorization: `Bearer ${getToken()}` }; }
function todayISO() { return new Date().toISOString().slice(0, 10); }
function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

export default function Notebook({ refreshKey, onGoalChanged }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [savedFlash, setSavedFlash] = useState(false);

  const [todayEntry, setTodayEntry] = useState(null);

  // Form fields — always start empty; saved data shown in top summary
  const [notes, setNotes] = useState("");
  const [feedback, setFeedback] = useState("");
  const [newQuestion, setNewQuestion] = useState("");

  // Goal-picker state
  const [books, setBooks] = useState([]);
  const [goalBook, setGoalBook] = useState("");
  const [goalChapter, setGoalChapter] = useState("");
  const [totalChapters, setTotalChapters] = useState(0);
  const [goalSuggestions, setGoalSuggestions] = useState(null);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [selectedMilestones, setSelectedMilestones] = useState(new Set());
  const [settingGoal, setSettingGoal] = useState(false);

  useEffect(() => { fetchEntries(); fetchBooks(); }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchBooks() {
    try {
      const res = await axios.get(`${API_BASE}/api/books/`);
      setBooks(res.data.books);
    } catch { /* silently ignore */ }
  }

  async function onBookChange(book) {
    setGoalBook(book);
    setGoalChapter("");
    setTotalChapters(0);
    setGoalSuggestions(null);
    if (book) {
      try {
        const res = await axios.get(`${API_BASE}/api/books/${encodeURIComponent(book)}/1`);
        setTotalChapters(res.data.total_chapters);
      } catch { /* ignore */ }
    }
  }

  async function getSuggestions() {
    setLoadingSuggestions(true);
    setGoalSuggestions(null);
    try {
      const res = await axios.post(
        `${API_BASE}/api/notebook/goal/suggest`,
        { book: goalBook, chapter: Number(goalChapter) },
        { headers: authHeaders() }
      );
      setGoalSuggestions(res.data.milestones);
      setSelectedMilestones(new Set(res.data.milestones.map((_, i) => i)));
    } catch { setError("Could not get milestone suggestions."); }
    finally { setLoadingSuggestions(false); }
  }

  async function setGoalFromSuggestions() {
    setSettingGoal(true);
    try {
      const milestones = goalSuggestions.filter((_, i) => selectedMilestones.has(i));
      const entry = await ensureToday();
      const res = await axios.patch(
        `${API_BASE}/api/notebook/${entry.id}`,
        { daily_goal: `${goalBook} ${goalChapter}`, goal_milestones: milestones, goal_completed: [] },
        { headers: authHeaders() }
      );
      const updated = res.data;
      setTodayEntry(updated);
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
      setGoalSuggestions(null);
      onGoalChanged?.();
    } catch { setError("Could not set goal."); }
    finally { setSettingGoal(false); }
  }

  async function toggleMilestone(idx) {
    if (!todayEntry) return;
    const completed = todayEntry.goal_completed || [];
    const newCompleted = completed.includes(idx)
      ? completed.filter(i => i !== idx)
      : [...completed, idx];
    try {
      const res = await axios.patch(
        `${API_BASE}/api/notebook/${todayEntry.id}`,
        { goal_completed: newCompleted },
        { headers: authHeaders() }
      );
      const updated = res.data;
      setTodayEntry(updated);
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
    } catch { setError("Could not update milestone."); }
  }

  async function clearGoal() {
    if (!todayEntry) return;
    try {
      const res = await axios.patch(
        `${API_BASE}/api/notebook/${todayEntry.id}`,
        { daily_goal: null, goal_milestones: null, goal_completed: [] },
        { headers: authHeaders() }
      );
      const updated = res.data;
      setTodayEntry(updated);
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
      setGoalBook(""); setGoalChapter(""); setGoalSuggestions(null);
      onGoalChanged?.();
    } catch { setError("Could not clear goal."); }
  }

  async function fetchEntries() {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/notebook/`, { headers: authHeaders() });
      const data = res.data;
      setEntries(data);
      const te = data.find(e => e.session_date.slice(0, 10) === todayISO()) || null;
      if (te) setTodayEntry(te);
    } catch { setError("Could not load notebook."); }
    finally { setLoading(false); }
  }

  async function ensureToday() {
    if (todayEntry) return todayEntry;
    const res = await axios.post(
      `${API_BASE}/api/notebook/`,
      { session_date: todayISO() },
      { headers: authHeaders() }
    );
    const created = res.data;
    setEntries(prev => [created, ...prev]);
    setTodayEntry(created);
    return created;
  }

  async function saveToday() {
    if (!notes.trim() && !feedback.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const entry = await ensureToday();
      // Append new notes to existing
      const existingNotes = entry.notes || "";
      const newNotes = notes.trim()
        ? (existingNotes ? existingNotes + "\n\n" + notes.trim() : notes.trim())
        : existingNotes || null;
      const existingFeedback = entry.feedback || "";
      const newFeedback = feedback.trim()
        ? (existingFeedback ? existingFeedback + "\n\n" + feedback.trim() : feedback.trim())
        : existingFeedback || null;
      const payload = {
        notes: newNotes,
        feedback: newFeedback,
      };
      const res = await axios.patch(
        `${API_BASE}/api/notebook/${entry.id}`, payload, { headers: authHeaders() }
      );
      const updated = res.data;
      setTodayEntry(updated);
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
      // Clear form after save
      setNotes(""); setFeedback("");
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2500);
      onGoalChanged?.();
    } catch { setError("Could not save."); }
    finally { setSaving(false); }
  }

  async function addQuestion() {
    const trimmed = newQuestion.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      const entry = await ensureToday();
      const current = entry.unresolved_questions || [];
      const res = await axios.patch(
        `${API_BASE}/api/notebook/${entry.id}`,
        { unresolved_questions: [...current, trimmed] },
        { headers: authHeaders() }
      );
      const updated = res.data;
      setTodayEntry(updated);
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
      setNewQuestion("");
    } catch { setError("Could not add question."); }
    finally { setSaving(false); }
  }

  async function removeQuestion(entryId, qIdx) {
    const entry = entries.find(e => e.id === entryId);
    if (!entry) return;
    const updated_qs = entry.unresolved_questions.filter((_, i) => i !== qIdx);
    const res = await axios.patch(
      `${API_BASE}/api/notebook/${entryId}`,
      { unresolved_questions: updated_qs },
      { headers: authHeaders() }
    );
    const updated = res.data;
    setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
    if (todayEntry?.id === entryId) setTodayEntry(updated);
  }

  async function clearAll() {
    if (!window.confirm("Delete all notebook entries?")) return;
    await axios.delete(`${API_BASE}/api/notebook/all`, { headers: authHeaders() });
    setEntries([]);
    setTodayEntry(null);
    setNotes(""); setFeedback(""); setNewQuestion("");
    setGoalBook(""); setGoalChapter(""); setGoalSuggestions(null);
  }

  const allAchievements = entries.flatMap(e =>
    (e.achievements || []).map(a => ({ text: a, date: e.session_date }))
  );
  const allQuestions = entries.flatMap(e =>
    (e.unresolved_questions || []).map((q, i) => ({
      text: q, date: e.session_date, entryId: e.id, idx: i,
    }))
  );

  if (loading) return <div className="nb-dashboard"><p className="notebook-loading">Loading…</p></div>;

  return (
    <div className="nb-dashboard">
      {/* Header */}
      <div className="nb-header">
        <h2 className="nb-title">📓 Study Notebook</h2>
        <button className="notebook-clear-btn" onClick={clearAll}>🗑 Clear All</button>
      </div>

      {error && <div className="notebook-error">{error}</div>}

      {/* ── Top: Today's Progress Summary ── */}
      <div className="nb-today-summary">
        <div className="nb-today-summary-header">
          <span className="nb-panel-title">📅 Today's Progress</span>
          <span className="nb-panel-date">{formatDate(new Date().toISOString())}</span>
          <div className="nb-today-stats">
            <span className="nb-mini-stat">🗓 {entries.length} sessions</span>
            <span className="nb-mini-stat">🏆 {allAchievements.length} achievements</span>
            <span className="nb-mini-stat">❓ {allQuestions.length} questions</span>
          </div>
        </div>

        {todayEntry?.daily_goal && (
          <div className="nb-summary-block">
            <span className="nb-summary-block-label">🎯 Goal</span>
            <p className="nb-summary-block-text">{todayEntry.daily_goal}</p>
          </div>
        )}

        <div className="nb-progress-summary-row">
          <span className="nb-progress-summary-label">Progress</span>
          <div className="notebook-progress-bar-wrap">
            <div className="notebook-progress-bar-fill"
              style={{ width: `${Math.min(100, Math.max(0, todayEntry?.progress_score || 0))}%` }} />
          </div>
          <span className="nb-progress-summary-pct">
            {todayEntry?.daily_goal
              ? (todayEntry.progress_score != null ? `${todayEntry.progress_score}%` : "0%")
              : "—"}
          </span>
        </div>

        {todayEntry?.notes && (
          <div className="nb-summary-block">
            <span className="nb-summary-block-label">📝 Notes</span>
            <p className="nb-summary-block-text">{todayEntry.notes}</p>
          </div>
        )}
        {todayEntry?.feedback && (
          <div className="nb-summary-block">
            <span className="nb-summary-block-label">💬 Reflection</span>
            <p className="nb-summary-block-text">{todayEntry.feedback}</p>
          </div>
        )}
        {!todayEntry && (
          <p className="nb-empty-hint">No entry yet today — add notes below and save.</p>
        )}
      </div>

      {/* ── Main grid: form + feeds ── */}
      <div className="nb-grid">
        {/* Form */}
        <div className="nb-panel">
          <div className="nb-panel-header">
            <span className="nb-panel-title">📝 Add to Today</span>
            {savedFlash && <span className="nb-saved-flash">✓ Saved</span>}
          </div>

          <div className="nb-field">
            <label className="nb-label">Notes</label>
            <textarea className="notebook-textarea" rows={3}
              placeholder="What did you study today?"
              value={notes} onChange={e => setNotes(e.target.value)} />
          </div>

          <div className="nb-field">
            <label className="nb-label">Reflection</label>
            <textarea className="notebook-textarea" rows={2}
              placeholder="How did today's study go?"
              value={feedback} onChange={e => setFeedback(e.target.value)} />
          </div>

          <div className="nb-field">
            <label className="nb-label">Add a question for later</label>
            <div className="notebook-add-row">
              <input className="notebook-add-input" placeholder="Something to explore…"
                value={newQuestion} onChange={e => setNewQuestion(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addQuestion()} />
              <button className="notebook-add-btn" onClick={addQuestion}>Add</button>
            </div>
          </div>

          <button className="nb-save-btn" onClick={saveToday} disabled={saving}>
            {saving ? "Saving…" : "Save Today"}
          </button>
        </div>

        {/* Right column: feeds */}
        <div className="nb-right-col">

          {/* Today's Goal */}
          <div className="nb-panel">
            <div className="nb-panel-header">
              <span className="nb-panel-title">🎯 Today's Goal</span>
              {todayEntry?.daily_goal && (
                <button className="nb-goal-reset" onClick={clearGoal}>Change</button>
              )}
            </div>

            {!todayEntry?.daily_goal ? (
              <div className="nb-goal-picker">
                <div className="nb-field">
                  <label className="nb-label">Book</label>
                  <select className="nb-goal-select" value={goalBook}
                    onChange={e => onBookChange(e.target.value)}>
                    <option value="">— Choose a book —</option>
                    {books.map(b => <option key={b} value={b}>{b}</option>)}
                  </select>
                </div>

                {goalBook && (
                  <div className="nb-field">
                    <label className="nb-label">Chapter</label>
                    <select className="nb-goal-select" value={goalChapter}
                      onChange={e => { setGoalChapter(e.target.value); setGoalSuggestions(null); }}>
                      <option value="">— Choose a chapter —</option>
                      {Array.from({ length: totalChapters }, (_, i) => i + 1).map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                )}

                {goalBook && goalChapter && !goalSuggestions && (
                  <button className="nb-goal-set-btn" onClick={getSuggestions}
                    disabled={loadingSuggestions}>
                    {loadingSuggestions ? "Getting suggestions…" : "✨ Suggest milestones"}
                  </button>
                )}

                {goalSuggestions && (
                  <>
                    <p className="nb-label" style={{ marginTop: "0.25rem" }}>Select milestones:</p>
                    <ul className="nb-milestone-list">
                      {goalSuggestions.map((m, i) => (
                        <li key={i} className="nb-milestone-item">
                          <label>
                            <input type="checkbox" checked={selectedMilestones.has(i)}
                              onChange={() => {
                                const s = new Set(selectedMilestones);
                                s.has(i) ? s.delete(i) : s.add(i);
                                setSelectedMilestones(new Set(s));
                              }} />
                            {m}
                          </label>
                        </li>
                      ))}
                    </ul>
                    <button className="nb-goal-set-btn" onClick={setGoalFromSuggestions}
                      disabled={settingGoal || selectedMilestones.size === 0}>
                      {settingGoal ? "Setting…" : "Set Goal"}
                    </button>
                  </>
                )}
              </div>
            ) : (
              <div>
                <p className="nb-goal-title">📖 {todayEntry.daily_goal}</p>
                <ul className="nb-milestone-list">
                  {(todayEntry.goal_milestones || []).map((m, i) => {
                    const done = (todayEntry.goal_completed || []).includes(i);
                    return (
                      <li key={i} className={`nb-milestone-item${done ? " nb-milestone-done" : ""}`}>
                        <label>
                          <input type="checkbox" checked={done}
                            onChange={() => toggleMilestone(i)} />
                          {m}
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>
          <div className="nb-panel">
            <div className="nb-panel-header">
              <span className="nb-panel-title">🏆 Achievements</span>
            </div>
            {allAchievements.length === 0 ? (
              <p className="nb-empty-hint">No achievements yet — complete a game or memorize a verse!</p>
            ) : (
              <ul className="nb-feed">
                {allAchievements.map((a, i) => (
                  <li key={i} className="nb-feed-item">
                    <span className="nb-feed-text">{a.text}</span>
                    <span className="nb-feed-date">{formatDate(a.date)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="nb-panel">
            <div className="nb-panel-header">
              <span className="nb-panel-title">❓ Open Questions</span>
            </div>
            {allQuestions.length === 0 ? (
              <p className="nb-empty-hint">No open questions yet.</p>
            ) : (
              <ul className="nb-feed">
                {allQuestions.map((q, i) => (
                  <li key={i} className="nb-feed-item">
                    <span className="nb-feed-text">{q.text}</span>
                    <div className="nb-feed-right">
                      <span className="nb-feed-date">{formatDate(q.date)}</span>
                      <button className="notebook-remove-btn"
                        onClick={() => removeQuestion(q.entryId, q.idx)}>✕</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
