// request.js — the ONE place that turns wizard state into a request.
//
// buildRequest(st, ctx) returns the exact multipart entries the server
// receives, a preview object built FROM those entries (so the JSON tab shows
// what is sent, never a parallel reconstruction), and the reference budget:
// which images the server will attach, in order, under the model's cap.
//
// Three callers, one function:
//   mode "generate" → POST /api/generate      (Generuj wariant)
//   mode "set"      → POST /api/generate-set  (Warianty)
//   mode "shoot"    → shared fields of /api/generate-photoshoot* (Seria)
//
// The reference budget mirrors app/core/generator.plan_reference_slots:
// base, scene, [locked moodboard], material macro, colour patch, oblique
// views, light-response, in-use photo, moodboards; detail / close-up shots
// drop the plate and the in-use photo; the cap is the model's max_refs.
// The server remains the authority — this is what the UI promises.

export const TIGHT_SHOTS = ["close_up", "detail_fabric", "detail_corner"];

const PLACEHOLDER_FILE = Symbol("pending-file");

function cameraEntries(st) {
  return [
    ["cam", st.cam],
    ["lens", st.lens],
    ["tod", st.tod],
    ["shadow", st.shadow],
    ["shot", st.shot || ""],
    ["yaw", st.yaw || ""],
    ["height", st.height || ""],
    ["dof", st.dof || ""],
    ["detail_region", st.detailRegion || ""],
  ];
}

function beddingEntries(st) {
  if (st.kind !== "bed") return [];
  return [
    ["bedding", st.bedding || ""],
    ["bedding_custom", st.beddingCustom || ""],
    ["throw", st.throw || ""],
    ["tidy", st.tidy || ""],
    ["density", st.density || ""],
    ["accents", (st.accents || []).join(",")],
    ["bed_note", st.bedNote || ""],
  ];
}

function outputEntries(st) {
  return [
    ["model", st.model],
    ["aspect", st.aspect],
    ["res", st.res],
    ["seed", st.seed || ""],
    ["output_format", st.outputFormat || "jpg"],
    ["output_quality", String(st.outputQuality || 82)],
  ];
}

/**
 * Which images the server will attach for this state, in slot order.
 * Returns [{ role, label, source }]; `source` is a short human label.
 */
export function referenceBudget(st, ctx) {
  const { bgObj, bgLocked, modelObj, catalogRefs = {}, colorObj, prevRender, mode = "generate" } = ctx;
  const tight = TIGHT_SHOTS.includes(st.shot);
  const refs = catalogRefs[st.mat] || {};
  const hex = st.color === "custom" ? (st.colorCustomHex || "") : (colorObj?.hex || "");
  const want = [];
  want.push({ role: "base_product", label: "zdjęcie bazowe", source: st.baseFileName || "base" });

  // Scene slot: the previous render (flagged), the user's photo, or the
  // locked backdrop's plate — never more than one, never for tight shots
  // when it is the plate.
  if (!bgLocked && prevRender) {
    want.push({ role: "scene", label: "poprzedni render jako scena", source: "ostatni render" });
  } else if (!bgLocked && st.bg === "custom" && st.bgFile) {
    want.push({ role: "scene", label: "własne zdjęcie tła", source: st.bgFile.name });
  } else if (bgLocked && bgObj?.plate && !tight) {
    want.push({ role: "scene", label: "plansza cykloramy", source: bgObj.plate });
  }

  const moodboards = bgLocked || mode !== "generate" ? [] : st.refs.filter(r => r && r.file);
  let extraIndex = 1;
  if (!bgLocked && st.refsLock && moodboards.length) {
    const m = moodboards[0];
    want.push({ role: "extra_reference_1", label: "wzorzec (reference lock)", source: m.name });
    extraIndex = 2;
  }
  if (refs.macro) want.push({ role: "material_macro", label: "makro tkaniny", source: st.mat });
  if (hex) want.push({ role: "color_patch", label: "plamka koloru", source: hex.toUpperCase() });
  if (refs.left) want.push({ role: "material_left", label: "tkanina pod kątem (L)", source: st.mat });
  if (refs.right) want.push({ role: "material_right", label: "tkanina pod kątem (P)", source: st.mat });
  if (refs.behavior) want.push({ role: "material_behavior", label: "tkanina w świetle", source: st.mat });
  if (refs.application && !tight) want.push({ role: "material_application", label: "tkanina na meblu", source: st.mat });
  const rest = (!bgLocked && st.refsLock) ? moodboards.slice(1) : moodboards;
  for (const m of rest) {
    want.push({ role: `extra_reference_${extraIndex++}`, label: "moodboard", source: m.name });
  }

  const cap = Math.max(1, modelObj?.max_refs || 3);
  return { attached: want.slice(0, cap), dropped: want.slice(cap), cap };
}

/**
 * The request for the current state.
 *
 * ctx: { mode, isLab, apiKey, oaKey, quality, effectiveLegs, customColorText,
 *        bgObj, bgLocked, prevRender (File | "pending" | null),
 *        variantColors, variantMaterials, catalogRefs, colorObj, matObj,
 *        sizeObj, modelObj, matchedPreset, bedLegsHidden }
 */
export function buildRequest(st, ctx) {
  const {
    mode = "generate", isLab = false, apiKey = "", oaKey = "", quality = "",
    effectiveLegs, customColorText = "", bgObj, bgLocked = false, prevRender = null,
    variantColors = [], variantMaterials = [], colorObj, matObj, sizeObj,
    matchedPreset = null, bedLegsHidden = false,
  } = ctx;

  const entries = [];
  const files = [];
  const push = (name, value) => entries.push([name, value]);
  const pushFile = (name, file, label) => {
    if (file instanceof File) { entries.push([name, file]); files.push({ field: name, name: file.name, size: file.size }); }
    else if (file) { entries.push([name, PLACEHOLDER_FILE]); files.push({ field: name, name: label || "(plik)", size: null, pending: true }); }
  };

  push("api_key", (apiKey || "").trim());
  if (isLab) { push("openai_key", (oaKey || "").trim()); if (quality) push("quality", quality); }
  push("kind", st.kind);

  if (mode === "set") {
    push("colors_csv", variantColors.join(","));
    push("materials_csv", variantMaterials.join(","));   // empty → server reuses `mat`
  }
  if (mode !== "shoot") {
    push("color", st.color);
    push("mat", st.mat);
  }
  push("color_custom", customColorText);
  push("mat_notes", st.matNotes || "");
  push("size", st.size);
  push("legs", effectiveLegs);
  for (const e of cameraEntries(st)) push(...e);

  if (mode !== "shoot") {
    // ONE background id; the server decides locks / normalize / transparency.
    push("background", st.bg || "");
    if (st.bg === "custom") push("env_note", st.bgNote || "");
  }
  for (const e of beddingEntries(st)) push(...e);
  for (const e of outputEntries(st)) push(...e);

  if (mode !== "shoot") {
    pushFile("base_image", st.baseFile, st.baseFileName);
    // Scene: the previous render (flagged as a product render) beats the
    // custom photo; neither under a locked backdrop, whose plate is the authority.
    if (!bgLocked && prevRender) {
      pushFile("scene_image", prevRender, "ostatni render");
      push("scene_from_render", "1");
    } else if (!bgLocked && st.bg === "custom" && st.bgFile) {
      pushFile("scene_image", st.bgFile);
    }
  }
  if (mode === "generate" && !bgLocked) {
    const picked = st.refs.filter(r => r && r.file instanceof File);
    for (const r of picked) pushFile("references", r.file);
    if (picked.length && st.refsLock) push("refs_lock", "1");
    if (st.preserveBaseCamera) push("preserve_base", "1");
  }

  const endpoint = mode === "set" ? "/api/generate-set"
    : mode === "shoot" ? "/api/generate-photoshoot" : "/api/generate";
  const budget = referenceBudget(st, ctx);

  // Preview = the entries, masked keys, files by name. Plus the readable
  // summary the JSON tab always carried (stable English ids).
  const fields = {};
  for (const [k, v] of entries) {
    if (v === PLACEHOLDER_FILE || v instanceof File) continue;
    fields[k] = (k === "api_key" || k === "openai_key") ? (v ? "•••" : "") : v;
  }
  const preview = {
    endpoint,
    wire: { fields, files },
    will_attach: budget.attached.map((r, i) => `${i + 1}. ${r.role} — ${r.label}`),
    dropped_over_cap: budget.dropped.map(r => r.role),
    summary: {
      product: { type: st.kind, base: st.uploaded ? st.baseFileName || "base.jpg" : null },
      variant: {
        color: st.color === "custom"
          ? { custom: st.colorCustom || null, hex: st.colorCustomHex || null }
          : { id: colorObj?.id, hex: colorObj?.hex },
        material: { id: matObj?.id, notes: st.matNotes || null },
        size: { id: sizeObj?.id, dim: sizeObj?.dim },
        legs: bedLegsHidden ? "disabled_for_bed" : st.legs,
      },
      scene: {
        background: { kind: bgObj?.kind, id: bgObj?.id, locked: bgLocked,
                      note: st.bg === "custom" ? (st.bgNote || null) : null },
        camera_preset: matchedPreset,
        shot: st.shot,
        detail_region: TIGHT_SHOTS.includes(st.shot) ? st.detailRegion : null,
        yaw: st.yaw, camera_height: st.height, depth_of_field: st.dof, lens: st.lens,
        time_of_day: bgLocked ? "noon_neutral (katalog)" : st.tod,
        shadows: bgLocked ? "soft_diffuse (katalog)" : st.shadow,
      },
      output: { model: st.model, aspect: st.aspect, resolution: (st.res || "").split(" ")[0], seed: st.seed || null },
    },
  };
  return { endpoint, entries, files, preview, budget };
}

/** FormData from entries; pending placeholders (no File yet) are skipped. */
export function toFormData(entries) {
  const fd = new FormData();
  for (const [k, v] of entries) {
    if (v === PLACEHOLDER_FILE) continue;
    fd.append(k, v);
  }
  return fd;
}
