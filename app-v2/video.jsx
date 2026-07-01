/*
  Nano Sofa — Wideo (Veo). A standalone subpage served at /video, sharing the
  studio page's localStorage API key. Text-to-video: freeform prompt, no sofa/
  bed coupling. The model list + per-model constraints come from
  /api/video-models (which can probe the user's key), so nothing here hardcodes
  the catalog — resolutions / aspect ratios / durations follow the chosen model.
*/
const { useState, useEffect, useRef, useCallback } = React;

const API_KEY_STORAGE = "nano-sofa-v2-api-key"; // shared with the studio page

const Ic = {
  sparkle: <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" fill="currentColor"/></svg>,
};

function fmtCost(n) {
  const v = Number(n) || 0;
  return v >= 1 ? v.toFixed(2) : v.toFixed(2);
}
function aspectClass(a) { return a === "9:16" ? "a-9-16" : "a-16-9"; }

function App() {
  // ---- shared API key (same storage key as the studio) --------------------
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(API_KEY_STORAGE, apiKey); } catch {}
  }, [apiKey]);
  const [showKeyEdit, setShowKeyEdit] = useState(() => {
    try { return !(localStorage.getItem(API_KEY_STORAGE) || ""); } catch { return true; }
  });

  // ---- catalog from server ------------------------------------------------
  const [cfg, setCfg] = useState({ models: [], default_model: null, hd: null });
  const [modelId, setModelId] = useState("");
  const [aspect, setAspect] = useState("16:9");
  const [resolution, setResolution] = useState("720p");
  const [duration, setDuration] = useState(8);
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");
  const [seed, setSeed] = useState("");
  const [imageFile, setImageFile] = useState(null);      // first-frame / reference
  const [imagePreview, setImagePreview] = useState(null);
  const imageInputRef = React.useRef(null);

  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [diag, setDiag] = useState(null);
  const [diagBusy, setDiagBusy] = useState(false);

  const loadModels = useCallback((key) => {
    const q = key ? ("?api_key=" + encodeURIComponent(key)) : "";
    fetch("/api/video-models" + q)
      .then(r => r.ok ? r.json() : null)
      .then(c => {
        if (c && c.models && c.models.length) {
          setCfg(c);
          setModelId(prev => (prev && c.models.some(m => m.id === prev)) ? prev : (c.default_model || c.models[0].id));
        }
      })
      .catch(() => {});
  }, []);
  // On mount: populate the full catalog instantly (no key), then, if a key is
  // already stored, re-probe to narrow the list to models that key can reach.
  useEffect(() => {
    loadModels("");
    const k = apiKey.trim();
    if (k) loadModels(k);
    /* eslint-disable-next-line */
  }, []);
  // The shared top-bar key field doesn't re-probe on its own — re-probe whenever
  // the key editor closes (blur / Enter / Esc), mirroring the old inline field.
  useEffect(() => {
    if (!showKeyEdit) loadModels(apiKey.trim());
    /* eslint-disable-next-line */
  }, [showKeyEdit]);

  const model = cfg.models.find(m => m.id === modelId) || null;
  const hd = cfg.hd || { resolutions: ["1080p", "4k"], aspect_ratio: "16:9", duration_seconds: 8 };
  const hdRes = hd.resolutions || [];
  // Omni is a different engine (Interactions API): 720p only, no duration matrix.
  const isOmni = !!(model && model.engine === "omni");

  // When the model changes, clamp the format fields to what it supports.
  useEffect(() => {
    if (!model) return;
    if (!model.aspect_ratios.includes(aspect)) setAspect(model.aspect_ratios[0]);
    if (!model.resolutions.includes(resolution)) setResolution(model.resolutions[0]);
    // Some engines (Omni) don't expose a duration list — leave duration as-is.
    if (model.durations_seconds.length && !model.durations_seconds.includes(duration)) {
      setDuration(model.durations_seconds[model.durations_seconds.length - 1]);
    }
    // eslint-disable-next-line
  }, [modelId]);

  // ---- constraint-aware setters (1080p/4k ⇒ 16:9 + 8s) --------------------
  const isHd = hdRes.includes(resolution);
  const pickResolution = (r) => {
    setResolution(r);
    if (hdRes.includes(r)) { setAspect(hd.aspect_ratio); setDuration(hd.duration_seconds); }
  };
  const pickAspect = (a) => {
    setAspect(a);
    if (isHd && a !== hd.aspect_ratio) setResolution("720p");
  };
  const pickDuration = (d) => {
    setDuration(d);
    if (isHd && d !== hd.duration_seconds) setResolution("720p");
  };

  const rateFor = (m, r) => {
    if (!m) return 0;
    const byRes = m.price_by_resolution || {};
    return (byRes[r] != null) ? byRes[r] : m.price_per_second_usd;
  };
  const cost = Number(rateFor(model, resolution)) * Number(duration);
  // Omni sets its own length, so a per-second estimate is meaningless → "~".
  const costLabel = isOmni ? "~" : ("$" + fmtCost(cost));

  const onPickImage = (file) => {
    if (!file) return;
    if (imagePreview) { try { URL.revokeObjectURL(imagePreview); } catch {} }
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
  };
  const clearImage = () => {
    if (imagePreview) { try { URL.revokeObjectURL(imagePreview); } catch {} }
    setImageFile(null);
    setImagePreview(null);
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const runDiagnose = async () => {
    if (!apiKey.trim()) { setShowKeyEdit(true); return; }
    setDiagBusy(true);
    setDiag(null);
    try {
      const r = await fetch("/api/video-diagnose?api_key=" + encodeURIComponent(apiKey.trim()));
      const d = await r.json().catch(() => null);
      setDiag(d || { error: "Brak odpowiedzi serwera." });
    } catch (e) {
      setDiag({ error: "Błąd sieci." });
    } finally {
      setDiagBusy(false);
    }
  };

  const handleGenerate = async () => {
    setError(null);
    if (!apiKey.trim()) { setError({ message: "Wklej klucz Gemini API u góry.", code: "MISSING_API_KEY" }); setShowKeyEdit(true); return; }
    if (!prompt.trim()) { setError({ message: "Wpisz opis (prompt) filmu.", code: "INVALID_REQUEST" }); return; }
    if (busy) return;
    setResult(null);
    setBusy(true);
    setElapsed(0);
    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 250);
    try {
      const fd = new FormData();
      fd.append("api_key", apiKey.trim());
      fd.append("prompt", prompt.trim());
      fd.append("model", modelId);
      fd.append("aspect", aspect);
      fd.append("resolution", resolution);
      fd.append("duration", String(duration));
      if (negative.trim()) fd.append("negative_prompt", negative.trim());
      if (seed.trim()) fd.append("seed", seed.trim());
      if (imageFile) fd.append("image", imageFile);

      const r = await fetch("/api/generate-video", { method: "POST", body: fd });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data || !data.success) {
        setError({
          message: (data && data.error) || "Nie udało się wygenerować wideo.",
          code: data && data.error_code,
          detail: data && data.error_detail,
        });
      } else {
        setResult(data);
      }
    } catch (e) {
      setError({ message: "Błąd sieci lub przekroczono czas oczekiwania. Spróbuj ponownie.", code: "NETWORK_TIMEOUT" });
    } finally {
      clearInterval(timer);
      setBusy(false);
    }
  };

  const mm = String(Math.floor(elapsed / 60)).padStart(1, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="app-frame">
      <NanoTopbar active="video" apiKey={apiKey} setApiKey={setApiKey} showKeyEdit={showKeyEdit} setShowKeyEdit={setShowKeyEdit} />
      <div className="shell">
      {/* ================= LEFT — player / stage ================= */}
      <section className="stage-pane">
        <div className="stage-canvas" style={{ display: "grid", placeItems: "center", padding: "36px 24px 28px", background: "var(--bg-2)" }}>
          <div>
            <div className={"vid-frame " + aspectClass(aspect)}>
              {busy ? (
                <div className="vid-placeholder">
                  <div className="vid-spinner"></div>
                  Renderuję wideo…<br />
                  {mm}:{ss} · zwykle 1–3 min<br />
                  <span style={{ opacity: .6 }}>{model ? model.label : ""} · {resolution} · {aspect} · {duration}s</span>
                </div>
              ) : result ? (
                <video src={result.video_url} controls autoPlay loop playsInline />
              ) : (
                <div className="vid-placeholder">
                  Twój film pojawi się tutaj.<br />
                  <span style={{ opacity: .6 }}>Opisz scenę po prawej i naciśnij „Generuj wideo”.</span>
                </div>
              )}
            </div>

            {result && (
              <div className="vid-meta">
                <a className="vid-dl" href={result.video_url} download>⭳ Pobierz mp4</a>
                <span>{result.model}</span><span className="dot">·</span>
                <span>{result.resolution} · {result.aspect}</span><span className="dot">·</span>
                <span>{result.duration}s</span><span className="dot">·</span>
                <span>{result.audio ? "z dźwiękiem" : "bez dźwięku"}</span>
                <span className="dot">·</span><span>≈ ${fmtCost(result.cost)}</span>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ================= RIGHT — form ================= */}
      <section className="form-pane">
        <div className="form-intro">
          <div className="eyebrow">Wideo · Veo · <a href="/" style={{ color: "inherit", textDecoration: "underline", textUnderlineOffset: "2px" }}>← wróć do zdjęć</a></div>
          <div className="intro-body">
            <h1>Generuj wideo z <em>opisu tekstowego.</em></h1>
            <p>Dowolny prompt — bez potrzeby odnoszenia się do sofy czy łóżka. Modele Google Veo, natywny dźwięk, do 4K.</p>
          </div>
        </div>

        {!apiKey && (
          <div className="api-banner">
            <div className="api-banner-head">
              <div className="api-banner-eyebrow">krok zerowy</div>
              <div className="api-banner-title serif">Wklej swój klucz Gemini API, żeby zacząć</div>
              <div className="api-banner-help">
                Klucz trzymamy tylko w Twojej przeglądarce (localStorage) i używamy go wyłącznie do wywołań Google.
                Ten sam klucz działa też w studiu zdjęć. Pobierz z {" "}
                <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">aistudio.google.com/app/apikey</a>.
              </div>
            </div>
            <div className="api-banner-form">
              <input autoFocus type="password" className="input" placeholder="AIza..."
                value={apiKey} onChange={e => setApiKey(e.target.value)}
                onBlur={() => loadModels(apiKey.trim())}
                style={{ flex: 1, fontFamily: "Geist Mono", fontSize: 13 }} />
            </div>
          </div>
        )}

        {error && (
          <div className="vid-err">
            <strong>{error.code || "Błąd"}</strong> — {error.message}
            {error.detail && (
              <div style={{ marginTop: 6, fontFamily: "'Geist Mono', monospace", fontSize: 11, opacity: .8, wordBreak: "break-word" }}>
                Szczegóły od Google: {error.detail}
              </div>
            )}
          </div>
        )}

        {/* 01 — model */}
        <div className="section">
          <div className="sec-head">
            <div className="num">01</div>
            <div className="title serif">Model</div>
            {model && (isOmni
              ? <div className="summary" style={{ color: "#B5663A" }}>eksperymentalny</div>
              : <div className="summary">${Number(model.price_per_second_usd).toFixed(2)}/s</div>)}
          </div>
          <p className="sec-help">Modele różnią się jakością, dźwiękiem i ceną za sekundę. Lista pochodzi z Twojego konta Google.</p>
          <div className="sec-body">
            <select className="select" value={modelId} onChange={e => setModelId(e.target.value)}>
              {cfg.models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.label}{m.experimental ? " · eksperymentalny" : ""} · od ${Number(m.price_per_second_usd).toFixed(2)}/s · do {m.resolutions[m.resolutions.length - 1]}
                </option>
              ))}
            </select>
            {model && model.notes && <div className="hint">{model.notes}</div>}
            {model && model.audio && (
              <div className="hint" style={{ marginTop: 12 }}>🔊 Natywny dźwięk zawsze włączony (wliczony w cenę).</div>
            )}
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn-mini" onClick={runDiagnose} disabled={diagBusy}>
                {diagBusy ? "Sprawdzam…" : "Sprawdź dostęp klucza do modeli"}
              </button>
              {diag && (
                <div className="hint" style={{ marginTop: 8, whiteSpace: "normal", lineHeight: 1.5 }}>
                  {diag.error
                    ? <span style={{ color: "#B5663A" }}>Próba nieudana: {diag.error}</span>
                    : <>Klucz widzi <strong>{diag.total_models}</strong> modeli. Modele wideo/Veo w liście:{" "}
                        {(diag.video_models_visible || []).length
                          ? (diag.video_models_visible || []).join(", ")
                          : "brak (uwaga: lista nie zawsze pokazuje modele preview — Veo może działać mimo to, o ile masz płatny tier)"}.</>}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 02 — format */}
        <div className="section">
          <div className="sec-head">
            <div className="num">02</div>
            <div className="title serif">Format</div>
            <div className="summary">{aspect} · {resolution}{isOmni ? "" : " · " + duration + "s"}</div>
          </div>
          <p className="sec-help">{isOmni
            ? "Proporcje i rozdzielczość. Omni sam dobiera długość klipu (720p)."
            : "Proporcje, rozdzielczość i długość. 1080p / 4K tylko dla 16:9 i 8 s."}</p>
          <div className="sec-body">
            <div className="field-lbl">proporcje</div>
            <div className="seg">
              {(model ? model.aspect_ratios : ["16:9", "9:16"]).map(a => (
                <button key={a} className={aspect === a ? "on" : ""} onClick={() => pickAspect(a)}>
                  {a}{a === "16:9" ? " — poziomo" : a === "9:16" ? " — pionowo" : ""}
                </button>
              ))}
            </div>

            <div className="field-lbl" style={{ marginTop: 16 }}>rozdzielczość</div>
            <div className="seg">
              {(model ? model.resolutions : ["720p"]).map(r => (
                <button key={r} className={resolution === r ? "on" : ""} onClick={() => pickResolution(r)}>{r}</button>
              ))}
            </div>

            {!isOmni && (
              <>
                <div className="field-lbl" style={{ marginTop: 16 }}>długość</div>
                <div className="seg">
                  {(model ? model.durations_seconds : [4, 6, 8]).map(d => (
                    <button key={d}
                      className={duration === d ? "on" : ""}
                      disabled={isHd && d !== hd.duration_seconds}
                      onClick={() => pickDuration(d)}>{d}s</button>
                  ))}
                </div>
                {isHd && <div className="hint">{resolution} ogranicza do 16:9 i 8 s.</div>}
              </>
            )}
            {isOmni && <div className="hint" style={{ marginTop: 16 }}>Długość dobiera model automatycznie.</div>}
          </div>
        </div>

        {/* 03 — prompt */}
        <div className="section">
          <div className="sec-head">
            <div className="num">03</div>
            <div className="title serif">Prompt</div>
          </div>
          <p className="sec-help">Opisz scenę, ruch kamery, światło, nastrój. Możesz dodać opis dźwięku. Opcjonalnie wgraj klatkę początkową / referencję.</p>
          <div className="sec-body">
            <div className="field-lbl">klatka początkowa / referencja (opcjonalne)</div>
            <div className="vid-imgdrop" onClick={() => imageInputRef.current && imageInputRef.current.click()}>
              {imagePreview ? (
                <div className="vid-imgpick">
                  <img src={imagePreview} alt="klatka początkowa" />
                  <div className="vid-imgmeta">
                    <div className="nm">{imageFile ? imageFile.name : "obraz"}</div>
                    <div className="sub">{isOmni ? "obraz wejściowy Omni" : "wideo powstanie na bazie tej klatki (image-to-video)"}</div>
                  </div>
                  <button type="button" className="btn-mini" onClick={e => { e.stopPropagation(); clearImage(); }}>usuń</button>
                </div>
              ) : (
                <div className="vid-imgempty">
                  <span className="lead">＋ Wgraj zdjęcie (JPG / PNG / WebP)</span>
                  <span className="sub">wideo powstanie na bazie tej klatki — {isOmni ? "obraz wejściowy Omni" : "image-to-video (Veo)"}</span>
                </div>
              )}
            </div>
            <input ref={imageInputRef} type="file" accept="image/*" style={{ display: "none" }}
              onChange={e => { onPickImage(e.target.files && e.target.files[0]); e.target.value = ""; }} />

            <div className="field-lbl" style={{ marginTop: 16 }}>opis (prompt)</div>
            <textarea className="input" rows={5}
              placeholder="np. Powolny najazd kamery na filiżankę parującej kawy na drewnianym stole o poranku, miękkie boczne światło, ciepłe kolory…"
              value={prompt} onChange={e => setPrompt(e.target.value)}
              style={{ resize: "vertical", lineHeight: 1.55 }} />

            <div className="field-lbl" style={{ marginTop: 16 }}>czego unikać (opcjonalne)</div>
            <input className="input" placeholder="np. tekst na ekranie, zniekształcone dłonie, migotanie"
              value={negative} onChange={e => setNegative(e.target.value)} />

            <div className="field-lbl" style={{ marginTop: 16 }}>seed (opcjonalny)</div>
            <input className="input" placeholder="losowy" value={seed}
              onChange={e => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
              style={{ maxWidth: 160, fontFamily: "Geist Mono" }} />
          </div>
        </div>

        {/* foot */}
        <div className="form-foot">
          <div className="foot-summary">
            <div className="foot-lead">{busy ? `Renderuję… ${mm}:${ss}` : "Gotowe do generowania"}</div>
            <div className="foot-meta">
              <span className="mono">{model ? model.label : "—"}</span><span className="dot">·</span>
              <span className="mono">{aspect} · {resolution}{isOmni ? "" : " · " + duration + "s"}</span><span className="dot">·</span>
              <span className="mono">{model && model.audio ? "audio" : "bez audio"}</span>
            </div>
          </div>
          <div className="foot-actions">
            <button className="foot-gen" onClick={handleGenerate} disabled={busy}
              style={busy ? { opacity: .6, cursor: "wait" } : {}}>
              <span className="ico">{Ic.sparkle}</span>
              <span>{busy ? "Generuję…" : "Generuj wideo"}</span>
              <span className="cost">{costLabel}</span>
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
