/*
  Nano Sofa — Editorial. A standalone subpage served at /editorial, sharing the
  studio page's localStorage API key. Freeform text-to-image: no base product
  photo — you describe the shot (magazine cover, web hero, campaign…), pick a
  model and optional art-direction pickers (scene / light / lens / palette /
  fabric cue), and the model composes from scratch. Optional moodboard refs.
*/
import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/300.css";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "./styles-v2.css";
import { NS_DATA } from "./data.jsx";
import { NanoTopbar } from "./header.jsx";

const API_KEY_STORAGE = "nano-sofa-v2-api-key"; // shared with the studio page
const OR_KEY_STORAGE = "nano-sofa-v2-openrouter-key"; // FLUX / Seedream via OpenRouter
const { ENVIRONMENTS, TIMES_OF_DAY, LENSES, CAMERA_HEIGHTS, COLORS, MATERIALS,
        EDITORIAL_STYLES, PEOPLE_OPTIONS } = NS_DATA;

// Lifestyle + cyclorama scenes minus legacy aliases and "custom" (needs an
// upload slot the editorial page doesn't have).
const SCENES = ENVIRONMENTS.filter(e => !e.id.startsWith("studio_") && e.id !== "custom");
const ASPECTS = ["1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9", "21:9"];
const MAX_REFS = 3;

const Ic = {
  sparkle: <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" fill="currentColor"/></svg>,
};

function aspectStyle(a) {
  const [w, h] = a.split(":").map(Number);
  const vertical = h > w;
  return { aspectRatio: `${w} / ${h}`, width: vertical ? "min(72%, 380px)" : "min(92%, 640px)" };
}

// "brak" (none) entry prepended to each optional picker.
function withNone(list, label = "brak — model decyduje") {
  return [{ id: "", name: label }, ...list];
}

function App() {
  // ---- shared API key -----------------------------------------------------
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(API_KEY_STORAGE, apiKey); } catch {}
  }, [apiKey]);
  const [showKeyEdit, setShowKeyEdit] = useState(() => {
    try { return !(localStorage.getItem(API_KEY_STORAGE) || ""); } catch { return true; }
  });

  // ---- OpenRouter key (only needed for FLUX / Seedream) -------------------
  const [orKey, setOrKey] = useState(() => {
    try { return localStorage.getItem(OR_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(OR_KEY_STORAGE, orKey); } catch {}
  }, [orKey]);

  // ---- model catalog from /api/config ------------------------------------
  const [models, setModels] = useState([]);
  const [modelId, setModelId] = useState("gemini-2.5-flash-image");
  useEffect(() => {
    fetch("/api/config").then(r => r.ok ? r.json() : null).then(c => {
      const list = (c && (c.editorial_models || c.models)) || [];
      if (list.length) {
        setModels(list);
        setModelId(prev => list.some(m => m.id === prev) ? prev : list[0].id);
      }
    }).catch(() => {});
  }, []);
  const model = models.find(m => m.id === modelId) || null;
  const isOpenRouter = !!(model && model.provider === "openrouter");

  // ---- form state ---------------------------------------------------------
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("magazine_cover");
  const [aspect, setAspect] = useState("3:4");
  const [res, setRes] = useState("1K");
  const [env, setEnv] = useState("");
  const [tod, setTod] = useState("");
  const [lens, setLens] = useState("");
  const [height, setHeight] = useState("");
  const [color, setColor] = useState("");
  const [mat, setMat] = useState("");
  const [people, setPeople] = useState("");
  const [seed, setSeed] = useState("");
  const [refs, setRefs] = useState([]);          // [{file, url}]
  const refInputRef = useRef(null);

  // Clamp resolution to what the model supports.
  useEffect(() => {
    if (model && !(model.resolutions || []).includes(res)) {
      setRes((model.resolutions || ["1K"])[0]);
    }
    // eslint-disable-next-line
  }, [modelId]);

  const addRefs = (files) => {
    const next = [...refs];
    for (const f of files || []) {
      if (next.length >= MAX_REFS) break;
      next.push({ file: f, url: URL.createObjectURL(f) });
    }
    setRefs(next);
  };
  const removeRef = (i) => {
    try { URL.revokeObjectURL(refs[i].url); } catch {}
    setRefs(refs.filter((_, j) => j !== i));
  };

  // ---- generation ---------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const [shown, setShown] = useState(null);      // currently displayed result
  const [history, setHistory] = useState([]);    // this session's results

  const handleGenerate = async () => {
    setError(null);
    if (isOpenRouter) {
      if (!orKey.trim()) { setError({ message: "Ten model działa przez OpenRouter — wklej klucz sk-or-… w sekcji Model.", code: "MISSING_OPENROUTER_KEY" }); return; }
    } else if (!apiKey.trim()) { setError({ message: "Wklej klucz Gemini API u góry.", code: "MISSING_API_KEY" }); setShowKeyEdit(true); return; }
    if (prompt.trim().length < 3) { setError({ message: "Opisz, co ma być na zdjęciu.", code: "MISSING_PROMPT" }); return; }
    if (busy) return;
    setBusy(true);
    setElapsed(0);
    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 250);
    try {
      const fd = new FormData();
      fd.append("api_key", apiKey.trim());
      if (isOpenRouter) fd.append("openrouter_key", orKey.trim());
      fd.append("prompt", prompt.trim());
      fd.append("style", style);
      fd.append("env", env);
      fd.append("tod", tod);
      fd.append("lens", lens);
      fd.append("height", height);
      fd.append("color", color);
      fd.append("mat", mat);
      fd.append("people", people);
      fd.append("model", modelId);
      fd.append("aspect", aspect);
      fd.append("res", res);
      if (seed.trim()) fd.append("seed", seed.trim());
      for (const r of refs) fd.append("references", r.file);

      const r = await fetch("/api/generate-free", { method: "POST", body: fd });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data || !data.success) {
        setError({
          message: (data && data.error) || "Nie udało się wygenerować obrazu.",
          code: data && data.error_code,
          detail: data && data.error_detail,
        });
      } else {
        const entry = { ...data, aspect, at: Date.now() };
        setShown(entry);
        setHistory(h => [entry, ...h].slice(0, 12));
      }
    } catch (e) {
      setError({ message: "Błąd sieci lub przekroczono czas oczekiwania. Spróbuj ponownie.", code: "NETWORK_TIMEOUT" });
    } finally {
      clearInterval(timer);
      setBusy(false);
    }
  };

  const mm = String(Math.floor(elapsed / 60));
  const ss = String(elapsed % 60).padStart(2, "0");
  const stageAspect = shown ? shown.aspect : aspect;

  return (
    <div className="app-frame">
      <NanoTopbar active="editorial" apiKey={apiKey} setApiKey={setApiKey} showKeyEdit={showKeyEdit} setShowKeyEdit={setShowKeyEdit} />
      <div className="shell">
      {/* ================= LEFT — stage ================= */}
      <section className="stage-pane">
        <div className="stage-canvas" style={{ display: "grid", placeItems: "center", padding: "36px 24px 28px", background: "var(--bg-2)" }}>
          <div style={{ width: "100%", display: "grid", justifyItems: "center" }}>
            <div className="ed-frame" style={aspectStyle(stageAspect)}>
              {busy ? (
                <div className="ed-placeholder">
                  <div className="ed-spinner"></div>
                  Komponuję kadr… {mm}:{ss}<br />
                  <span style={{ opacity: .6 }}>{model ? model.id : ""} · {aspect} · {res}</span>
                </div>
              ) : shown ? (
                <img src={shown.image_url} alt="wygenerowany kadr" />
              ) : (
                <div className="ed-placeholder">
                  Twój kadr pojawi się tutaj.<br />
                  <span style={{ opacity: .6 }}>Opisz zdjęcie po prawej i naciśnij „Generuj kadr”.</span>
                </div>
              )}
            </div>

            {shown && !busy && (
              <div className="ed-meta">
                <a className="ed-dl" href={shown.image_url} download>⭳ Pobierz {String(shown.format || "jpg").toUpperCase()}</a>
                <span>{shown.model}</span><span>·</span>
                <span>{shown.resolution} · {shown.aspect}</span><span>·</span>
                <span>≈ ${Number(shown.cost || 0).toFixed(3)}</span><span>·</span>
                <span>{Math.round((shown.elapsed_ms || 0) / 100) / 10}s</span>
              </div>
            )}

            {history.length > 1 && (
              <div className="ed-hist">
                {history.map(h => (
                  <img key={h.generation_id} src={h.image_url} alt=""
                    className={shown && shown.generation_id === h.generation_id ? "on" : ""}
                    onClick={() => setShown(h)} />
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ================= RIGHT — form ================= */}
      <section className="form-pane">
        <div className="form-intro">
          <div className="eyebrow">Editorial · <a href="/" style={{ color: "inherit", textDecoration: "underline", textUnderlineOffset: "2px" }}>← wróć do zdjęć</a></div>
          <div className="intro-body">
            <h1>Kadr od zera, <em>bez zdjęcia bazowego.</em></h1>
            <p>Okładka, hero na stronę, kampania. Opisujesz — model komponuje. Pickery sceny, światła i palety trzymają spójność z marką.</p>
          </div>
        </div>

        {!apiKey && (
          <div className="api-banner">
            <div className="api-banner-head">
              <div className="api-banner-eyebrow">krok zerowy</div>
              <div className="api-banner-title serif">Wklej swój klucz Gemini API, żeby zacząć</div>
              <div className="api-banner-help">
                Klucz trzymamy tylko w Twojej przeglądarce (localStorage). Ten sam klucz działa
                w studiu zdjęć i wideo. Pobierz z {" "}
                <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">aistudio.google.com/app/apikey</a>.
              </div>
            </div>
            <div className="api-banner-form">
              <input autoFocus type="password" className="input" placeholder="AIza..."
                value={apiKey} onChange={e => setApiKey(e.target.value)}
                style={{ flex: 1, fontFamily: "Geist Mono", fontSize: 13 }} />
            </div>
          </div>
        )}

        {error && (
          <div className="ed-err">
            <strong>{error.code || "Błąd"}</strong> — {error.message}
            {error.detail && (
              <div style={{ marginTop: 6, fontFamily: "'Geist Mono', monospace", fontSize: 11, opacity: .8, wordBreak: "break-word" }}>
                Szczegóły od Google: {error.detail}
              </div>
            )}
          </div>
        )}

        {/* 01 — brief */}
        <div className="section">
          <div className="sec-head">
            <div className="num">01</div>
            <div className="title serif">Brief</div>
          </div>
          <p className="sec-help">Opisz, co ma być na zdjęciu — scena, nastrój, bohater kadru. Twój opis prowadzi; pickery niżej tylko doprecyzowują.</p>
          <div className="sec-body">
            <textarea className="input" rows={5}
              placeholder="np. Przytulna sypialnia o świcie, tapicerowane łóżko z baldachimem z lnu, poranna mgła za oknem, minimalistyczna kompozycja z dużą ilością spokojnej przestrzeni…"
              value={prompt} onChange={e => setPrompt(e.target.value)}
              style={{ resize: "vertical", lineHeight: 1.55 }} />

            <div className="field-lbl" style={{ marginTop: 16 }}>styl / przeznaczenie</div>
            <div className="ed-style">
              {EDITORIAL_STYLES.map(s => (
                <button key={s.id} className={style === s.id ? "on" : ""} onClick={() => setStyle(s.id)}>
                  <div className="nm">{s.name}</div>
                  <div className="pr">{s.prop}</div>
                </button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 16 }}>moodboard (opcjonalnie, do {MAX_REFS})</div>
            <div className="ed-refs">
              {refs.map((r, i) => (
                <div key={r.url} className="slot" onClick={e => e.stopPropagation()}>
                  <img src={r.url} alt={`ref ${i + 1}`} />
                  <button type="button" className="x" onClick={() => removeRef(i)}>×</button>
                </div>
              ))}
              {refs.length < MAX_REFS && (
                <div className="slot" onClick={() => refInputRef.current && refInputRef.current.click()}>＋</div>
              )}
            </div>
            <input ref={refInputRef} type="file" accept="image/*" multiple style={{ display: "none" }}
              onChange={e => { addRefs(e.target.files); e.target.value = ""; }} />
            <div className="hint">luźna inspiracja stylu / nastroju — model ich nie kopiuje</div>
          </div>
        </div>

        {/* 02 — model + format */}
        <div className="section">
          <div className="sec-head">
            <div className="num">02</div>
            <div className="title serif">Model i format</div>
            <div className="summary">{aspect} · {res}</div>
          </div>
          <p className="sec-help">Okładka: 3:4 · story: 9:16 · hero www: 16:9 lub 21:9.</p>
          <div className="sec-body">
            <select className="select" value={modelId} onChange={e => setModelId(e.target.value)}>
              {models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.label}{m.provider === "openrouter"
                    ? (m.price_hint ? ` · ${m.price_hint}` : "")
                    : ` · do ${m.max_resolution}`}
                </option>
              ))}
            </select>
            {isOpenRouter && (
              <>
                <div className="hint" style={{ marginTop: 8 }}>
                  Model alternatywny — komponuje pięknie, ale nie jest wierny produktowi jak Gemini.
                  Działa przez OpenRouter i wymaga osobnego klucza.
                </div>
                <div className="field-lbl" style={{ marginTop: 10 }}>klucz OpenRouter</div>
                <input type="password" className="input" placeholder="sk-or-…"
                  value={orKey} onChange={e => setOrKey(e.target.value)}
                  style={{ fontFamily: "Geist Mono", fontSize: 13 }} />
                <div className="hint">
                  trzymany tylko w tej przeglądarce · pobierz z{" "}
                  <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">openrouter.ai/settings/keys</a>
                </div>
              </>
            )}

            <div className="field-lbl" style={{ marginTop: 16 }}>proporcje</div>
            <div className="seg">
              {ASPECTS.map(a => (
                <button key={a} className={aspect === a ? "on" : ""} onClick={() => setAspect(a)}>{a}</button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 16 }}>rozdzielczość</div>
            <div className="seg">
              {(model ? model.resolutions : ["1K"]).map(r => (
                <button key={r} className={res === r ? "on" : ""} onClick={() => setRes(r)}>{r}</button>
              ))}
            </div>
          </div>
        </div>

        {/* 03 — art direction */}
        <div className="section">
          <div className="sec-head">
            <div className="num">03</div>
            <div className="title serif">Art direction</div>
            <div className="summary">wszystko opcjonalne</div>
          </div>
          <p className="sec-help">Te same presety co w studiu — scena, światło, obiektyw, paleta TreeTale. Puste pole = pełna swoboda modelu.</p>
          <div className="sec-body">
            <div className="field-lbl">scena</div>
            <select className="select" value={env} onChange={e => setEnv(e.target.value)}>
              {withNone(SCENES).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>

            <div className="field-lbl" style={{ marginTop: 14 }}>światło</div>
            <div className="seg">
              {withNone(TIMES_OF_DAY, "brak").map(t => (
                <button key={t.id} className={tod === t.id ? "on" : ""} onClick={() => setTod(t.id)}>{t.name}</button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>obiektyw</div>
            <div className="seg">
              {withNone(LENSES, "brak").map(l => (
                <button key={l.id} className={lens === l.id ? "on" : ""} onClick={() => setLens(l.id)}>{l.name}</button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>wysokość kamery</div>
            <div className="seg">
              {withNone(CAMERA_HEIGHTS, "brak").map(h => (
                <button key={h.id} className={height === h.id ? "on" : ""} onClick={() => setHeight(h.id)}>{h.name}</button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>paleta przewodnia (TreeTale)</div>
            <div className="ed-sw">
              <button title="brak" className={color === "" ? "on" : ""}
                style={{ background: "repeating-conic-gradient(#ddd 0% 25%, #fff 0% 50%) 0 0/8px 8px" }}
                onClick={() => setColor("")} />
              {COLORS.map(c => (
                <button key={c.id} title={c.name} className={color === c.id ? "on" : ""}
                  style={{ background: c.hex }} onClick={() => setColor(c.id)} />
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>tkanina przewodnia</div>
            <div className="seg">
              {withNone(MATERIALS, "brak").map(m => (
                <button key={m.id} className={mat === m.id ? "on" : ""} onClick={() => setMat(m.id)}>{m.name}</button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>ludzie w kadrze</div>
            <div className="seg">
              {PEOPLE_OPTIONS.map(p => (
                <button key={p.id} className={people === p.id ? "on" : ""} onClick={() => setPeople(p.id)}>{p.name}</button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>seed (opcjonalny)</div>
            <input className="input" placeholder="losowy" value={seed}
              onChange={e => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
              style={{ maxWidth: 160, fontFamily: "Geist Mono" }} />
          </div>
        </div>

        {/* foot */}
        <div className="form-foot">
          <div className="foot-summary">
            <div className="foot-lead">{busy ? `Komponuję… ${mm}:${ss}` : "Gotowe do generowania"}</div>
            <div className="foot-meta">
              <span className="mono">{modelId}</span><span className="dot">·</span>
              <span className="mono">{aspect} · {res}</span>
              {style && <><span className="dot">·</span><span className="mono">{(EDITORIAL_STYLES.find(s => s.id === style) || {}).name}</span></>}
            </div>
          </div>
          <div className="foot-actions">
            <button className="foot-gen" onClick={handleGenerate} disabled={busy}
              style={busy ? { opacity: .6, cursor: "wait" } : {}}>
              <span className="ico">{Ic.sparkle}</span>
              <span>{busy ? "Generuję…" : "Generuj kadr"}</span>
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
