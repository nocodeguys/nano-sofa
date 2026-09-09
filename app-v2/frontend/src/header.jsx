/*
  Shared top menu bar for both pages (studio /  + video /video). Presentational:
  it receives the API-key state and the active tab from whichever app renders it,
  so the key entered on one page (localStorage "nano-sofa-v2-api-key") is the same
  everywhere. Styling lives in styles-v2.css under .topbar*.

*/
import React from "react";

export function NanoTopbar({ active, apiKey = "", setApiKey, showKeyEdit, setShowKeyEdit, hideApiKey = false, adminLabel = "tylko lokalnie",
                            keyName = "Gemini", keyPlaceholder = "AIza… wklej klucz Gemini" }) {
  const suffix = active === "video" ? "wideo" : active === "editorial" ? "editorial" : active === "lab" ? "lab · OpenAI" : active === "admin" ? "katalog" : active === "experiments" ? "eksperymenty" : "studio";
  const forget = () => setApiKey?.("");
  return (
    <header className="topbar">
      <div className="topbar-brand">
        <span className="glyph">ns</span>
        <span className="wm">Nano Sofa <span className="light">{suffix}</span></span>
      </div>

      <nav className="topbar-tabs">
        <a href="/" className={active === "photos" ? "on" : ""}>Zdjęcia</a>
        <a href="/video" className={active === "video" ? "on" : ""}>Wideo</a>
        <a href="/editorial" className={active === "editorial" ? "on" : ""}>Editorial</a>
        <a href="/lab" className={active === "lab" ? "on" : ""} title="eksperyment: kreator produktowy na GPT Image 2.5 (OpenAI Images API)">Lab</a>
        <a href="/experiments" className={active === "experiments" ? "on" : ""}>Eksperymenty</a>
        <a href="/admin" className={active === "admin" ? "on" : ""}>Katalog</a>
      </nav>

      <div className="topbar-key">
        {hideApiKey ? (
          <span className="admin-local-chip"><span className="dot"></span>{adminLabel}</span>
        ) : showKeyEdit ? (
          <>
            <input
              autoFocus
              type="password"
              className="keyfield"
              placeholder={keyPlaceholder}
              value={apiKey}
              onChange={e => setApiKey?.(e.target.value)}
              onBlur={() => setShowKeyEdit?.(false)}
              onKeyDown={e => { if (e.key === "Enter" || e.key === "Escape") setShowKeyEdit?.(false); }}
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
              onClick={() => setShowKeyEdit?.(true)}
              title={`kliknij aby wkleić / zmienić klucz ${keyName}`}>
              <span className="dot"></span>
              <span>{apiKey ? `klucz ••${apiKey.slice(-4)}` : `wklej klucz ${keyName}`}</span>
            </div>
            {apiKey && (
              <button type="button" className="btn-mini" title="usuń zapisany klucz z tej przeglądarki"
                onClick={e => { e.stopPropagation(); setApiKey?.(""); setShowKeyEdit?.(true); }}>
                reset
              </button>
            )}
          </>
        )}
      </div>
    </header>
  );
}
