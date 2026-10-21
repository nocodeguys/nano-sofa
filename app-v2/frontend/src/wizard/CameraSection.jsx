import React from "react";
import { NS_DATA } from "../data.jsx";
import { Section } from "./Section.jsx";

const { CAMERAS, SHOT_TYPES, DETAIL_REGIONS_FABRIC, DETAIL_REGIONS_CORNER,
        CLOSE_REGIONS_BED, CLOSE_REGIONS_SOFA, CAMERA_HEIGHTS, CAMERA_YAWS,
        DEPTHS_OF_FIELD, LENSES, TIMES_OF_DAY, SHADOWS } = NS_DATA;

// Szybki preset → seeded structured fields. Mirrors _CAM_PRESET_TO_STRUCTURED
// in studio/mappings.py (server-side fallback for legacy form posts) but adds
// the lens / DoF / detail-region that the UI also seeds on click. App uses it
// to highlight the matching tile (`matchedPreset`).
export const CAM_PRESET_DEFAULTS = {
  studio: { shot: "hero",          yaw: "34_left",  height: "eye",      lens: "50mm_natural",  dof: "standard" },
  lounge: { shot: "hero",          yaw: "34_right", height: "eye",      lens: "50mm_natural",  dof: "standard" },
  loft:   { shot: "hero",          yaw: "34_left",  height: "eye",      lens: "35mm_wide",     dof: "standard" },
  detail: { shot: "detail_fabric", yaw: "front",    height: "eye",      lens: "100mm_macro",   dof: "macro_shallow", detailRegion: "weave" },
  eye:    { shot: "hero",          yaw: "front",    height: "eye",      lens: "50mm_natural",  dof: "standard" },
  top:    { shot: "hero",          yaw: "front",    height: "overhead", lens: "50mm_natural",  dof: "standard" },
};

/* 08 — camera and framing. Always fully available; a locked backdrop only
   greys out the light selects (the server locks tod / shadow). */
export function CameraSection({ st, set, bgLocked, lensObj, camObj, matchedPreset }) {
  return (
<Section num="08" title="Kamera i kadrowanie" summary={(() => {
  if (st.preserveBaseCamera) return "z bazowego zdjęcia · " + (lensObj?.name?.split(" — ")[0] || "—");
  const shotObj = SHOT_TYPES.find(s => s.id === st.shot);
  let regionTable = null;
  if (st.shot === "detail_fabric") regionTable = DETAIL_REGIONS_FABRIC;
  else if (st.shot === "detail_corner") regionTable = DETAIL_REGIONS_CORNER;
  else if (st.shot === "close_up") regionTable = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
  const regionObj = regionTable ? regionTable.find(r => r.id === st.detailRegion) : null;
  const parts = [shotObj?.name || camObj?.name];
  if (regionObj) parts.push(regionObj.name);
  parts.push(lensObj?.name?.split(" — ")[0] || "—");
  return parts.filter(Boolean).join(" · ");
})()}
  help="Wybierz typ kadru, obrót, obiektyw i głębię. Zbliżenia i detale makro nie dostają planszy tła ani zdjęcia całego mebla, a kontrakt kadrowania katalogu dotyczy tylko ujęcia hero.">
  {bgLocked && (
    <div style={{
      marginBottom:12, padding:"10px 12px", borderRadius:10,
      border:"1px solid rgba(95,122,86,.28)", background:"rgba(95,122,86,.06)",
      fontSize:12, lineHeight:1.5,
    }}>
      Tło katalogowe blokuje tylko światło (południe, miękkie cienie). Kadr, obrót,
      obiektyw, głębia i region są Twoje; render hero jest normalizowany do profilu.
    </div>
  )}
  <label style={{
    display:"flex", alignItems:"flex-start", gap:8, marginBottom:12,
    padding:"10px 12px", border:"1px solid var(--line-2)", borderRadius:10,
    background: st.preserveBaseCamera ? "rgba(95,122,86,.06)" : "var(--bg-1)",
    cursor: st.uploaded ? "pointer" : "not-allowed",
    opacity: st.uploaded ? 1 : 0.55,
    fontSize:12.5, lineHeight:1.45,
  }}>
    <input
      type="checkbox"
      checked={st.uploaded && !!st.preserveBaseCamera}
      disabled={!st.uploaded}
      onChange={e => set({ preserveBaseCamera: e.target.checked })}
      style={{marginTop:2, flexShrink:0}} />
    <span>
      <strong style={{fontWeight:600}}>Zachowaj kąt i sylwetkę z bazowego zdjęcia</strong>
      {!st.uploaded
        ? " — wgraj najpierw zdjęcie bazowe w sekcji 02, żeby włączyć tę opcję."
        : " — kamera, kadrowanie, dystans i pozycja produktu pochodzą wtedy z bazowego zdjęcia (sekcja 02). Idealne do macro / detal crop, kiedy nie chcesz, by model „doframował” pełny produkt. Kolor, materiał, rozmiar i otoczenie nadal pochodzą z kreatora."}
    </span>
  </label>
  {/* Quick preset — clicking a tile also seeds the structured fields
      below (yaw, height, shot type, lens, DoF) so the user has a
      sensible starting point that they can then tweak. Mirrors
      _CAM_PRESET_TO_STRUCTURED in server.py. */}
  <div className="field-lbl">szybki preset</div>
  <div className="cam-grid" style={st.preserveBaseCamera ? {opacity:0.4, pointerEvents:"none"} : undefined}>
    {CAMERAS.map(c => (
      <div key={c.id} className={"cam " + (matchedPreset === c.id ? "sel" : "")} onClick={() => {
        set({ cam: c.id, ...(CAM_PRESET_DEFAULTS[c.id] || {}) });
      }}>
        <div className={"cam-render " + (c.style || "")}>
          <div className="floor"></div>
          <div className="obj"></div>
        </div>
        <div className="cam-meta">
          <div className="cam-name">{c.name}</div>
          <div className="cam-prop">{c.prop}</div>
        </div>
      </div>
    ))}
  </div>

  {/* Shot type — primary framing intent. Detail variants suppress
      the cyclorama SCENE block server-side and emit an OOF-background
      line, so the model actually crops to the detail region instead
      of falling back to a hero packshot. */}
  <div className="field-lbl" style={{marginTop:16}}>typ kadru</div>
  <div className="cam-grid" style={{
    gridTemplateColumns: "repeat(auto-fill,minmax(150px,1fr))",
    ...(st.preserveBaseCamera ? {opacity:0.4, pointerEvents:"none"} : {}),
  }}>
    {SHOT_TYPES.map(s => (
      <div key={s.id} className={"cam " + (st.shot === s.id ? "sel" : "")} onClick={() => {
        // Shot-type picks nudge sensible defaults for lens / DoF /
        // region so the user has a reasonable starting point.
        const isDetail = s.id === "detail_fabric" || s.id === "detail_corner";
        const isCloseUp = s.id === "close_up";
        const patch = { shot: s.id };
        if (isDetail) {
          patch.lens = (st.lens === "35mm_wide" || st.lens === "50mm_natural") ? "100mm_macro" : st.lens;
          patch.dof = "macro_shallow";
          if (s.id === "detail_fabric") patch.detailRegion = DETAIL_REGIONS_FABRIC.some(r => r.id === st.detailRegion) ? st.detailRegion : "weave";
          if (s.id === "detail_corner") patch.detailRegion = DETAIL_REGIONS_CORNER.some(r => r.id === st.detailRegion) ? st.detailRegion : "arm_back_corner";
        }
        if (isCloseUp) {
          // 85 mm short telephoto flatters the close-up framing.
          // Don't downgrade a longer focal length the user already picked.
          if (st.lens === "35mm_wide" || st.lens === "50mm_natural") patch.lens = "85mm_product";
          patch.dof = "shallow";
          const table = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
          const stillValid = table.some(r => r.id === st.detailRegion);
          patch.detailRegion = stillValid ? st.detailRegion : (st.kind === "bed" ? "bed_corner_head" : "sofa_corner");
        }
        set(patch);
      }}>
        <div className="cam-meta" style={{padding:"10px 12px"}}>
          <div className="cam-name">{s.name}</div>
          <div className="cam-prop">{s.hint}</div>
        </div>
      </div>
    ))}
  </div>

  {/* Subject region — visible for detail and close-up shots. The
      region table is product-aware for close-up: bed → bed regions,
      sofa → sofa regions. */}
  {(() => {
    let regions = null;
    let label = "";
    if (st.shot === "detail_fabric") { regions = DETAIL_REGIONS_FABRIC; label = "obszar detalu"; }
    else if (st.shot === "detail_corner") { regions = DETAIL_REGIONS_CORNER; label = "obszar detalu"; }
    else if (st.shot === "close_up") {
      regions = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
      label = "obszar zbliżenia";
    }
    if (!regions) return null;
    return (
      <>
        <div className="field-lbl" style={{marginTop:12}}>{label}</div>
        <div style={{display:"flex", flexWrap:"wrap", gap:8, marginBottom:4}}>
          {regions.map(r => (
            <button key={r.id} type="button"
              onClick={() => set({ detailRegion: r.id })}
              style={{
                padding:"6px 12px", borderRadius:8, fontSize:12.5,
                border: st.detailRegion === r.id ? "1.5px solid var(--ink)" : "1px solid var(--line-2)",
                background: st.detailRegion === r.id ? "var(--bg-1)" : "transparent",
                cursor: "pointer", fontWeight: st.detailRegion === r.id ? 600 : 400,
              }}>{r.name}</button>
          ))}
        </div>
      </>
    );
  })()}

  {/* Yaw / height / DoF — orientation + height + aperture. Yaw and
      height are dimmed for detail shots because the macro crop fills
      the frame regardless of where the camera is yawed. */}
  <div className="tri-row" style={{marginTop:12,
    ...(st.preserveBaseCamera ? {opacity:0.4, pointerEvents:"none"} : {}),
  }}>
    <div style={(st.shot === "detail_fabric" || st.shot === "detail_corner") ? {opacity:0.45, pointerEvents:"none"} : undefined}>
      <div className="field-lbl">kąt (yaw)</div>
      <select className="select" value={st.yaw} onChange={e => set({ yaw: e.target.value })}>
        {CAMERA_YAWS.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
      </select>
    </div>
    <div style={(st.shot === "detail_fabric" || st.shot === "detail_corner") ? {opacity:0.45, pointerEvents:"none"} : undefined}>
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
</Section>
  );
}
