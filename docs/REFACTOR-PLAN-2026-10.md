# Refactor: przewidywalność generowania — plan (2026-10-20)

Branch: `refactor/generation-predictability`. Punkt wyjścia: `98b8495` (main).
Research wejściowy: `docs/research/nano-banana-state.md` (sekcja „2026-10-20
refresh”), `docs/research/gpt-image-state.md` (nowy).

Cel: ta sama konfiguracja w UI ma dawać ten sam prompt, ten sam zestaw
referencji i mierzalnie ten sam efekt — na każdym silniku. Jakość materiałów i
kadrów ma być sprawdzalna liczbą, nie wrażeniem.

---

## 1. Diagnoza (co faktycznie się zepsuło)

Pięć niezależnych przeglądów kodu i historii. Skrót:

### 1.1 Tło — 15 wejść, jeden przełącznik decyduje

- O tle decyduje wyłącznie przełącznik **Katalog / Lifestyle**
  (`request_builder.py:170-190`). W trybie katalogowym profil (ivory /
  atelier / softblush) nadpisuje `env`, kasuje upload sceny, moodboardy,
  notatkę i tryb, a `normalize.py` na końcu **przemalowuje piksele tła** wg
  osobnej tabeli. W trybie lifestyle jest łańcuch pierwszeństwa:
  refs-lock > „zablokuj tło” > upload > kafel `env`.
- **Martwe kontrolki**: select „tryb” (referencja / dosłowne tło / światło)
  trafia tylko do `ADDITIONAL NOTES` jako tekst, generator go nie czyta.
  Tweaks panel „scena” nie jest wysyłany. `anchor_ref` ukryty pod
  `{false && …}`. Checkbox `alpha` nie wysyłany.
- **Przecieki**: wgrane tło i notatka lecą do każdego env lifestyle, nie tylko
  „custom” (`app-v2.jsx:735, 705`). „Zablokuj tło” wysyła poprzedni render z
  produktem, a prompt opisuje go jako „EMPTY studio plate”.
- **Rozjazdy danych**: hex ivory `#F7F3EA` (data.jsx) vs `#F7F5F1`
  (mappings.py) vs `(247,245,241)` (normalize.py). Profile katalogowe
  wypisane w 3 miejscach. README scene-references opisuje pliki, które nie
  istnieją.
- Podgląd „stage” i eksport JSON w trybie katalogowym pokazują **inne tło niż
  to, które idzie do modelu**.

### 1.2 Kadry — tekst kamery się nie zmienił, zmieniło się wszystko wokół

Sekcja CAMERA i tabele mapowań są bajt w bajt takie jak w `fef487c` (maj).
Regresja bierze się z trzech rzeczy:

1. **Katalog domyślnie włączony** (`c74a20a`). W tym trybie UI wysyła tylko
   `yaw`; serwer wymusza hero, 85 mm, f/8 i „CATALOG FRAMING CONTRACT … do
   not zoom in tighter”. Chipy shot-type / close-up / macro są ukryte.
   Stare presety nie mają klucza `catalog`, więc po wczytaniu nadal jest hero.
   W 25 zapisanych trace'ach nie ma ani jednego close-up.
2. **Referencje: 1 → 4–8 na render** (`5b223db`, `6128a20`, `5606fb5`).
   Domyślnie: baza + plansza cykloramy + `boucle.png` + plamka koloru.
   Cremona: 8. Repo samo udokumentowało w `b59b49b`, że obraz referencyjny
   wygrywa z tekstem kadru.
3. **CAMERA zakopana**: zaczyna się w ~56% promptu (znak ~8.5k z 15k), po
   niej ~6.5k znaków sceny. Przed nią bloki materiałowe, które kotwiczą
   „normal product-photography distance” i „at hero distance”.
   Usunięto też zdanie ochronne „tight macro detail crop wins”.

Mniejsze: `close_up` nie jest traktowany jako detail (dostaje pełną
cykloramę i SOURCE BACKGROUND DISCARD); GPT Image nie dostaje system
instruction i jedzie na `/edits` z 16 refami.

### 1.3 Kod — dwa kompilatory promptu, modele w ośmiu plikach

- **Dwa buildery** opisują te same zasady innymi słowami: produktowy
  (`generator._build_prompt_text`, ~540 linii) i freeform
  (`mappings._build_freeform_prompt`). Kolor, makro, kąty, zachowanie,
  aplikacja, moodboardy, negatywy — każde po dwa razy, inaczej. Deep-shade
  tylko w produktowym. Negatywy z 4 źródeł; `negative.default` ze schematu
  nigdzie nie używany.
- **Model id w ~8 plikach** (sofa.json, cost_tracker, routes_pages,
  routes_generate, request_builder, app-v2.jsx, editorial.jsx). Tier zgadywany
  po substringu „pro” w 10 miejscach. Koszt w UI z trzech różnych stałych.
- **Noga nigdy nie jest załączana**: `leg_reference_image` nie ma żadnego
  writera, a prompt mówi „legs shown in the reference image”.
- **Freeform numeruje sloty przed wczytaniem obrazów** — jak jeden nie
  wczyta się, prompt opisuje slot, którego nie ma.
- **Testy**: tylko substringi; brak golden-promptu per silnik/tryb, brak
  testu ścieżki lifestyle, legs, negatywów, system instruction, żadnego testu
  route'ów renderujących, zero testów frontu.
- Martwe: `leg_browser`, pół `schema_loader`, `validate_request`,
  `openrouter._legacy_references`, `BEDDING_PRESETS[].prompt` w data.jsx
  (rozjechane z mappings), worktree `.claude/worktrees/webgl-3d-preview`
  z kopią starego monolitu (indeksowany przez grep/IDE).

### 1.4 Modele — schemat poleca deprecated

- Google (oficjalnie, 2026-10-06): **`gemini-nano-banana-2.1`** stabilny,
  $0.034 / $0.050 / $0.113 za 1K/2K/4K, 14 refów. `gemini-3.1-flash-image`
  (nasz „recommended”) **deprecated**. `gemini-2.5-flash-image` deprecated.
  Brak seeda, thinking zawsze włączone (`thinking_level` minimal/medium/high).
- OpenAI: pinować snapshot `gpt-image-2.5-flare-2026-09-08`;
  `input_fidelity` **nie istnieje** dla 2/2.5 (400) — kod i ARCHITECTURE
  mówią inaczej; `quality: high` na 2.5 to dawne medium, roboczy default
  powinien być `xhigh`; 2K dla 3:4, 4:3, 21:9 w strefie „experimental”.
  `gpt-image-1` ginie 2026-10-23, w OpenRouter nadal na liście.

### 1.5 Dobre praktyki, które łamiemy (oficjalne, obie firmy)

- **Jedna rola na referencję + „take nothing else from it”** — u nas
  moodboardy bez locka są załączane i nieopisane, plansza cykloramy i zdjęcie
  „application” pokazują cały produkt w hero-dystansie.
- **Mniej referencji** — oba vendory i praktycy: każdy zbędny obraz to
  konkurencyjna instrukcja.
- **Opisuj pozytywnie, nie negatywnie** (Google) — mamy 4 bloki NEGATIVE.
- **Lista „keep exactly” powtarzana w każdym edycie** (OpenAI) — mamy
  PRESERVE na samym końcu, po 13k znaków.
- **Narracja zamiast etykiet** (Google) — mamy `TASK:` `LIGHT:` `CAMERA:`.
  Umiarkowane odstępstwo, nie udowodniony defekt.
- **Kolor: mierzyć, nie ufać** — brak oficjalnego wsparcia dla hex ani
  plamki koloru u żadnego vendora; jedyny test (NB2.1) dał ciemniejszy i
  żółtszy wynik niż hex. Nikt poza nami nie opisuje plamki koloru ani
  „framing collapse” od swatcha — to nasze wewnętrzne ustalenia, do
  zweryfikowania pomiarem.

---

## 2. Zasady refactoru

1. **Najpierw miara, potem zmiana.** Żadna zmiana promptu bez golden-testu
   i bez przebiegu macierzy ewaluacyjnej przed/po.
2. **Jedno źródło prawdy na pojęcie**: modele, tło, kamera, materiał — każde
   w jednym pliku, konsumowane przez serwer, front i testy.
3. **Jeden kompilator promptu** dla wszystkich silników i trybów. Silnik
   dostaje gotowy `PromptSpec`, nie buduje własnego tekstu.
4. **Podgląd = prawda.** To, co UI pokazuje (JSON, stage, chipy), jest
   generowane z tej samej funkcji, która buduje request.
5. **Mało referencji domyślnie, więcej na życzenie.** Budżet referencji
   jest jawny i widoczny w UI.
6. Każda faza = osobny PR na ten branch, zielone CI (pytest + golden), raport
   z macierzy ewaluacyjnej w opisie PR.

---

## 3. Docelowy kształt (wysokopoziomowo)

```
app-v2/
  models.json            ← jedyny rejestr modeli: id, silnik, caps, rozdzielczości,
                           ceny, deprecation, default quality/thinking
  catalog.json           ← materiały, kolory, kolekcje + NOWE: backdrops
                           (id, hex, tekst promptu, tony normalize, plansza)
  studio/
    prompt/
      spec.py            ← PromptSpec: subject, preserve[], camera, backdrop|scene,
                           material, colour, references[{role, scope, path}],
                           output; jedna dataclass dla product i freeform
      compile.py         ← PromptSpec → tekst; stała kolejność akapitów;
                           referencje numerowane PO wczytaniu; jedna lista
                           preserve; pozytywne sformułowania zamiast NEGATIVE
      references.py      ← plan_references(spec, engine_caps) — jedna funkcja,
                           budżet jawny, rola+scope dla każdego obrazu
    engines/
      gemini.py          ← tylko transport + system instruction + thinking
      openai.py          ← tylko transport (/edits, size, quality)
      openrouter.py      ← tylko transport
    request_builder.py   ← UI ids → PromptSpec (cienki)
    routes_*.py          ← bez logiki promptu
  frontend/src/
    request.js           ← buildRequest(state) → FormData + JSON preview
                           (ta sama funkcja)
    sections/*.jsx       ← wizard rozbity na sekcje
tests/
  golden/<engine>/<mode>/*.txt   ← pełne prompty, porównywane 1:1
  test_prompt_compile.py
  test_references_plan.py
scripts/
  eval_matrix.py         ← stała macierz generacji + metryki
  eval_report.py         ← ΔE koloru, udział produktu w kadrze, porównanie runów
```

Kolejność akapitów w skompilowanym prompcie (jedna dla wszystkich):

1. Zadanie + co jest w obrazie 1
2. **KEEP EXACTLY** (lista preserve, w tym kąt kamery i kadr)
3. **CAMERA / FRAMING** (shot type, kąt, obiektyw, co ma być w kadrze)
4. Tło albo scena (jeden akapit, jedno źródło)
5. Materiał (noun + spec) i kolor (hex + plamka, jeśli załączona)
6. Role referencji: „Image N is X; take only Y from it, nothing else”
7. Output (styl, format)

---

## 4. Fazy i agenci

Każda faza ma właściciela-agenta, wejście, wyjście i bramkę. Agenci
„research” są doradczy: aktualizują notatki, nie dotykają kodu.

| # | Faza | Agent | Zależy od | Równolegle z |
|---|------|-------|-----------|--------------|
| 0 | Baseline i harness ewaluacyjny | **eval-harness** | — | 1, R1, R2 |
| 1 | Rejestr modeli | **model-registry** | — | 0 |
| 2 | Jeden kompilator promptu + plan referencji | **prompt-compiler** | 0, 1, R1, R2 | — |
| 3 | Tło: jedno pojęcie `backdrop` | **backdrop** | 2 | 4 |
| 4 | Kadry: kamera działa w każdym trybie | **framing** | 2 | 3 |
| 5 | Front: `buildRequest` + podział wizarda | **frontend** | 3, 4 | 6 |
| 6 | Sprzątanie i dokumentacja | **cleanup** | 2 | 5 |
| R1 | Research Nano Banana (cykliczny) | **nano-banana-researcher** (istnieje) | — | wszystko |
| R2 | Research GPT Image (cykliczny) | **gpt-image-researcher** (nowy, `.claude/agents/`) | — | wszystko |
| R3 | Sędzia jakości | **eval-judge** (opcjonalnie, model wizyjny) | 0 | 2–4 |

### Faza 0 — Baseline i harness (eval-harness)

Bez tego reszta jest zgadywaniem.

- Golden-prompty: zrzut **pełnego** tekstu promptu i listy referencji
  (rola, ścieżka, kolejność) dla stałego zestawu requestów: produkt × {katalog,
  lifestyle} × {hero, close_up, macro} × {bouclé, cremona} × {Gemini, OpenAI},
  plus editorial. Zapisane z **obecnego** kodu jako punkt odniesienia.
  Test porównuje 1:1; zmiana promptu = świadoma aktualizacja goldena.
- Macierz ewaluacyjna (`scripts/eval_matrix.py`): ~12 generacji, stałe
  wejścia (jedno zdjęcie bazowe łóżka, jedno sofy), zapis do
  `outputs/eval/<run-id>/` z trace'em.
- Metryki (`scripts/eval_report.py`): ΔE2000 median koloru tapicerki vs hex
  (maska z segmentacji lub prosty próg na bazie), udział bbox produktu w
  kadrze (test „do not zoom in tighter” i „macro wypełnia kadr”), odchylenie
  tła od zadanego hex. Raport markdown porównujący dwa runy.
- Bramka: `pytest` zielone, jeden pełny run macierzy zapisany jako
  `outputs/eval/baseline-2026-10`.

### Faza 1 — Rejestr modeli (model-registry)

- `app-v2/models.json`: id, label, silnik, `max_refs`, rozdzielczości,
  aspekty, ceny per tier, deprecation, domyślne `quality` / `thinking_level`,
  flaga `input_fidelity`. Jedna funkcja `models.get(id)`.
- Aktualizacja line-upu wg researchu: default **`gemini-nano-banana-2.1`**,
  `gemini-3-pro-image` jako precision; NB2 i 2.5 Flash oznaczone deprecated i
  ukryte; OpenAI: pin `gpt-image-2.5-flare-2026-09-08` i `sunburst`, default
  `quality: xhigh`, bez `input_fidelity`, 2K tylko w dozwolonych rozmiarach;
  usunąć `gpt-image-1` z OpenRouter.
- Usunąć wszystkie zduplikowane id i stałe kosztowe (cost_tracker,
  routes_pages, app-v2.jsx, editorial.jsx, `_ETA_SEED`); `/api/config` serwuje
  rejestr; front nie ma fallbacków z id.
- Test: żaden plik poza `models.json` nie zawiera literału id modelu
  (grep w teście).

### Faza 2 — Kompilator promptu (prompt-compiler)

Serce refactoru. Wejście: oba researche, obecne buildery, goldeny z fazy 0.

- `PromptSpec` + `compile()` + `plan_references()` jak w sekcji 3.
  Produkt i freeform to dwa sposoby **wypełnienia** spec, nie dwa kompilatory.
- Kolejność akapitów z sekcji 3; KEEP EXACTLY i CAMERA w pierwszych ~800
  znakach.
- Każda referencja ma rolę i scope w tekście. Bez referencji nieopisanych.
  Numeracja zawsze po wczytaniu obrazów (naprawa freeform).
- Budżet referencji: profil **minimal** (baza + plamka koloru + makro) jako
  default; **full** (kąty, zachowanie, aplikacja, plansza) jako opt-in w UI.
  Zdjęcie „application” i plansza cykloramy nigdy przy shot ≠ hero.
- Negatywy → pozytywne sformułowania; jedna lista `avoid` z katalogu, bez
  czterech źródeł. „seed hint” usunięty z tekstu (żaden silnik nie ma seeda).
- System instruction (kontrakt preserve) wysyłana do Gemini jako system,
  do OpenAI i OpenRouter jako pierwszy akapit — ten sam tekst.
- Noga: albo załączamy referencję z `legs/manifest.json`, albo prompt
  przestaje udawać, że ją ma.
- Bramka: nowe goldeny per silnik/tryb; test „Gemini i OpenAI dostają
  identyczny tekst dla tego samego spec”; macierz ewaluacyjna vs baseline —
  ΔE nie gorsze, udział produktu w kadrze zgodny z shot type.

### Faza 3 — Tło (backdrop)

- Jedno pojęcie `backdrop` w `catalog.json`: id, hex, tekst promptu, tony
  normalize, opcjonalna plansza. Katalogowe profile i lifestyle-cykloramy
  to ten sam typ; sceny wnętrzowe to osobny typ `scene`. Picker w UI:
  **albo backdrop, albo scena, albo własne zdjęcie** — jedna sekcja.
- Usunąć: select „tryb” (env_mode), `envNote` jako osobne pole (zostaje w
  jednej notatce ogólnej), tweaks „scena”, `anchorRef`, checkbox `alpha`.
- „Zablokuj tło”: wysyłać z flagą `scene_contains_product`, działać tak samo
  dla Generuj i Warianty, albo usunąć na rzecz „użyj poprzedniego renderu
  jako sceny” z jawnym opisem.
- Upload i notatka wysyłane tylko przy `custom`.
- Hex spójny: jedna wartość w katalogu, normalize czyta z niej.
- Bramka: tabela 15 wejść z raportu diagnostycznego zredukowana do 3
  (backdrop | scene | upload) + lock; test, że każde z nich dociera do
  promptu i że żadne inne pole nie zmienia tła.

### Faza 4 — Kadry (framing)

- Shot type, obiektyw, DOF, region detalu dostępne **także w trybie
  katalogowym**; katalog blokuje tylko tło i światło, nie kadr.
  „CATALOG FRAMING CONTRACT” tylko dla `hero`.
- `close_up` traktowany jak detail (bez pełnej cykloramy, bez SOURCE
  BACKGROUND DISCARD). Przywrócić ochronę „detail crop wins over reference
  distance”.
- Migracja presetów: brak klucza `catalog` → wnioskować z `shot`.
- Bramka: macierz hero / close_up / macro w obu trybach — udział produktu
  w kadrze w zadanych widełkach; goldeny.

### Faza 5 — Front (frontend)

- `request.js: buildRequest(state)` zwraca FormData **i** obiekt podglądu;
  JSON tab, chipy i stage korzystają z tego samego obiektu.
- `app-v2.jsx` (3029 linii) → sekcje: produkt, materiał+kolor, kadr,
  tło/scena, referencje, output, akcje; stan w jednym reducerze.
- Budżet referencji widoczny: „wyślemy N obrazów: …”.
- Bramka: smoke przez Vite build + test route'ów renderujących na mocku
  silnika z realnym FormData.

### Faza 6 — Sprzątanie i dokumentacja (cleanup)

- Usunąć martwy kod z sekcji 1.3; wykasować worktree
  `.claude/worktrees/webgl-3d-preview` (po decyzji o branchu
  `worktree-webgl-3d-preview`, 40 commitów za HEAD).
- `prompts/schemas/sofa.json`: zostaje jako kontrakt pól, model-constraints
  i reference_slots przeniesione do rejestru / usunięte.
- ARCHITECTURE.md: nowy flow, nowe invarianty (budżet referencji, kolejność
  akapitów, backdrop jako jedno pojęcie); scene-references README
  poprawiony; `docs/research/*` linkowane.
- Dodać sekcję „jak zmienić prompt”: zmień spec → uruchom goldeny →
  uruchom macierz → porównaj raport → zaktualizuj goldeny w tym samym PR.

### Agenci researchowi (R1, R2, R3)

- **nano-banana-researcher** (istnieje): już odświeżył notatkę. Harmonogram:
  przed fazą 2 i przy każdej zmianie line-upu. Dodatkowo zlecić mu jedno
  konkretne pytanie: wpływ `thinking_level` na wierność tekstury.
- **gpt-image-researcher** (nowy, definicja w `.claude/agents/`):
  utrzymuje `docs/research/gpt-image-state.md`. Pierwsze zadanie otwarte:
  maski / lokalne kompozytowanie jako sposób na drift przy zmianie tkaniny.
- **eval-judge** (opcjonalnie): model wizyjny oceniający pary obrazów po
  rubryce (tekstura, kolor, kadr, tło) — uzupełnienie metryk liczbowych
  z fazy 0, nie ich zamiennik.

---

## 5. Co dostajemy po każdej fazie

| Po fazie | Widoczny efekt |
|---|---|
| 0 | Liczby: ΔE koloru i udział w kadrze dla dzisiejszego stanu. Pierwszy raz wiadomo, co znaczy „gorzej”. |
| 1 | Aktualne modele, jeden cennik, brak deprecated w UI. |
| 2 | Ten sam prompt na Gemini i GPT; 3 referencje zamiast 8; kadr w pierwszych 800 znakach. Tu spodziewamy się największej poprawy kadrów. |
| 3 | Jeden picker tła. Podgląd pokazuje to, co idzie do modelu. |
| 4 | Close-up i macro działają w katalogu. |
| 5 | Wizard do utrzymania; JSON = prawda. |
| 6 | Repo bez kopii i martwego kodu; dokumentacja zgodna z kodem. |

## 6. Ryzyka

- Faza 2 zmienia brzmienie promptu — invarianty z ARCHITECTURE (noun ≥ spec,
  brak swatcha w fotosesji) muszą przejść jako testy, nie jako pamięć.
- Metryka ΔE wymaga maski tapicerki; na start prosty próg wokół bazy, potem
  segmentacja. Nie blokować fazy 0 na idealnej masce.
- `gemini-nano-banana-2.1` jest nowy (stabilny od 2026-10-06); macierz z
  fazy 0 trzeba przebiec na nim **i** na obecnym defaulcie, żeby oddzielić
  efekt modelu od efektu refactoru.
