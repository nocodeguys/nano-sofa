/* global React */
const { useState, useMemo, useEffect, useCallback } = React;

/* ======================================================
   Data — colors, materials, sizes, cameras, legs
   ====================================================== */
// Upholstery colour GROUPS from the TreeTale fabric matrix (Generator AI).
// Each group is one pickable AI colour; `covers` lists the real fabric SKUs it
// stands in for (shown on hover). English prompt terms live in server.py
// _COLOR_PL_TO_EN keyed by the same id.
const COLORS = [
  { id: "cream",      name: "śmietankowy",    hex: "#E7E0D6", fabric: true, covers: "glam-2, baloo-2073, cremona-1, perfecto-1, bellini-5, vibe-3" },
  { id: "sand",       name: "beż piaskowy",   hex: "#D9D4CD", fabric: true, covers: "baloo-2074, cremona-2, rouge-2, bellini-20, velutto-2" },
  { id: "greige",     name: "greige",         hex: "#C3BEB6", fabric: true, covers: "barrel-3, lumi-6, cremona-14, bella-5, rouge-1" },
  { id: "cappuccino", name: "cappuccino",     hex: "#B4A799", fabric: true, covers: "vibe-6, vibe-8, soft-31, soft-33, perfecto-7" },
  { id: "taupe",      name: "taupe",          hex: "#938A83", fabric: true, covers: "glam-4, barrel-9, lumi-11, cremona-24, vibe-21, miscanto-30, bellini-6, rouge-4, velutto-29" },
  { id: "caramel",    name: "karmelowy",      hex: "#9F693D", fabric: true, covers: "glam-7, baloo-2077, vibe-7, vibe-19, perfecto-52, soft-2, bellini-7, rouge-10" },
  { id: "choc",       name: "czekoladowy",    hex: "#4E3E2F", fabric: true, covers: "miscanto-80, toro-45, toro-50, bella-70, soft-34, vena-14, velutto-6" },
  { id: "ash",        name: "srebrzysty",     hex: "#BCBCBC", fabric: true, covers: "glam-10, baloo-2085, barrel-80, vega-1, cremona-4, rouge-14, bellini-1, velutto-15" },
  { id: "steelgrey",  name: "szary stalowy",  hex: "#908F8B", fabric: true, covers: "vega-11, lumi-84, miscanto-10, toro-140, bella-55, perfecto-4, vena-3, vena-9" },
  { id: "graphite",   name: "grafitowy",      hex: "#656F70", fabric: true, covers: "barrel-21, vega-26, vega-90, miscanto-40, vena-5, vena-8" },
  { id: "olive",      name: "oliwkowy",       hex: "#6A7763", fabric: true, covers: "baloo-2090, barrel-38, vega-37, lumi-35, cremona-34, toro-135, bella-85, perfecto-39" },
  { id: "forest",     name: "butelkowa zieleń", hex: "#2E3B2C", fabric: true, covers: "miscanto-75, bella-75, velutto-27" },
  { id: "rose",       name: "brudny róż",     hex: "#D4BABA", fabric: true, covers: "glam-15, lumi-52" },
  { id: "steelblue",  name: "stalowy błękit", hex: "#8A979D", fabric: true, covers: "vega-80, bella-30" },
  { id: "black",      name: "czarny",         hex: "#17161A", fabric: true, covers: "soft-11" },
];

// Fabric TYPES from the TreeTale matrix (Matryca AI Tkaniny). `tex` maps to a
// .fabric-overlay preview class; the rich texture/drape/features prompt lives
// in server.py _MATERIAL_TEXTURE_EN keyed by the same id.
const MATERIALS = [
  { id: "knit",        name: "dzianina",  prop: "miękka, gładka",           tex: "linen",    finish: "matowy" },
  { id: "boucle",      name: "bouclé",    prop: "pętelkowy, mięsisty",      tex: "boucle",   finish: "matowy" },
  { id: "basketweave", name: "plecionka", prop: "splot koszykowy",          tex: "weave",    finish: "matowy" },
  { id: "chenille",    name: "szenila",   prop: "aksamitny, ciepły",        tex: "chenille", finish: "delikatny połysk" },
  { id: "ecoleather",  name: "eco skóra", prop: "gładka, łatwa w czyszczeniu", tex: "leather", finish: "połysk" },
  { id: "velour",      name: "welur",     prop: "gęsty włos, połysk",       tex: "velvet",   finish: "połysk" },
];

const SIZES_SOFA = [
  { id: "1", name: "fotel",       cushions: 1, dim: "90×90 cm" },
  { id: "2", name: "2-osobowa",   cushions: 2, dim: "180×95 cm" },
  { id: "3", name: "3-osobowa",   cushions: 3, dim: "220×95 cm" },
  { id: "4", name: "4-osobowa",   cushions: 4, dim: "280×95 cm" },
  { id: "L", name: "narożnik L",  cushions: 5, dim: "260×170 cm" },
  { id: "U", name: "narożnik U",  cushions: 6, dim: "300×220 cm" },
];
const SIZES_BED = [
  { id: "90",  name: "pojedyncze", cushions: 1, dim: "90×200 cm" },
  { id: "120", name: "francuskie", cushions: 2, dim: "120×200 cm" },
  { id: "140", name: "podwójne",   cushions: 2, dim: "140×200 cm" },
  { id: "160", name: "queen",      cushions: 3, dim: "160×200 cm" },
  { id: "180", name: "king",       cushions: 3, dim: "180×200 cm" },
];

const CAMERAS = [
  { id: "studio", name: "Studio biały",   prop: "katalog, cienie miękkie", style: "studio" },
  { id: "lounge", name: "Salon rodzinny", prop: "lifestyle, dzienne",      style: "lounge" },
  { id: "loft",   name: "Loft skandynaw.",prop: "drewno, naturalne",       style: "" },
  { id: "detail", name: "Detal makro",    prop: "tekstura tkaniny",        style: "detail" },
  { id: "eye",    name: "Wysokość oczu",  prop: "3/4, neutralny baseline", style: "eye" },
  { id: "top",    name: "Z góry 45°",     prop: "schemat / aranżacja",     style: "studio" },
];

const ENVIRONMENTS = [
  // Locked cyclorama profiles — guarantee identical backdrop look across renders.
  { id: "cyclorama_warm",    name: "Cyklorama ciepła",   prop: "warm catalog white #F4F0E5", grad: "linear-gradient(180deg,#F4F0E5,#E4DBC6)",      acc: "#E8DEC9" },
  { id: "cyclorama_neutral", name: "Cyklorama neutralna",prop: "pure photo white #FAFAFA",    grad: "linear-gradient(180deg,#FAFAFA,#E8E8E8)",      acc: "#F0F0F0" },
  { id: "cyclorama_grey",    name: "Cyklorama szara",    prop: "packshot grey #DCDCDC",       grad: "linear-gradient(180deg,#DEDED9,#9C9D97)",      acc: "#C2C3BD" },
  { id: "cyclorama_architectural", name: "Architektoniczna ivory", prop: "high-key ivory #F7F3EA, cień w prawo", grad: "linear-gradient(180deg,#F1ECDE 0%,#F7F3EA 60%,#FCF9F2 100%)", acc: "#EFE9DA" },
  { id: "cyclorama_softlight",     name: "Softlight minimal",      prop: "off-white #FAF8F6, płaskie tło, zero plam",     grad: "linear-gradient(180deg,#FAF8F6,#FAF8F6)",                     acc: "#F2EFEB" },
  { id: "cyclorama_paperwhite",    name: "Paperwhite bright",      prop: "jasne off-white #FCFAF7, lifted high-key",      grad: "linear-gradient(180deg,#FCFAF7,#FCFAF7)",                     acc: "#F5F2ED" },
  // Legacy ids — kept for back-compat; both resolve to cyclorama_warm/grey server-side.
  { id: "studio_white",  name: "Białe studio (legacy)",   prop: "→ cyklorama ciepła",      grad: "linear-gradient(180deg,#F4F0E5,#DCD3BD)",      acc: "#E8DEC9" },
  { id: "studio_grey",   name: "Studio szare (legacy)",   prop: "→ cyklorama szara",       grad: "linear-gradient(180deg,#DEDED9,#9C9D97)",      acc: "#C2C3BD" },
  { id: "scandi",        name: "Salon skandynawski",  prop: "drewno, biel, rośliny",  grad: "linear-gradient(180deg,#EFE8D6,#C9B796)",      acc: "#B89F7A" },
  { id: "loft",          name: "Loft industrial",     prop: "cegła, beton, metal",    grad: "linear-gradient(180deg,#C9B79C,#7C6B57)",      acc: "#8E7B62" },
  { id: "japandi",       name: "Japandi",             prop: "ciepła minimalistyka",   grad: "linear-gradient(180deg,#E9DDC4,#B59A74)",      acc: "#A88560" },
  { id: "boho",          name: "Boho ciepłe",         prop: "tekstylia, ratan",       grad: "linear-gradient(180deg,#E5C6A0,#A8754C)",      acc: "#C39065" },
  { id: "dark_moody",    name: "Mroczne wnętrze",     prop: "ciemne ściany, lampy",   grad: "linear-gradient(180deg,#3D3A33,#191815)",      acc: "#5A4F3F" },
  { id: "garden",        name: "Taras / ogród",       prop: "zieleń, światło dzienne",grad: "linear-gradient(180deg,#C8D4B6,#7E8E6A)",      acc: "#9CAC83" },
  { id: "showroom",      name: "Showroom marki",      prop: "lekka aranżacja prod.",  grad: "linear-gradient(180deg,#EAE2CE,#B7AE92)",      acc: "#D2C5A3" },
  { id: "transparent",   name: "Bez tła (PNG)",       prop: "alfa, do composu",       grad: "repeating-conic-gradient(#E8E3D5 0% 25%,#F4F0E5 0% 50%) 0/16px 16px", acc: "#FBFAF6", checker: true },
  { id: "custom",        name: "Własne zdjęcie tła",  prop: "wgraj swoje wnętrze",    grad: "repeating-linear-gradient(135deg,#EDE9DF 0 8px,#F4F1EA 8px 16px)", acc: "#D2CCBC", custom: true },
];

const LEGS = [
  { id: "keep",    name: "zachowaj obecne" },
  { id: "wood",    name: "drewniane stożkowe" },
  { id: "metal",   name: "metalowe szpilki" },
  { id: "block",   name: "bloki drewniane" },
  { id: "hidden",  name: "ukryte / cokół" },
  { id: "swivel",  name: "obrotowa stopa" },
];

/* Lens / time-of-day / shadow option tables.
   Polish `name` is UI display only — the English `id` is what crosses the
   network boundary and what the server resolves into a prompt fragment. */
const LENSES = [
  { id: "35mm_wide",    name: "35 mm — szeroki kontekst" },
  { id: "50mm_natural", name: "50 mm — naturalna" },
  { id: "85mm_product", name: "85 mm — produktowa" },
  { id: "100mm_macro",  name: "100 mm makro" },
];

const TIMES_OF_DAY = [
  { id: "morning_cool", name: "poranek — chłodne, miękkie" },
  { id: "noon_neutral", name: "południe — neutralne" },
  { id: "golden_hour",  name: "złota godzina — ciepłe" },
  { id: "evening_lamp", name: "wieczór — lampy" },
];

const SHADOWS = [
  { id: "soft_diffuse",  name: "miękkie rozproszone" },
  { id: "directional_4", name: "kierunkowe — okno" },
  { id: "hard_studio_5", name: "twarde — studio" },
];

/* Shot type — the primary framing intent. Drives the `framing` line in the
   generated prompt.

   `close_up` is a tight crop on a named anatomy region (corner / side /
   back / headboard etc) — only part of the product is visible but the
   backdrop is still partially in frame, so the cyclorama SCENE block is
   kept as-is.

   `detail_fabric` and `detail_corner` are macro-distance shots — at that
   range the cyclorama is not in the frame, so the SCENE block is replaced
   with an OOF-background line. Without that swap the cyclorama text
   overrides the detail crop instruction (the "can't generate detail
   photo" bug). */
const SHOT_TYPES = [
  { id: "wide",          name: "Szeroki — z otoczeniem",     hint: "produkt zajmuje centralną trzecią część kadru" },
  { id: "hero",          name: "Hero — pełny produkt",       hint: "klasyczny katalog, oddech wokół" },
  { id: "three_quarter", name: "3/4 — produkt wypełnia",     hint: "delikatne kadrowanie na krawędziach" },
  { id: "cropped",       name: "Kadr kompozycyjny",          hint: "tnij wzdłuż trójpodziału, produkt dominuje" },
  { id: "close_up",      name: "Close-up — fragment produktu", hint: "róg, bok, tył, wezgłowie — wybierz obszar" },
  { id: "detail_fabric", name: "Detal makro — tkanina",      hint: "ekstremalne zbliżenie na strukturę materiału" },
  { id: "detail_corner", name: "Detal — szew / złącze",      hint: "ciasny makro na szew, joinery, mocowanie nóżki" },
];

/* Detail / close-up subject regions.
   - DETAIL_REGIONS_FABRIC → fabric-texture macro (extreme close-up, no product silhouette)
   - DETAIL_REGIONS_CORNER → small mechanical detail (stitching, joinery)
   - CLOSE_REGIONS_BED / CLOSE_REGIONS_SOFA → section close-up of the product
     (corner / side / back etc); chosen by product kind, not by shot type alone.
*/
const DETAIL_REGIONS_FABRIC = [
  { id: "weave",   name: "splot tkaniny" },
  { id: "nap",     name: "włos / boucle / welur" },
  { id: "threads", name: "nici / faktura lnu" },
  { id: "boucle",  name: "pętle boucle" },
];
const DETAIL_REGIONS_CORNER = [
  { id: "arm_back_corner", name: "róg podłokietnik / oparcie" },
  { id: "cushion_edge",    name: "krawędź siedziska" },
  { id: "panel_seam",      name: "łączenie paneli / szew" },
  { id: "leg_attachment",  name: "mocowanie nóżki / stopa" },
];
const CLOSE_REGIONS_BED = [
  { id: "bed_headboard",   name: "wezgłowie (front)" },
  { id: "bed_side",        name: "bok łóżka (profil)" },
  { id: "bed_foot",        name: "stopa łóżka (end-on)" },
  { id: "bed_back",        name: "tył wezgłowia" },
  { id: "bed_corner_head", name: "narożnik przy wezgłowiu" },
  { id: "bed_corner_foot", name: "narożnik przy stopie" },
];
const CLOSE_REGIONS_SOFA = [
  { id: "sofa_armrest",  name: "podłokietnik" },
  { id: "sofa_backrest", name: "oparcie (góra)" },
  { id: "sofa_seat",     name: "siedzisko" },
  { id: "sofa_corner",   name: "narożnik (cała wysokość)" },
  { id: "sofa_side",     name: "bok (profil)" },
  { id: "sofa_back",     name: "tył kanapy" },
];

/* Camera height — vertical position of the camera relative to product. */
const CAMERA_HEIGHTS = [
  { id: "low",      name: "nisko (kolano)" },
  { id: "seated",   name: "siedząca (krzesło)" },
  { id: "eye",      name: "wzrok stojący" },
  { id: "standing", name: "wysoko (podest)" },
  { id: "overhead", name: "z góry (45°)" },
];

/* Camera yaw — horizontal angle around the product. */
const CAMERA_YAWS = [
  { id: "front",      name: "front" },
  { id: "34_left",    name: "3/4 z lewej" },
  { id: "34_right",   name: "3/4 z prawej" },
  { id: "side_left",  name: "bok lewy" },
  { id: "side_right", name: "bok prawy" },
  { id: "back",       name: "tył" },
];

/* Depth of field — pairs with lens to drive aperture in the prompt. */
const DEPTHS_OF_FIELD = [
  { id: "deep",          name: "głęboka — f/8" },
  { id: "standard",      name: "standard — f/4.5" },
  { id: "shallow",       name: "płytka — f/2" },
  { id: "macro_shallow", name: "makro płytka — f/2.8" },
];

/* ======================================================
   Wizard meta
   ====================================================== */
const STEPS = [
  { id: "photo",  num: "01", top: "Zdjęcie i typ",     bot: "wgraj produkt bazowy" },
  { id: "color",  num: "02", top: "Kolor",             bot: "12 presetów lub własny opis" },
  { id: "mat",    num: "03", top: "Materiał",          bot: "tkaniny rysowane wiernie" },
  { id: "size",   num: "04", top: "Konfiguracja",      bot: "liczba miejsc / rozmiar" },
  { id: "legs",   num: "05", top: "Nogi",              bot: "opcjonalne — domyślnie zachowuje" },
  { id: "env",    num: "06", top: "Otoczenie / tło",   bot: "predefiniowane lub własne" },
  { id: "scene",  num: "07", top: "Kamera i światło",  bot: "scena renderingu" },
  { id: "refs",   num: "08", top: "Referencje",        bot: "do 3 dodatkowych zdjęć" },
];

/* ======================================================
   Tiny SVG icon set (no emoji, no AI-slop SVGs)
   ====================================================== */
const Ic = {
  upload: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 4v12"/><path d="m6 10 6-6 6 6"/><path d="M4 20h16"/>
    </svg>
  ),
  sofa: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 14v-3a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v3"/>
      <path d="M3 18a2 2 0 0 1-2-2v-1a2 2 0 0 1 2-2 2 2 0 0 1 2 2v3z"/>
      <path d="M21 18a2 2 0 0 0 2-2v-1a2 2 0 0 0-2-2 2 2 0 0 0-2 2v3z"/>
      <path d="M5 14h14v4H5z"/><path d="M5 18v2"/><path d="M19 18v2"/>
    </svg>
  ),
  bed: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 16V7"/><path d="M22 16v-4a3 3 0 0 0-3-3H10v7"/>
      <path d="M2 13h20"/><path d="M2 19v-3h20v3"/>
      <circle cx="6" cy="11" r="2"/>
    </svg>
  ),
  arrowL: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>,
  arrowR: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6"/></svg>,
  caret: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>,
  sparkle: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>,
  check: <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l4 4L19 7"/></svg>,
  camera: <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7h4l2-3h6l2 3h4v12H3z"/><circle cx="12" cy="13" r="4"/></svg>,
  lens: <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>,
  bulb: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12c.7 1 1 1.7 1 3h6c0-1.3.3-2 1-3a7 7 0 0 0-4-12z"/></svg>,
  scale: <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3h7v7H3zM14 14h7v7h-7zM10 14l4 4M14 10l-4-4"/></svg>,
  copy: <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>,
};

// ─────────────────────────────────────────────────────────────────────────────
// Bed styling — controls what lies on the bed and how tidy it is.
// Only rendered when product type === "bed" (sofas don't have bedding).
// Each preset.prompt becomes a fragment of the BEDDING block sent to Gemini.
// ─────────────────────────────────────────────────────────────────────────────
const BEDDING_PRESETS = [
  { id: "none",         name: "Bez pościeli",        prop: "tylko materac, brak tekstyliów",
    prompt: "no bedding at all — the bare mattress is visible, no sheets, no duvet, no pillows" },
  { id: "linen_white",  name: "Len biały",           prop: "naturalne lniane prześcieradło + kołdra",
    prompt: "crisp white pure-linen sheets and a matching white linen duvet, gentle natural creases, soft matte texture" },
  { id: "linen_natural",name: "Len naturalny",       prop: "ciepły len ecru, surowy beż",
    prompt: "natural undyed flax linen sheets and duvet in warm ecru / oatmeal tone, visible weave, soft wrinkles" },
  { id: "linen_grey",   name: "Len szary",           prop: "stonowany len kamienno-szary",
    prompt: "stone-grey washed linen sheets and duvet, gently rumpled, slightly cool undertone" },
  { id: "linen_sage",   name: "Len szałwiowy",       prop: "len w kolorze sage / oliwka",
    prompt: "muted sage-green washed linen sheets and duvet, soft and matte" },
  { id: "cotton_white", name: "Bawełna percale",     prop: "biała bawełna percale, hotel-look",
    prompt: "smooth white percale cotton sheets and duvet, crisp and lightly pressed, hotel-look finish" },
  { id: "jersey_warm",  name: "Jersey kremowy",      prop: "miękki jersey w odcieniu kremu",
    prompt: "soft cream cotton-jersey sheets and a matching jersey duvet, cozy and relaxed drape" },
  { id: "custom",       name: "Własny opis",         prop: "wpisz swój opis pościeli",
    prompt: "" },
];

const THROW_PRESETS = [
  { id: "none",         name: "Brak",                prompt: "" },
  { id: "linen_foot",   name: "Lniana u stóp",       prompt: "a light-weight linen throw folded neatly at the foot of the bed" },
  { id: "knit_chunky",  name: "Chunky knit",         prompt: "a chunky hand-knit wool throw casually draped across the lower third of the bed" },
  { id: "wool_plaid",   name: "Wełniana krata",      prompt: "a folded wool plaid blanket placed across the foot of the bed" },
  { id: "boucle",       name: "Bouclé miękki",       prompt: "a soft cream bouclé throw lightly tossed across one corner of the bed" },
  { id: "quilt",        name: "Pikowana narzuta",    prompt: "a vintage-style quilted bedspread folded along the foot, lightly textured" },
];

const TIDY_LEVELS = [
  { id: "unmade",      name: "Rozbebrana",          prompt: "the bed is unmade — sheets pulled aside, duvet partly thrown off, a clearly slept-in look. Casual and very lived-in, but still photogenic and not chaotic" },
  { id: "lived_in",   name: "Naturalna",           prompt: "the bedding is naturally rumpled with soft organic creases and gentle wrinkles — a lived-in but pleasant look, not staged-stiff and not messy" },
  { id: "neat",        name: "Równa",               prompt: "the bedding is smoothed and tidy with only subtle natural wrinkles, the duvet centered and even, pillows neatly arranged. Calm and orderly" },
  { id: "hotel",       name: "Hotel-perfect",       prompt: "the bedding is crisp and hotel-perfect — taut sheets, perfectly squared duvet corners, pillows precisely stacked and fluffed, zero wrinkles, magazine-grade styling" },
  { id: "five_star",   name: "5★ hotel — zero zagnieceń", prompt: "the bedding is rendered to ultra-luxury five-star hotel suite standard: ABSOLUTELY zero folds, zero creases, zero wrinkles, zero rumples anywhere on the sheets, duvet, or pillowcases. Every surface is ironed glass-smooth and pulled taut to the millimeter. Duvet corners are knife-sharp 90-degree right angles, perfectly squared and aligned to the mattress edges. The duvet itself lies flat and evenly tensioned across the entire bed with no air bubbles, no puckering, and no soft sag. Pillows are flawlessly fluffed, identical in height and shape, precisely stacked or aligned with mathematical symmetry. Sheet edges are crisp and perfectly parallel. Top-tier luxury presentation, like a Mandarin Oriental or Four Seasons master suite immediately after housekeeping turn-down. ANY visible fold, wrinkle, or asymmetry is a defect that ruins the render" },
];

const DENSITY_LEVELS = [
  { id: "minimal",     name: "Minimalna",           prompt: "an extremely minimal scene — only the bed and its bedding are visible, absolutely no decorative props, no books, no trays, no plants, no extra objects in the frame" },
  { id: "balanced",    name: "Zbalansowana",        prompt: "a balanced scene with the bedding and at most one or two small tasteful styling items if requested below; otherwise the frame stays clean" },
  { id: "rich",        name: "Bogata aranżacja",    prompt: "a fully styled editorial-look scene with multiple tasteful styling items adding warmth and narrative — but never cluttered or busy" },
];

const BED_ACCENTS = [
  { id: "extra_pillows", name: "Dodatkowe poduszki",    prompt: "an extra pair of decorative pillows neatly arranged against the headboard" },
  { id: "book",          name: "Książka",               prompt: "a single hardback book resting on top of the duvet, casually placed" },
  { id: "tray",          name: "Taca śniadaniowa",      prompt: "a small wooden breakfast tray with a coffee cup placed on the bed" },
  { id: "robe",          name: "Szlafrok / koszula",    prompt: "a soft linen robe casually laid across the corner of the bed" },
  { id: "plant",         name: "Roślinka obok",         prompt: "a small potted plant visible on a nightstand or just beside the bed" },
  { id: "candle",        name: "Świeca",                prompt: "a single lit candle in a simple ceramic holder placed near the bed" },
];

window.Ic = Ic;
window.NS_DATA = { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS,
                   STEPS, ENVIRONMENTS, LENSES, TIMES_OF_DAY, SHADOWS,
                   SHOT_TYPES, DETAIL_REGIONS_FABRIC, DETAIL_REGIONS_CORNER,
                   CLOSE_REGIONS_BED, CLOSE_REGIONS_SOFA,
                   CAMERA_HEIGHTS, CAMERA_YAWS, DEPTHS_OF_FIELD,
                   BEDDING_PRESETS, THROW_PRESETS, TIDY_LEVELS, DENSITY_LEVELS, BED_ACCENTS };
