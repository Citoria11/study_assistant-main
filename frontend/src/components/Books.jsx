import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function Books({ target, onTargetConsumed }) {
  const [books, setBooks] = useState([]);
  const [selectedBook, setSelectedBook] = useState("");
  const [chapter, setChapter] = useState(1);
  const [totalChapters, setTotalChapters] = useState(1);
  const [verses, setVerses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [highlightVerse, setHighlightVerse] = useState(null);
  const highlightRef = useRef(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [searchHits, setSearchHits] = useState(null);      // null = closed
  const [searchInterpretation, setSearchInterpretation] = useState("");
  const searchRef = useRef(null);

  // Load book list on mount
  useEffect(() => {
    axios
      .get(`${API_BASE}/api/books/`)
      .then((r) => {
        setBooks(r.data.books);
        if (r.data.books.length > 0) setSelectedBook(r.data.books[0]);
      })
      .catch(() => setError("Could not load books."));
  }, []);

  // When a navigation target arrives from Chat, jump to it
  useEffect(() => {
    if (!target) return;
    setSelectedBook(target.book);
    setChapter(target.chapter);
    setHighlightVerse(target.verse);
    onTargetConsumed?.();
  }, [target]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load chapter whenever book or chapter changes
  useEffect(() => {
    if (!selectedBook) return;
    setLoading(true);
    setError(null);
    axios
      .get(`${API_BASE}/api/books/${encodeURIComponent(selectedBook)}/${chapter}`)
      .then((r) => {
        setVerses(r.data.verses);
        setTotalChapters(r.data.total_chapters);
      })
      .catch(() => setError("Could not load chapter."))
      .finally(() => setLoading(false));
  }, [selectedBook, chapter]);

  // Scroll highlighted verse into view after verses load
  useEffect(() => {
    if (highlightVerse == null || loading) return;
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [verses, highlightVerse, loading]);

  // Close search results when clicking outside
  useEffect(() => {
    const handler = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setSearchHits(null);
        setSearchError(null);
        setSearchInterpretation("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleBookChange = (e) => {
    setSelectedBook(e.target.value);
    setChapter(1);
    setHighlightVerse(null);
  };

  const navigateToHit = (hit) => {
    setSelectedBook(hit.book);
    setChapter(hit.chapter);
    setHighlightVerse(hit.verse);
    setSearchHits(null);
    setSearchInterpretation("");
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    setSearchLoading(true);
    setSearchError(null);
    setSearchHits(null);
    setSearchInterpretation("");
    try {
      const r = await axios.post(`${API_BASE}/api/books/search`, { query: q });
      const { match_type, interpretation, hits } = r.data;
      if (match_type === "not_found" || hits.length === 0) {
        setSearchError(interpretation || "Nothing found.");
      } else if (match_type === "reference" && hits.length === 1) {
        setSearchInterpretation(interpretation);
        navigateToHit(hits[0]);
      } else {
        setSearchInterpretation(interpretation);
        setSearchHits(hits);
      }
    } catch {
      setSearchError("Search failed. Please try again.");
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="books-container">
      {/* ── Navigation ribbon ── */}
      <div className="books-ribbon">
        <div className="books-ribbon-row">
          <select
            className="books-book-select"
            value={selectedBook}
            onChange={handleBookChange}
          >
            {books.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>

          <div className="books-chapter-nav">
            <button
              className="books-nav-btn"
              onClick={() => { setChapter((c) => Math.max(1, c - 1)); setHighlightVerse(null); }}
              disabled={chapter <= 1 || loading}
              aria-label="Previous chapter"
            >
              ← Prev
            </button>
            <span className="books-chapter-label">
              Ch. {chapter} <span className="books-chapter-of">of</span> {totalChapters}
            </span>
            <button
              className="books-nav-btn"
              onClick={() => { setChapter((c) => Math.min(totalChapters, c + 1)); setHighlightVerse(null); }}
              disabled={chapter >= totalChapters || loading}
              aria-label="Next chapter"
            >
              Next →
            </button>
          </div>
        </div>

        {/* ── Search row ── */}
        <div className="books-search-row" ref={searchRef}>
          <form className="books-search-form" onSubmit={handleSearch}>
            <input
              className="books-search-input"
              type="text"
              placeholder='Search — e.g. "jon 3:16" or "love your enemies"'
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              disabled={searchLoading}
            />
            <button
              className="books-search-btn"
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
            >
              {searchLoading ? "…" : "Search"}
            </button>
          </form>

          {searchError && (
            <div className="books-search-error">{searchError}</div>
          )}

          {searchInterpretation && !searchHits && (
            <div className="books-search-toast">{searchInterpretation}</div>
          )}

          {searchHits && searchHits.length > 0 && (
            <div className="books-search-results">
              <div className="books-search-results-header">
                <span>{searchInterpretation}</span>
                <button
                  className="books-search-results-close"
                  onClick={() => { setSearchHits(null); setSearchInterpretation(""); }}
                  aria-label="Close results"
                >
                  ✕
                </button>
              </div>
              <ul className="books-search-hits">
                {searchHits.map((hit) => (
                  <li
                    key={`${hit.book}-${hit.chapter}-${hit.verse}`}
                    className="books-search-hit"
                    onClick={() => navigateToHit(hit)}
                  >
                    <span className="books-search-hit-ref">
                      {hit.book} {hit.chapter}:{hit.verse}
                    </span>
                    <span className="books-search-hit-text">
                      {hit.text.length > 100 ? hit.text.slice(0, 100) + "…" : hit.text}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* ── Page ── */}
      <div className="books-page">
        {loading && <p className="books-status">Loading…</p>}
        {error && <p className="books-status books-error">{error}</p>}

        {!loading && !error && verses.length > 0 && (
          <div className="books-page-inner">
            <header className="books-chapter-header">
              <div className="books-book-name">{selectedBook}</div>
              <div className="books-chapter-title">Chapter {chapter}</div>
              <div className="books-ornament">✦ ✦ ✦</div>
            </header>

            <p className="books-prose">
              {verses.map((v, i) => {
                const isHighlight = highlightVerse === v.verse;
                return (
                  <span
                    key={v.verse}
                    id={`verse-${v.verse}`}
                    ref={isHighlight ? highlightRef : null}
                    className={[
                      i === 0 ? "books-first-verse" : "",
                      isHighlight ? "books-verse-highlight" : "",
                    ].join(" ").trim() || undefined}
                  >
                    <sup className="books-sup">{v.verse}</sup>
                    {v.text}{" "}
                  </span>
                );
              })}
            </p>

            <footer className="books-page-footer">
              <button
                className="books-footer-btn"
                onClick={() => { setChapter((c) => Math.max(1, c - 1)); setHighlightVerse(null); }}
                disabled={chapter <= 1}
              >
                ← {chapter > 1 ? `Chapter ${chapter - 1}` : ""}
              </button>
              <span className="books-footer-ref">{selectedBook} {chapter}</span>
              <button
                className="books-footer-btn"
                onClick={() => { setChapter((c) => Math.min(totalChapters, c + 1)); setHighlightVerse(null); }}
                disabled={chapter >= totalChapters}
              >
                {chapter < totalChapters ? `Chapter ${chapter + 1}` : ""} →
              </button>
            </footer>
          </div>
        )}
      </div>
    </div>
  );
}
