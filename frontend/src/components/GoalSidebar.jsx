import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "";

function getToken() { return localStorage.getItem("auth_token"); }
function authHeaders() { return { Authorization: `Bearer ${getToken()}` }; }
function todayISO() { return new Date().toISOString().slice(0, 10); }

export default function GoalSidebar({ onGoToNotebook }) {
  const [todayEntry, setTodayEntry] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchToday = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/api/notebook/`, { headers: authHeaders() });
      const te = res.data.find(e => e.session_date.slice(0, 10) === todayISO()) || null;
      setTodayEntry(te);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchToday(); }, [fetchToday]);

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
      setTodayEntry(res.data);
    } catch { /* ignore */ }
  }

  const milestones = todayEntry?.goal_milestones || [];
  const completed = todayEntry?.goal_completed || [];
  const pct = milestones.length > 0 ? Math.round(completed.length / milestones.length * 100) : 0;

  return (
    <aside className="goal-sidebar">
      <div className="goal-sidebar-header">
        <span className="goal-sidebar-title">🎯 Today's Goal</span>
      </div>

      {loading ? (
        <p className="goal-sidebar-hint">Loading…</p>
      ) : !todayEntry?.daily_goal ? (
        <div className="goal-sidebar-empty">
          <p className="goal-sidebar-hint">No goal set for today.</p>
          <button className="goal-sidebar-set-btn" onClick={onGoToNotebook}>
            Set a Goal →
          </button>
        </div>
      ) : (
        <div className="goal-sidebar-content">
          <p className="goal-sidebar-goal-name">{todayEntry.daily_goal}</p>

          <div className="goal-sidebar-progress-row">
            <div className="goal-sidebar-bar-wrap">
              <div className="goal-sidebar-bar-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="goal-sidebar-pct">{pct}%</span>
          </div>

          <ul className="goal-sidebar-milestones">
            {milestones.map((m, i) => {
              const done = completed.includes(i);
              return (
                <li key={i} className={`goal-sidebar-milestone${done ? " done" : ""}`}>
                  <label>
                    <input type="checkbox" checked={done}
                      onChange={() => toggleMilestone(i)} />
                    <span>{m}</span>
                  </label>
                </li>
              );
            })}
          </ul>

          {pct === 100 && (
            <p className="goal-sidebar-complete">🎉 Goal complete!</p>
          )}
        </div>
      )}
    </aside>
  );
}
