# Eval report — baseline-nb2-or

model `google/gemini-3.1-flash-image` · engine openrouter · quality – · git b41c860 · total $0.4363

| case | refs | cam@% | uph ΔE | uph share | uph hex | width | mask | bd ΔE | framing | backdrop | cost | ms | error |
|---|---:|---:|---:|---:|---|---:|---:|---:|:-:|:-:|---:|---:|---|
| bed-catalog-hero-gemini | 8 | 57 | 4.77 | 0.39 | #897D74 | 0.89 | 0.34 | 0.62 | ✗ | ✓ | 0.0733 | 23176 |  |
| bed-catalog-close_up-gemini | 8 | 58 | 2.57 | 0.20 | #9B9187 | 0.69 | 0.55 | 2.52 | ✗ | ✓ | 0.0732 | 20305 |  |
| bed-catalog-detail_fabric-gemini | 8 | 77 | 3.05 | 0.47 | #8C8279 | 0.96 | 0.31 | 3.17 | ✗ | ✗ | 0.0729 | 22153 |  |
| bed-lifestyle-hero-gemini | 7 | 78 | 6.78 | 0.24 | #A59885 | 1.00 | 0.95 | – | ✗ |  | 0.0723 | 20168 |  |
| bed-lifestyle-close_up-gemini | 7 | 76 | 1.76 | 0.33 | #8F877E | 1.00 | 0.55 | – | ✗ |  | 0.0723 | 21540 |  |
| bed-lifestyle-detail_fabric-gemini | 7 | 76 | 6.19 | 0.25 | #A59D94 | 1.00 | 0.26 | – | ✗ |  | 0.0723 | 23893 |  |

Legend: uph ΔE = CIEDE2000 of the product's dominant colour cluster nearest the target hex (≤ 3 indistinguishable, ≤ 6 close, > 10 visibly off); width = product bbox / frame width (hero contract 0.78–0.84); mask = product pixels / frame (close-up ≥ 0.6, macro ≥ 0.9); bd ΔE = border colour vs expected backdrop (catalog only).

## Obserwacje (2026-10-20, kod b41c860, prompt sprzed fazy 2b)

Ten raport jest punktem odniesienia dla fazy 2b. Ten sam model
(`google/gemini-3.1-flash-image` przez OpenRouter, trasa Vertex), to samo
zdjęcie bazowe łóżka, te same 6 requestów.

- **Kąt kamery jest ignorowany.** Każdy request prosi o „front 34 left,
  35 degrees”; każdy render jest frontalny (hero katalog i lifestyle) albo
  w innym kącie niż proszono (detail). System instruction mówi „Preserve
  camera angle”, prompt mówi „34 degrees from the left” — model słucha
  system instruction. To sprzeczność w naszym własnym prompcie.
- **Makro tkaniny (`detail_fabric`) daje pełne ujęcie łóżka**, nie zbliżenie:
  maska produktu 0,31 kadru zamiast ≥ 0,90. CAMERA leży w 77% promptu, po
  ośmiu referencjach, z których plansza cykloramy i zdjęcie „application”
  pokazują całe meble.
- **Hero katalogowy jest za szeroki**: 0,89 szerokości kadru wobec
  kontraktu 0,78–0,84.
- **Kolor**: ΔE 1,8–4,8 w katalogu (dobrze), 6,2–6,8 w lifestyle (ciepłe
  światło wnętrza przesuwa taupe w stronę beżu, `#A59885` vs `#938A83`).
- **Tło katalogowe trzyma się profilu**: ΔE 0,6–3,2 vs `#F7F5F1`.
