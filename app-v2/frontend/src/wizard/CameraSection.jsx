import React from "react";
import { NS_DATA } from "../data.jsx";
import { Section } from "./Section.jsx";

const { SHOT_TYPES, DETAIL_REGIONS_FABRIC, DETAIL_REGIONS_CORNER,
        CLOSE_REGIONS_BED, CLOSE_REGIONS_SOFA, CAMERA_HEIGHTS, CAMERA_YAWS,
        DEPTHS_OF_FIELD, LENSES, TIMES_OF_DAY, SHADOWS } = NS_DATA;

// The product-page shot list — what a shop like Westwing shows per bed:
// 3/4 hero, front, side profile, back, from above, a close-up of the
// headboard / armrest, and a fabric macro. One click seeds shot / yaw /
// height / region; lens and DoF follow the shot (see framePatch). Lifestyle
// interiors are a background choice (section 01), not a camera one.
const FRAMES = [
  { id: "hero",   name: "3/4 hero",   hint: "główne zdjęcie",  shot: "hero",          yaw: "34_left",    height: "eye" },
  { id: "front",  name: "Front",      hint: "na wprost",       shot: "hero",          yaw: "front",      height: "eye" },
  { id: "side",   name: "Bok",        hint: "profil",          shot: "hero",          yaw: "side_left",  height: "eye" },
  { id: "back",   name: "Tył",        hint: "od tyłu",         shot: "hero",          yaw: "back",       height: "eye" },
  { id: "top",    name: "Z góry",     hint: "45°, aranżacja",  shot: "hero",          yaw: "34_left",    height: "overhead" },
  { id: "close",  name: "Zbliżenie",  hint: "",                shot: "close_up",      yaw: "34_left",    height: "eye" },
  { id: "fabric", name: "Tkanina",    hint: "makro splotu",    shot: "detail_fabric", yaw: "front",      height: "eye", region: "weave" },
];

// The close-up subject differs by product: headboard corner on a bed,
// armrest on a sofa (the regions Westwing / catalogue pages actually show).
function framesFor(kind) {
  return FRAMES.map(f => f.id !== "close" ? f : kind === "bed"
    ? { ...f, hint: "narożnik wezgłowia", region: "bed_corner_head" }
    : { ...f, hint: "podłokietnik",       region: "sofa_armrest" });
}

// Which frame tile the current structured fields correspond to, or null when
// the user has drifted into custom settings. Lens / DoF are refinements and
// do not un-highlight a frame. Also sent as `camera_preset` in the JSON tab.
export function matchFrame(st) {
  for (const f of framesFor(st.kind)) {
    if (f.shot !== st.shot || f.height !== st.height) continue;
    if (f.region ? f.region !== st.detailRegion : f.yaw !== st.yaw) continue;
    return f.id;
  }
  return null;
}

function framePatch(f, bgObj, bgLocked) {
  const patch = { shot: f.shot, yaw: f.yaw, height: f.height, preserveBaseCamera: false };
  if (f.region) patch.detailRegion = f.region;
  if (f.shot === "detail_fabric") Object.assign(patch, { lens: "100mm_macro", dof: "macro_shallow" });
  else if (f.shot === "close_up") Object.assign(patch, { lens: "85mm_product", dof: "shallow" });
  else if (bgLocked) {
    const d = bgObj?.cameraDefaults || {};
    Object.assign(patch, { lens: d.lens || "85mm_product", dof: d.dof || "deep" });
  } else Object.assign(patch, { lens: "50mm_natural", dof: "standard" });
  return patch;
}

// The whole shot list as wizard-state patches, for "Generuj cały zestaw":
// one /api/generate per frame, everything else in the wizard unchanged.
export function frameSet(st, bgObj, bgLocked) {
  return framesFor(st.kind).map(f => ({ id: f.id, name: f.name, patch: framePatch(f, bgObj, bgLocked) }));
}

/* Line pictograms of the furniture from each frame's camera position. */
function FrameGlyph({ id }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinejoin: "round", strokeLinecap: "round" };
  return (
    <svg width="64" height="40" viewBox="0 0 64 40" aria-hidden="true">
      {id === "base" && <g {...p}><rect x="8" y="6" width="48" height="28" rx="2"/><path d="M16 28l10-10 7 7 5-4 10 7"/><circle cx="44" cy="14" r="3"/></g>}
      {id === "hero" && <g {...p}><path d="M10 28l14 6 30-8-14-5z"/><path d="M10 28v3l14 6 30-8v-3"/><path d="M40 21V9l14 4v13"/></g>}
      {id === "front" && <g {...p}><rect x="12" y="8" width="40" height="14" rx="5"/><rect x="8" y="22" width="48" height="10" rx="2"/></g>}
      {id === "side" && <g {...p}><path d="M8 32V8h5v15"/><rect x="8" y="23" width="48" height="9" rx="2"/></g>}
      {id === "back" && <g {...p}><rect x="12" y="6" width="40" height="22" rx="5"/><path d="M8 28h48v4H8z"/></g>}
      {id === "top" && <g {...p}><path d="M14 30l6-24h24l6 24z"/><path d="M21 8h22v5H21z"/><path d="M16 22h32"/></g>}
      {id === "close" && <g {...p}><path d="M14 36V12a8 8 0 0 1 8-8h34"/><path d="M14 26h42"/><circle cx="22" cy="20" r="0.6" fill="currentColor"/></g>}
      {id === "fabric" && <g {...p} strokeWidth="1.1"><path d="M8 10h48M8 17h48M8 24h48M8 31h48"/><path d="M14 6v28M24 6v28M34 6v28M44 6v28M54 6v28" strokeDasharray="3 4"/></g>}
    </svg>
  );
}

/* 08 — camera and framing. Picking a frame is the whole job; the raw
   controls stay available under "Ustawienia zaawansowane". A locked
   backdrop only greys out the light selects (the server locks tod / shadow). */
export function CameraSection({ st, set, bgObj, bgLocked, lensObj, baseCamLocked, frameRun, onGenerateSet, setCost }) {
  const frames = framesFor(st.kind);
  const current = baseCamLocked ? "base" : matchFrame(st);
  const curFrame = frames.find(f => f.id === current);
  const tile = (id, name, hint, onClick, disabled) => (
    <div key={id} className={"cam frame" + (current === id ? " sel" : "") + (disabled ? " off" : "")}
         onClick={disabled ? undefined : onClick} title={disabled ? "wgraj najpierw zdjęcie bazowe (sekcja 02)" : undefined}>
      <div className="frame-glyph"><FrameGlyph id={id} /></div>
      <div className="cam-meta">
        <div className="cam-name">{name}</div>
        {hint && <div className="cam-prop">{hint}</div>}
      </div>
    </div>
  );

  let regions = null;
  if (st.shot === "detail_fabric") regions = DETAIL_REGIONS_FABRIC;
  else if (st.shot === "detail_corner") regions = DETAIL_REGIONS_CORNER;
  else if (st.shot === "close_up") regions = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
  const isDetail = st.shot === "detail_fabric" || st.shot === "detail_corner";
  const lensName = lensObj?.name?.split(" — ")[0] || "—";
  const summary = current === "base" ? "jak na zdjęciu bazowym"
    : curFrame ? curFrame.name + " · " + lensName
    : "własne ustawienia · " + lensName;

  return (
<Section num="08" title="Kadr" summary={summary}
  help="Wybierz jeden kadr na render. Pełna karta produktu to zwykle te siedem ujęć plus aranżacja we wnętrzu (tło z sekcji 01).">
  <div className="cam-grid frame-grid">
    {tile("base", "Jak na zdjęciu", "kąt z sekcji 02", () => set({ preserveBaseCamera: true }), !st.uploaded)}
    {frames.map(f => tile(f.id, f.name, f.hint, () => set(framePatch(f, bgObj, bgLocked))))}
  </div>

  {/* Whole set in one click — the frame tile above only picks the next
      single render; this renders all seven with the rest of the wizard. */}
  <div className="frame-set">
    <button type="button" className="frame-set-btn" disabled={!!frameRun?.busy} onClick={() => onGenerateSet()}>
      {frameRun?.busy
        ? <>Generuję zestaw… {frameRun.done}/{frameRun.total}</>
        : <>Generuj cały zestaw · {frames.length} kadrów <span className="cost">${setCost}</span></>}
    </button>
    {frameRun && !frameRun.busy && (
      <span className="frame-set-note">
        {frameRun.failed.length === 0
          ? `Gotowe ${frameRun.done}/${frameRun.total} — kadry są w galerii.`
          : `Gotowe ${frameRun.done - frameRun.failed.length}/${frameRun.total}. Nie wyszło: ${frameRun.failed.map(f => f.name).join(", ")}.`}
        {frameRun.failed.length > 0 && (
          <button type="button" className="chip" style={{marginLeft:8}}
            onClick={() => onGenerateSet(frameRun.failed.map(f => f.id))}>Ponów nieudane</button>
        )}
      </span>
    )}
    {frameRun?.failed?.length > 0 && !frameRun.busy && (
      <div className="frame-set-err">{frameRun.failed[0].error?.message}</div>
    )}
  </div>

  <details className="cam-advanced">
    <summary>Ustawienia zaawansowane — kadr, obiektyw, światło</summary>

    <div style={baseCamLocked ? {opacity:0.4, pointerEvents:"none"} : undefined}>
      <div className="field-lbl" style={{marginTop:12}}>typ kadru</div>
      <div className="chip-row">
        {SHOT_TYPES.map(s => (
          <button key={s.id} type="button" title={s.hint}
            className={"chip" + (st.shot === s.id ? " on" : "")}
            onClick={() => {
              const patch = { shot: s.id };
              if (s.id === "detail_fabric" || s.id === "detail_corner") {
                patch.lens = (st.lens === "35mm_wide" || st.lens === "50mm_natural") ? "100mm_macro" : st.lens;
                patch.dof = "macro_shallow";
                const table = s.id === "detail_fabric" ? DETAIL_REGIONS_FABRIC : DETAIL_REGIONS_CORNER;
                patch.detailRegion = table.some(r => r.id === st.detailRegion) ? st.detailRegion : table[0].id;
              }
              if (s.id === "close_up") {
                // 85 mm flatters the close-up; never downgrade a longer lens.
                if (st.lens === "35mm_wide" || st.lens === "50mm_natural") patch.lens = "85mm_product";
                patch.dof = "shallow";
                const table = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
                patch.detailRegion = table.some(r => r.id === st.detailRegion) ? st.detailRegion
                  : (st.kind === "bed" ? "bed_corner_head" : "sofa_corner");
              }
              set(patch);
            }}>{s.name}</button>
        ))}
      </div>

      {regions && (
        <>
          <div className="field-lbl" style={{marginTop:12}}>{st.shot === "close_up" ? "obszar zbliżenia" : "obszar detalu"}</div>
          <div className="chip-row">
            {regions.map(r => (
              <button key={r.id} type="button" className={"chip" + (st.detailRegion === r.id ? " on" : "")}
                onClick={() => set({ detailRegion: r.id })}>{r.name}</button>
            ))}
          </div>
        </>
      )}

      {/* Yaw / height are dimmed for detail shots: the macro crop fills the
          frame regardless of where the camera stands. */}
      <div className="tri-row">
        <div style={isDetail ? {opacity:0.45, pointerEvents:"none"} : undefined}>
          <div className="field-lbl">kąt</div>
          <select className="select" value={st.yaw} onChange={e => set({ yaw: e.target.value })}>
            {CAMERA_YAWS.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
          </select>
        </div>
        <div style={isDetail ? {opacity:0.45, pointerEvents:"none"} : undefined}>
          <div className="field-lbl">wysokość kamery</div>
          <select className="select" value={st.height} onChange={e => set({ height: e.target.value })}>
            {CAMERA_HEIGHTS.map(h => <option key={h.id} value={h.id}>{h.name}</option>)}
          </select>
        </div>
        <div>
          <div className="field-lbl">głębia ostrości</div>
          <select className="select" value={st.dof} onChange={e => set({ dof: e.target.value })}>
            {DEPTHS_OF_FIELD.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
      </div>
    </div>

    <div className="tri-row">
      <div>
        <div className="field-lbl">ogniskowa</div>
        <select className="select" value={st.lens} onChange={e => set({ lens: e.target.value })}>
          {LENSES.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </div>
      <div style={bgLocked ? { opacity: 0.45 } : undefined} title={bgLocked ? "zablokowane przez tło katalogowe" : undefined}>
        <div className="field-lbl">pora dnia{bgLocked ? " · katalog" : ""}</div>
        <select className="select" value={bgLocked ? "noon_neutral" : st.tod} disabled={bgLocked}
                onChange={e => set({ tod: e.target.value })}>
          {TIMES_OF_DAY.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </div>
      <div style={bgLocked ? { opacity: 0.45 } : undefined} title={bgLocked ? "zablokowane przez tło katalogowe" : undefined}>
        <div className="field-lbl">cienie{bgLocked ? " · katalog" : ""}</div>
        <select className="select" value={bgLocked ? "soft_diffuse" : st.shadow} disabled={bgLocked}
                onChange={e => set({ shadow: e.target.value })}>
          {SHADOWS.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
    </div>
  </details>
</Section>
  );
}
