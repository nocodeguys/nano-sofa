/*
  Nano Sofa — Meli (Lab). Wood-colour recolor of solid-wood beds: upload a
  photo, pick a Meli finish (or describe your own), pick an engine — Google
  directly (Nano Banana with the user's own Google key, shared with the studio
  page) or any OpenRouter image model (key shared with /editorial and /lab) —
  and the bed comes back with ONLY its wood recoloured. No upholstery, no
  scene, no camera controls on purpose. Palette + finish photographs come from
  /api/meli/config (app-v2/meli/palette.json + references/), so new colours
  need no frontend change.
*/
import React, { useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/300.css";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "./styles-v2.css";
import "./editorial.css";
import { NanoTopbar, PageIntro } from "./header.jsx";
import { Ic, fileSlug, useMeliSetup, MeliErrors, MeliColorSection, MeliModelSection } from "./meli-common.jsx";

function App() {
  const s = useMeliSetup();
  const { modelId, colorLabel, opacityLabel } = s;

  // ---- form state -----------------------------------------------------------
  const [base, setBase] = useState(null);          // {file, url, w, h}
  const fileRef = useRef(null);
  const [product, setProduct] = useState("");

  const onPickBase = (f) => {
    if (!f) return;
    const url = URL.createObjectURL(f);
    const img = new Image();
    img.onload = () => setBase({ file: f, url, w: img.naturalWidth, h: img.naturalHeight });
    img.src = url;
  };

  // ---- generation -----------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const [shown, setShown] = useState(null);
  const [showBefore, setShowBefore] = useState(false);
  const [history, setHistory] = useState([]);

  const handleGenerate = async () => {
    setError(null);
    if (!base) { setError({ message: "Wgraj zdjęcie łóżka (sekcja 01).", code: "MISSING_BASE_IMAGE" }); return; }
    const invalid = s.validate();
    if (invalid) { setError(invalid); return; }
    if (busy) return;
    setBusy(true);
    setElapsed(0);
    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 250);
    try {
      const fd = new FormData();
      s.appendTo(fd);
      fd.append("base", base.file);
      fd.append("product_name", product.trim());
      const r = await fetch("/api/meli/recolor", { method: "POST", body: fd });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data || !data.success) {
        setError({
          message: (data && data.error) || "Nie udało się zmienić koloru drewna.",
          code: data && data.error_code,
          detail: data && data.error_detail,
        });
      } else {
        const entry = { ...data, product: product.trim(), before: base.url, at: Date.now() };
        setShown(entry);
        setShowBefore(false);
        setHistory(h => [entry, ...h].slice(0, 16));
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
  const frameRatio = base ? `${base.w} / ${base.h}` : "4 / 3";
  const vertical = base ? base.h > base.w : false;
  const stageImg = shown && !showBefore ? shown.image_url : (shown ? shown.before : base && base.url);
  const dlName = shown ? `meli-${fileSlug(shown.product, shown.color) || "lozko"}.${shown.format || "jpg"}` : "";

  return (
    <div className="app-frame">
      <NanoTopbar active="meli" hideApiKey adminLabel="klucz Google / OpenRouter w sekcji Model" />
      <div className="shell">
      {/* ================= LEFT — stage ================= */}
      <section className="stage-pane">
        <div className="stage-canvas" style={{ display: "grid", placeItems: "center", padding: "36px 24px 28px", background: "var(--bg-2)" }}>
          <div style={{ width: "100%", display: "grid", justifyItems: "center" }}>
            <div className="ed-frame" style={{ aspectRatio: frameRatio, width: vertical ? "min(72%, 420px)" : "min(92%, 720px)" }}>
              {busy ? (
                <div className="ed-placeholder">
                  <div className="ed-spinner"></div>
                  Zmieniam kolor drewna… {mm}:{ss}<br />
                  <span style={{ opacity: .6 }}>{modelId} · {colorLabel}</span>
                </div>
              ) : stageImg ? (
                <img src={stageImg} alt={shown && !showBefore ? "po zmianie koloru" : "zdjęcie źródłowe"} />
              ) : (
                <div className="ed-placeholder">
                  Tu pojawi się łóżko w nowym kolorze drewna.<br />
                  <span style={{ opacity: .6 }}>Wgraj zdjęcie po prawej, wybierz kolor i naciśnij „Zmień kolor drewna”.</span>
                </div>
              )}
            </div>

            {shown && !busy && (
              <div className="ed-meta">
                <div className="seg">
                  <button className={showBefore ? "" : "on"} onClick={() => setShowBefore(false)}>po</button>
                  <button className={showBefore ? "on" : ""} onClick={() => setShowBefore(true)}>przed</button>
                </div>
                <a className="ed-dl" href={shown.image_url} download={dlName}>⭳ Pobierz {String(shown.format || "jpg").toUpperCase()}</a>
                <span>{shown.color} · krycie {shown.opacity_label}{shown.opacity !== "sample" ? ` ${shown.opacity}%` : ""}</span><span>·</span>
                <span>{shown.model}</span><span>·</span>
                <span>{shown.resolution}{shown.quality ? ` · ${shown.quality}` : ""} · {shown.aspect}</span><span>·</span>
                <span>≈ ${Number(shown.cost || 0).toFixed(3)}</span><span>·</span>
                <span>{Math.round((shown.elapsed_ms || 0) / 100) / 10}s</span>
              </div>
            )}

            {history.length > 1 && (
              <div className="ed-hist">
                {history.map(h => (
                  <img key={h.generation_id} src={h.image_url} alt={h.color} title={`${h.color} · ${h.model}`}
                    className={shown && shown.generation_id === h.generation_id ? "on" : ""}
                    onClick={() => { setShown(h); setShowBefore(false); }} />
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ================= RIGHT — form ================= */}
      <section className="form-pane">
        <PageIntro eyebrow={<>Lab · Meli · <a href="/">← wróć do zdjęć</a></>}>
          Zmiana koloru drewna na zdjęciu łóżka z litego drewna. Zmienia się wyłącznie drewno łóżka —
          kadr, światło, tło, pościel i wszystkie detale zostają jak na zdjęciu źródłowym.
        </PageIntro>

        <MeliErrors s={s} error={error} />

        {/* 01 — photo */}
        <div className="section">
          <div className="sec-head">
            <div className="num">01</div>
            <div className="title serif">Zdjęcie łóżka</div>
            <div className="summary">{base ? `${base.w}×${base.h}` : "wymagane"}</div>
          </div>
          <p className="sec-help">Zdjęcie, na którym zmieni się tylko kolor drewna. Proporcje wyniku dobieramy do zdjęcia.</p>
          <div className="sec-body">
            <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }}
              onChange={e => { onPickBase(e.target.files && e.target.files[0]); e.target.value = ""; }} />
            <div className={"up-row " + (base ? "has" : "")}
              onClick={() => fileRef.current && fileRef.current.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); onPickBase(e.dataTransfer.files && e.dataTransfer.files[0]); }}>
              <div className="up-thumb">
                {base ? <img src={base.url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : Ic.upload}
              </div>
              <div className="up-body">
                <div className="lead">{base ? base.file.name : "Upuść zdjęcie łóżka tutaj"}</div>
                <div className="help">{base ? "kliknij, żeby podmienić" : "lub kliknij · JPG / PNG / WEBP"}</div>
              </div>
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>model produktu</div>
            <input className="input" placeholder="np. Meli 160" value={product} maxLength={80}
              onChange={e => setProduct(e.target.value)} />
            <div className="hint">zapisywany w metadanych i nazwie pobranego pliku — nie wpływa na prompt</div>
          </div>
        </div>

        <MeliColorSection num="02" s={s} />
        <MeliModelSection num="03" s={s} />

        {/* foot */}
        <div className="form-foot">
          <div className="foot-summary">
            <div className="foot-lead">{busy ? `Zmieniam kolor… ${mm}:${ss}` : "Gotowe do generowania"}</div>
            <div className="foot-meta">
              <span className="mono">{modelId}</span><span className="dot">·</span>
              <span className="mono">{colorLabel || "brak koloru"}</span><span className="dot">·</span>
              <span className="mono">krycie {opacityLabel}</span>
            </div>
          </div>
          <div className="foot-actions">
            <button className="foot-gen" onClick={handleGenerate} disabled={busy}
              style={busy ? { opacity: .6, cursor: "wait" } : {}}>
              <span className="ico">{Ic.sparkle}</span>
              <span>{busy ? "Generuję…" : "Zmień kolor drewna"}</span>
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
