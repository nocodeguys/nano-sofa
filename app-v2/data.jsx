/* global React */
const { useState, useMemo, useEffect, useCallback } = React;

/* ======================================================
   Data — colors, materials, sizes, cameras, legs
   ====================================================== */
const COLORS = [
  { id: "saliw",   name: "szałwiowy",     hex: "#6F8C68", fabric: true },
  { id: "ecru",    name: "ecru",          hex: "#E4DBC6", fabric: true },
  { id: "carmel",  name: "karmelowy",     hex: "#9B7048", fabric: true },
  { id: "graphi",  name: "grafitowy",     hex: "#3B3D3F", fabric: true },
  { id: "rust",    name: "rdzawy",        hex: "#A85B36", fabric: true },
  { id: "cream",   name: "kremowy",       hex: "#F2E8D2", fabric: true },
  { id: "navy",    name: "granatowy",     hex: "#2A3A52", fabric: true },
  { id: "moos",    name: "mech",          hex: "#4F6440", fabric: true },
  { id: "rose",    name: "pudrowy róż",   hex: "#D6B4A8", fabric: true },
  { id: "stone",   name: "kamień",        hex: "#8E8773", fabric: true },
  { id: "choc",    name: "czekolada",     hex: "#4D352A", fabric: true },
  { id: "blush",   name: "morela",        hex: "#D69874", fabric: true },
];

const MATERIALS = [
  { id: "boucle",   name: "bouclé",   prop: "miękki, pętelkowy", tex: "boucle" },
  { id: "velvet",   name: "aksamit",  prop: "kierunkowy włos",   tex: "velvet" },
  { id: "linen",    name: "len",      prop: "matowy splot",      tex: "linen" },
  { id: "weave",    name: "tkanina płaska", prop: "neutralny mebel", tex: "weave" },
  { id: "chenille", name: "szenila",  prop: "mięsisty, ciepły",  tex: "chenille" },
  { id: "leather",  name: "skóra",    prop: "gładka, połysk",    tex: "leather" },
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
  { id: "studio_white",  name: "Białe studio",        prop: "katalog, e-commerce",    grad: "linear-gradient(180deg,#F4F0E5,#DCD3BD)",      acc: "#E8DEC9" },
  { id: "studio_grey",   name: "Studio cykloramy",    prop: "neutralny, packshot",    grad: "linear-gradient(180deg,#DEDED9,#9C9D97)",      acc: "#C2C3BD" },
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

window.Ic = Ic;
window.NS_DATA = { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS,
                   STEPS, ENVIRONMENTS, LENSES, TIMES_OF_DAY, SHADOWS };
