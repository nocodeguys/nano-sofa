/*
  Nano Sofa — Meli Batch (Lab). The /meli wood recolor over a whole set of bed
  photos: drop in up to MAX_PHOTOS photos, pick one wood colour (a Meli palette
  colour, or your own with sample photographs) and one click recolours them
  all. Each photo is one /api/meli/recolor call — the same prompt, references
  and engines as /meli — sent with match_source so the result comes back at
  that photo's own proportions and pixel size. A few run at a time; a tile that
  failed or came out wrong can be re-run alone.
*/
import React, { useState, useRef, useEffect } from "react";
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

const MAX_PHOTOS = 20;
const PARALLEL = 3;   // requests in flight at once

let nextId = 1;

function stem(name) {
  return (name || "zdjecie").replace(/\.[^.]+$/, "").replace(/[\\/:*?"<>|]+/g, "-");
}

function App() {
  const s = useMeliSetup();
  const { modelId, colorLabel, opacityLabel } = s;

  // ---- photos ---------------------------------------------------------------
  // {id, file, url, status: "idle"|"queued"|"running"|"done"|"error", result, error}
  const [items, setItems] = useState([]);
  const [product, setProduct] = useState("");
  const fileRef = useRef(null);
  const patch = (id, change) => setItems(list => list.map(it => it.id === id ? { ...it, ...change } : it));

  const addPhotos = (files) => {
    const picked = [...(files || [])].filter(f => f.type.startsWith("image/"));
    if (!picked.length) return;
    setItems(list => {
      const room = MAX_PHOTOS - list.length;
      if (picked.length > room) {
        setError({ message: `Limit to ${MAX_PHOTOS} zdjęć w jednej partii — nadmiarowe pominięto.`, code: "TOO_MANY_PHOTOS" });
      }
      return [...list, ...picked.slice(0, Math.max(0, room)).map(f => (
        { id: nextId++, file: f, url: URL.createObjectURL(f), status: "idle", result: null, error: null }
      ))];
    });
  };
  const removePhoto = (id) => setItems(list => list.filter(it => it.id !== id));

  // ---- run ------------------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [showBefore, setShowBefore] = useState(false);
  const [zipBusy, setZipBusy] = useState(false);
  const abortRef = useRef(null);
  useEffect(() => () => abortRef.current && abortRef.current.abort(), []);

  const recolorOne = async (item, signal) => {
    patch(item.id, { status: "running", error: null });
    try {
      const fd = new FormData();
      s.appendTo(fd);
      fd.append("base", item.file);
      fd.append("product_name", product.trim());
      fd.append("match_source", "1");
      const r = await fetch("/api/meli/recolor", { method: "POST", body: fd, signal });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data || !data.success) {
        patch(item.id, { status: "error", error: {
          message: (data && data.error) || "Nie udało się zmienić koloru drewna.",
          code: data && data.error_code, detail: data && data.error_detail } });
      } else {
        patch(item.id, { status: "done", result: { ...data, label: colorLabel || "próbka" } });
      }
    } catch (e) {
      patch(item.id, signal.aborted
        ? { status: item.result ? "done" : "idle" }
        : { status: "error", error: { message: "Błąd sieci lub przekroczono czas oczekiwania.", code: "NETWORK_TIMEOUT" } });
    }
  };

  // Recolour `targets` a few at a time; the rest wait as "queued".
  const run = async (targets) => {
    setError(null);
    if (busy) return;
    if (!targets.length) { setError({ message: "Dodaj zdjęcia łóżek (sekcja 01).", code: "MISSING_BASE_IMAGE" }); return; }
    const invalid = s.validate();
    if (invalid) { setError(invalid); return; }
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setShowBefore(false);
    const ids = new Set(targets.map(t => t.id));
    setItems(list => list.map(it => ids.has(it.id) ? { ...it, status: "queued", error: null } : it));
    const queue = [...targets];
    const worker = async () => {
      while (queue.length && !controller.signal.aborted) {
        await recolorOne(queue.shift(), controller.signal);
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALLEL, queue.length) }, worker));
    // Whatever never started goes back to its previous state.
    setItems(list => list.map(it => it.status === "queued" ? { ...it, status: it.result ? "done" : "idle" } : it));
    setBusy(false);
  };
  const stop = () => abortRef.current && abortRef.current.abort();

  const done = items.filter(it => it.result);
  const failed = items.filter(it => it.status === "error");
  const inRun = items.filter(it => it.status === "queued" || it.status === "running").length;
  const totalCost = done.reduce((sum, it) => sum + Number(it.result.cost || 0), 0);
  const dlName = (it) => `${stem(it.file.name)}-${fileSlug(it.result.label) || "meli"}.${it.result.format || "jpg"}`;

  const downloadAll = async () => {
    if (!done.length || zipBusy) return;
    setZipBusy(true);
    try {
      const zipName = `meli-${fileSlug(product, done[0].result.label) || "partia"}.zip`;
      const r = await fetch("/api/outputs/zip", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: done.map(it => ({ url: it.result.image_url, filename: dlName(it) })), zip_name: zipName }) });
      if (!r.ok) throw new Error(`Nie udało się spakować zdjęć (${r.status}).`);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = zipName; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      setError({ message: e.message || "Nie udało się pobrać paczki.", code: "ZIP_FAILED" });
    } finally {
      setZipBusy(false);
    }
  };

  const footLead = busy
    ? `Zmieniam kolor… ${items.length - inRun}/${items.length}`
    : done.length ? `Gotowe: ${done.length} z ${items.length}` : "Gotowe do generowania";

  return (
    <div className="app-frame">
      <NanoTopbar active="meli-batch" hideApiKey adminLabel="klucz Google / OpenRouter w sekcji Model" />
      <div className="shell">
      {/* ================= LEFT — grid of photos ================= */}
      <section className="stage-pane">
        <div className="stage-canvas mb-stage">
          {items.length === 0 ? (
            <div className="ed-placeholder mb-empty">
              Tu pojawią się zdjęcia łóżek w nowym kolorze drewna.<br />
              <span style={{ opacity: .6 }}>Dodaj zdjęcia po prawej, wybierz kolor i naciśnij „Zmień kolor na wszystkich”.</span>
            </div>
          ) : (
            <>
              <div className="mb-bar">
                <div className="seg">
                  <button className={showBefore ? "" : "on"} onClick={() => setShowBefore(false)}>po</button>
                  <button className={showBefore ? "on" : ""} onClick={() => setShowBefore(true)}>przed</button>
                </div>
                <span className="mb-count">
                  {done.length}/{items.length} gotowych{failed.length ? ` · ${failed.length} z błędem` : ""}
                  {totalCost > 0 ? ` · ≈ $${totalCost.toFixed(3)}` : ""}
                </span>
                {failed.length > 0 && !busy && (
                  <button className="mb-btn" onClick={() => run(failed)}>ponów nieudane</button>
                )}
                {done.length > 0 && (
                  <button className="ed-dl mb-zip" onClick={downloadAll} disabled={zipBusy}>
                    {zipBusy ? "Pakuję…" : `↓ Pobierz wszystkie (${done.length}) · ZIP`}
                  </button>
                )}
              </div>
              <div className="mb-grid">
                {items.map(it => {
                  const after = it.result && !showBefore;
                  return (
                    <figure key={it.id} className={"mb-tile " + it.status}>
                      <div className="mb-img">
                        <img src={after ? it.result.image_url : it.url} alt={after ? "po zmianie koloru" : "zdjęcie źródłowe"} />
                        {(it.status === "running" || it.status === "queued") && (
                          <div className="mb-veil">
                            {it.status === "running" ? <div className="ed-spinner"></div> : null}
                            {it.status === "running" ? "zmieniam kolor…" : "w kolejce"}
                          </div>
                        )}
                        {it.status === "error" && (
                          <div className="mb-veil err" title={it.error.detail || ""}>
                            <strong>{it.error.code || "Błąd"}</strong>
                            {it.error.message}
                          </div>
                        )}
                        {!busy && (
                          <button type="button" className="mb-x" title="usuń zdjęcie z partii" onClick={() => removePhoto(it.id)}>×</button>
                        )}
                      </div>
                      <figcaption>
                        <span className="nm" title={it.file.name}>{it.file.name}</span>
                        {it.result && <a href={it.result.image_url} download={dlName(it)} title="pobierz">↓</a>}
                        {!busy && (it.result || it.status === "error") && (
                          <button type="button" title="zmień kolor tego zdjęcia jeszcze raz" onClick={() => run([it])}>↻</button>
                        )}
                      </figcaption>
                    </figure>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </section>

      {/* ================= RIGHT — form ================= */}
      <section className="form-pane">
        <PageIntro eyebrow={<>Lab · Meli Batch · <a href="/meli">← pojedyncze zdjęcie</a></>}>
          Zmiana koloru drewna na wielu zdjęciach łóżek naraz. Na każdym zdjęciu zmienia się wyłącznie drewno
          ramy łóżka — kadr, światło, tło, pościel i wszystkie detale zostają jak na zdjęciu źródłowym,
          a wynik wraca w tym samym rozmiarze.
        </PageIntro>

        <MeliErrors s={s} error={error} />

        {/* 01 — photos */}
        <div className="section">
          <div className="sec-head">
            <div className="num">01</div>
            <div className="title serif">Zdjęcia łóżek</div>
            <div className="summary">{items.length ? `${items.length} / ${MAX_PHOTOS}` : "wymagane"}</div>
          </div>
          <p className="sec-help">Do {MAX_PHOTOS} zdjęć w jednej partii. Każde dostaje ten sam kolor drewna i wraca we własnych proporcjach i rozmiarze.</p>
          <div className="sec-body">
            <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: "none" }}
              onChange={e => { addPhotos(e.target.files); e.target.value = ""; }} />
            <div className={"up-row " + (items.length ? "has" : "")}
              onClick={() => !busy && fileRef.current && fileRef.current.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); if (!busy) addPhotos(e.dataTransfer.files); }}>
              <div className="up-thumb">{Ic.upload}</div>
              <div className="up-body">
                <div className="lead">{items.length ? `Dodano ${items.length} — upuść kolejne zdjęcia` : "Upuść zdjęcia łóżek tutaj"}</div>
                <div className="help">lub kliknij i zaznacz kilka plików · JPG / PNG / WEBP</div>
              </div>
            </div>
            {items.length > 0 && !busy && (
              <button className="meli-own" style={{ marginTop: 10 }} onClick={() => setItems([])}>wyczyść partię</button>
            )}

            <div className="field-lbl" style={{ marginTop: 14 }}>model produktu</div>
            <input className="input" placeholder="np. Meli 160" value={product} maxLength={80}
              onChange={e => setProduct(e.target.value)} />
            <div className="hint">zapisywany w metadanych i nazwie paczki ZIP — nie wpływa na prompt</div>
          </div>
        </div>

        <MeliColorSection num="02" s={s} />
        <MeliModelSection num="03" s={s} fixedSize />

        {/* foot */}
        <div className="form-foot">
          <div className="foot-summary">
            <div className="foot-lead">{footLead}</div>
            <div className="foot-meta">
              <span className="mono">{modelId}</span><span className="dot">·</span>
              <span className="mono">{colorLabel || (s.customRefs.length ? "wg próbki" : "brak koloru")}</span><span className="dot">·</span>
              <span className="mono">krycie {opacityLabel}</span><span className="dot">·</span>
              <span className="mono">{items.length} zdj.</span>
            </div>
          </div>
          <div className="foot-actions">
            {busy && <button className="copy" onClick={stop}>zatrzymaj</button>}
            <button className="foot-gen" onClick={() => run(items)} disabled={busy}
              style={busy ? { opacity: .6, cursor: "wait" } : {}}>
              <span className="ico">{Ic.sparkle}</span>
              <span>{busy ? "Generuję…" : `Zmień kolor na wszystkich${items.length ? ` (${items.length})` : ""}`}</span>
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
