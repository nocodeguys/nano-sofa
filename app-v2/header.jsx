/*
  Shared top menu bar for both pages (studio /  + video /video). Presentational:
  it receives the API-key state and the active tab from whichever app renders it,
  so the key entered on one page (localStorage "nano-sofa-v2-api-key") is the same
  everywhere. Styling lives in styles-v2.css under .topbar*.

  Loaded as a plain <script type="text/babel"> BEFORE each page's app script, so
  `NanoTopbar` is a global both apps can use (same mechanism as data.jsx).
*/
function NanoTopbar({ active, apiKey, setApiKey, showKeyEdit, setShowKeyEdit }) {
  const suffix = active === "video" ? "wideo" : "studio";
  const forget = () => setApiKey("");
  return (
    <header className="topbar">
      <div className="topbar-brand">
        <span className="glyph">ns</span>
        <span className="wm">Nano Sofa <span className="light">{suffix}</span></span>
      </div>

      <nav className="topbar-tabs">
        <a href="/" className={active === "photos" ? "on" : ""}>Zdjęcia</a>
        <a href="/video" className={active === "video" ? "on" : ""}>Wideo</a>
      </nav>

      <div className="topbar-key">
        {showKeyEdit ? (
          <>
            <input
              autoFocus
              type="password"
              className="keyfield"
              placeholder="AIza… wklej klucz Gemini"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              onBlur={() => setShowKeyEdit(false)}
              onKeyDown={e => { if (e.key === "Enter" || e.key === "Escape") setShowKeyEdit(false); }}
            />
            {apiKey && (
              <button type="button" className="btn-mini" title="usuń zapisany klucz z tej przeglądarki"
                onMouseDown={e => e.preventDefault()} onClick={forget}>
                zapomnij
              </button>
            )}
          </>
        ) : (
          <>
            <div className={"keychip" + (apiKey ? "" : " empty")}
              onClick={() => setShowKeyEdit(true)}
              title="kliknij aby wkleić / zmienić klucz Gemini">
              <span className="dot"></span>
              <span>{apiKey ? `klucz ••${apiKey.slice(-4)}` : "wklej klucz Gemini"}</span>
            </div>
            {apiKey && (
              <button type="button" className="btn-mini" title="usuń zapisany klucz z tej przeglądarki"
                onClick={e => { e.stopPropagation(); setApiKey(""); setShowKeyEdit(true); }}>
                reset
              </button>
            )}
          </>
        )}
      </div>
    </header>
  );
}
window.NanoTopbar = NanoTopbar;
