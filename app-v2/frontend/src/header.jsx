/*
  Shared top menu bar for every page (studio, video, lab pages, admin). Presentational:
  it receives the API-key state and the active tab from whichever app renders it,
  so the key entered on one page (localStorage "nano-sofa-v2-api-key") is the same
  everywhere. Styling lives in styles-v2.css under .topbar*.

*/
import React from "react";
import logoUrl from "./logo.svg"; // "nano sofa" wordmark, 895×130, black on transparent

// Primary tabs. "Lab" groups the experimental / analytical pages under one
// entry with its own sub-menu (rendered below the bar) so the top row stays
// short: the OpenAI generator (/lab), the comparator (/experiments) and the
// editorial composer (/editorial).
const LAB_PAGES = [
  { id: "lab", href: "/lab", label: "Generator OpenAI", hint: "kreator produktowy na GPT Image 2.5" },
  { id: "experiments", href: "/experiments", label: "Porównywarka", hint: "porównanie generacji A/B, trace, koszty" },
  { id: "editorial", href: "/editorial", label: "Editorial", hint: "kadr od zera, Gemini / OpenRouter / OpenAI" },
];
const LAB_IDS = new Set(LAB_PAGES.map(p => p.id));
const SUFFIX = { video: "wideo", editorial: "lab · editorial", lab: "lab · OpenAI", experiments: "lab · porównywarka", admin: "katalog" };

// Page intro shared by every tab: a small mono eyebrow and one short,
// friendly paragraph — no display headings, one typographic voice.
export function PageIntro({ eyebrow, children, aside = null }) {
  return (
    <div className="page-intro">
      <div>
        {eyebrow && <div className="page-intro-eyebrow">{eyebrow}</div>}
        <p>{children}</p>
      </div>
      {aside}
    </div>
  );
}

export function NanoTopbar({ active, apiKey = "", setApiKey, showKeyEdit, setShowKeyEdit, hideApiKey = false, adminLabel = "tylko lokalnie",
                            keyName = "Gemini", keyPlaceholder = "AIza… wklej klucz Gemini" }) {
  const suffix = SUFFIX[active] || "studio";
  const inLab = LAB_IDS.has(active);
  const forget = () => setApiKey?.("");
  return (
    <>
    <header className="topbar">
      <a className="topbar-brand" href="/" title="Nano Sofa — studio">
        <img className="logo" src={logoUrl} alt="nano sofa" />
        <span className="wm light">{suffix}</span>
      </a>

      <nav className="topbar-tabs">
        <a href="/" className={active === "photos" ? "on" : ""}>Zdjęcia</a>
        <a href="/video" className={active === "video" ? "on" : ""}>Wideo</a>
        <a href="/lab" className={inLab ? "on" : ""} title="eksperymenty: generator OpenAI, porównywarka, editorial">Lab</a>
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
    {inLab && (
      <nav className="topbar-sub" aria-label="Lab">
        <span className="topbar-sub-lbl">Lab</span>
        {LAB_PAGES.map(p => (
          <a key={p.id} href={p.href} className={active === p.id ? "on" : ""} title={p.hint}>{p.label}</a>
        ))}
      </nav>
    )}
    </>
  );
}
