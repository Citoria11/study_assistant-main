import { useState, useEffect } from "react";
import ChatInterface from "./components/ChatInterface";
import Games from "./components/Games";
import Mnemonics from "./components/Mnemonics";
import Notebook from "./components/Notebook";
import AuthScreen from "./components/AuthScreen";
import Books from "./components/Books";
import GoalSidebar from "./components/GoalSidebar";
import "./index.css";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const NAV_ITEMS = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "games", label: "Games", icon: "🎮" },
  { id: "notebook", label: "Notebook", icon: "📓" },
  { id: "books", label: "Books", icon: "📖" },
];

function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

function getStoredUser() {
  try {
    const raw = localStorage.getItem("auth_user");
    const token = localStorage.getItem("auth_token");
    if (raw && token) {
      if (isTokenExpired(token)) {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_user");
        return null;
      }
      return { ...JSON.parse(raw), token };
    }
  } catch {
    // ignore malformed data
  }
  return null;
}

function App() {
  const [user, setUser] = useState(getStoredUser);
  const [activeSection, setActiveSection] = useState("chat");
  const [bookTarget, setBookTarget] = useState(null);
  const [gameTarget, setGameTarget] = useState(null);
  const [notebookRefreshKey, setNotebookRefreshKey] = useState(0);
  const [goalSidebarKey, setGoalSidebarKey] = useState(0);
  const [translations, setTranslations] = useState([]);
  const [selectedTranslation, setSelectedTranslation] = useState("");
  const [appliedTranslation, setAppliedTranslation] = useState("");
  const [translationSaving, setTranslationSaving] = useState(false);
  const [translationBuilding, setTranslationBuilding] = useState(false);

  useEffect(() => {
    if (!user) return;
    // Fetch available translations
    fetch(`${API}/api/user/translations`)
      .then((r) => r.json())
      .then(setTranslations)
      .catch(() => {});
    // Fetch user's current preference
    fetch(`${API}/api/user/translation?token=${user.token}`)
      .then((r) => r.json())
      .then((d) => {
        setSelectedTranslation(d.translation);
        setAppliedTranslation(d.translation);
      })
      .catch(() => {});
  }, [user]);

  const handleApplyTranslation = async () => {
    if (!selectedTranslation || selectedTranslation === appliedTranslation)
      return;
    setTranslationSaving(true);
    try {
      const res = await fetch(
        `${API}/api/user/translation?token=${user.token}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ translation: selectedTranslation }),
        },
      );
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (res.ok) {
        setAppliedTranslation(selectedTranslation);
        // Poll until the FAISS index is ready
        setTranslationBuilding(true);
        const target = selectedTranslation;
        const poll = setInterval(async () => {
          try {
            const s = await fetch(
              `${API}/api/user/translation/status?translation=${target}`,
            );
            const data = await s.json();
            if (data.ready) {
              clearInterval(poll);
              setTranslationBuilding(false);
            }
          } catch {
            clearInterval(poll);
            setTranslationBuilding(false);
          }
        }, 2000);
      }
    } finally {
      setTranslationSaving(false);
    }
  };

  const triggerNotebookRefresh = () => setNotebookRefreshKey((k) => k + 1);
  const triggerGoalRefresh = () => setGoalSidebarKey((k) => k + 1);

  const navigateToBook = (target) => {
    setBookTarget(target);
    setActiveSection("books");
  };

  const navigateToGame = (target) => {
    setGameTarget(target);
    setActiveSection("games");
  };

  const handleAuth = (userData) => setUser(userData);

  const handleLogout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    setUser(null);
  };

  if (!user) {
    return <AuthScreen onAuth={handleAuth} />;
  }

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="sidebar-logo-icon">✝️</span>
          <span className="sidebar-logo-text">Bible Study</span>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${activeSection === item.id ? "active" : ""}`}
              onClick={() => setActiveSection(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          {translations.length > 0 && (
            <div className="sidebar-translation">
              <label className="sidebar-translation-label">Translation</label>
              <select
                className="sidebar-translation-select"
                value={selectedTranslation}
                onChange={(e) => setSelectedTranslation(e.target.value)}
              >
                {translations.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              <button
                className="sidebar-translation-apply"
                onClick={handleApplyTranslation}
                disabled={
                  translationSaving ||
                  selectedTranslation === appliedTranslation ||
                  translationBuilding
                }
              >
                {translationSaving ? "Saving…" : "Apply"}
              </button>
              {translationBuilding && (
                <div className="sidebar-translation-status">
                  <span className="sidebar-translation-spinner" />
                  Building index…
                </div>
              )}
              {!translationBuilding && appliedTranslation && (
                <div className="sidebar-translation-active">
                  Active:{" "}
                  {translations.find((t) => t.id === appliedTranslation)
                    ?.name ?? appliedTranslation}
                </div>
              )}
            </div>
          )}
          <span className="sidebar-user">{user.name}</span>
          <button className="sidebar-logout" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="app-body">
        <header className="app-header">
          <h1>{NAV_ITEMS.find((i) => i.id === activeSection)?.label}</h1>
        </header>
        <div className="app-content">
          <main className="app-main">
            {activeSection === "chat" && (
              <ChatInterface
                userId={user.user_id}
                token={user.token}
                onNavigateToBook={navigateToBook}
                onLaunchGame={navigateToGame}
                onAchievementLogged={() => {
                  triggerNotebookRefresh();
                  triggerGoalRefresh();
                }}
              />
            )}
            {activeSection === "games" && (
              <Games
                token={user.token}
                gameTarget={gameTarget}
                onGameTargetConsumed={() => setGameTarget(null)}
                onAchievementLogged={() => {
                  triggerNotebookRefresh();
                  triggerGoalRefresh();
                }}
              />
            )}
            {activeSection === "notebook" && (
              <Notebook
                refreshKey={notebookRefreshKey}
                onGoalChanged={triggerGoalRefresh}
              />
            )}
            {activeSection === "books" && (
              <Books
                target={bookTarget}
                onTargetConsumed={() => setBookTarget(null)}
              />
            )}
          </main>
          <GoalSidebar
            key={goalSidebarKey}
            onGoToNotebook={() => setActiveSection("notebook")}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
