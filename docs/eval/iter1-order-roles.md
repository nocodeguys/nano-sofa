# Eval report — iter1-order-roles

model `google/gemini-3.1-flash-image` · engine openrouter · quality – · git d6f5de0 · total $0.4346

| case | refs | cam@% | uph ΔE | uph share | uph hex | width | mask | bd ΔE | framing | backdrop | cost | ms | error |
|---|---:|---:|---:|---:|---|---:|---:|---:|:-:|:-:|---:|---:|---|
| bed-catalog-hero-gemini | 8 | 4 | 5.02 | 0.36 | #857D77 | 0.78 | 0.27 | 0.62 | ✗ | ✓ | 0.0733 | 24624 |  |
| bed-catalog-close_up-gemini | 8 | 4 | 1.82 | 0.16 | #988F89 | 0.76 | 0.43 | 1.82 | ✗ | ✓ | 0.0733 | 18438 |  |
| bed-catalog-detail_fabric-gemini | 6 | 6 | 1.77 | 0.25 | #988E84 | 1.00 | 0.74 | 33.99 | ✗ | ✗ | 0.0716 | 20700 |  |
| bed-lifestyle-hero-gemini | 7 | 6 | 8.16 | 0.21 | #A89881 | 1.00 | 0.52 | – | ✗ |  | 0.0723 | 23400 |  |
| bed-lifestyle-close_up-gemini | 7 | 6 | 1.47 | 0.15 | #938B81 | 1.00 | 0.86 | – | ✓ |  | 0.0723 | 21254 |  |
| bed-lifestyle-detail_fabric-gemini | 6 | 6 | 6.49 | 0.39 | #A69D93 | 1.00 | 0.40 | – | ✗ |  | 0.0717 | 16233 |  |

Legend: uph ΔE = CIEDE2000 of the product's dominant colour cluster nearest the target hex (≤ 3 indistinguishable, ≤ 6 close, > 10 visibly off); width = product bbox / frame width (hero contract 0.78–0.84); mask = product pixels / frame (close-up ≥ 0.6, macro ≥ 0.9); bd ΔE = border colour vs expected backdrop (catalog only).

## Obserwacje (2026-10-20, faza 2b iteracja 1 vs baseline-nb2-or)

Ten sam model (`google/gemini-3.1-flash-image` przez OpenRouter), to samo
zdjęcie bazowe, te same 6 requestów, pełny zestaw referencji. Zmieniła się
tylko kolejność i brzmienie promptu, system instruction oraz to, że makro
nie dostaje planszy cykloramy ani zdjęcia „application”.

- **Kąt kamery działa.** Oba hero są w widoku 34° z lewej, tak jak prosi
  request; w baseline były frontalne. Zadziałało usunięcie sprzeczności
  (system instruction nie każe już zachować kąta z image 1) plus zdanie
  „this camera overrides the viewpoint of image 1”.
- **Hero katalogowy wszedł w kontrakt**: 0,78 szerokości kadru (było 0,89,
  kontrakt 0,78–0,84).
- **Makro tkaniny jest makrem**: maska 0,74 (było 0,31), kadr wypełnia
  tkanina, brak tła w kadrze (stąd „bd ΔE 34” — brzeg kadru to tkanina, nie
  cyklorama; dla makra to poprawny sygnał).
- **Kolor w katalogu bez zmian lub lepiej** (ΔE 1,8–5,0). W lifestyle hero
  gorzej (8,2 vs 6,8): ciepłe światło i inny kąt.
- **Tekstura**: makro katalogowe wygląda na grubszy splot niż „fine
  irregular short-pile chenille” ze specyfikacji; lifestyle hero zjechał w
  stronę pętelek bouclé. Metryki tego nie łapią — to zadanie dla sędziego
  wizyjnego (R3) albo dla porównania przy profilu „minimal”.
- **Nie zmierzono**: profil referencji „minimal” (iteracja 2) — saldo konta
  OpenRouter wyczerpane ($0,70 z $10). Domyślny profil zostaje „full”.
