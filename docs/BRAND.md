# Brand Guide

Argus's README identity is a member of the shared **freed-dev-llc** visual family — a
denim‑blue + warm‑accent system on a dark ink panel, with an SVG horizontal logo and a
matching square icon. The **system** bits (palette, panel, typography, layout) are held
constant across every repo so they read as one family; only the **project‑specific** bits
change — here, the wordmark (`ARGUS NET`) and the bespoke glyph (an **all‑seeing eye**).

The anchor color is **PANTONE 17‑4139 TCX "Niagara"** (a denim/teal blue, ≈ `#5B89A6`).
The system deliberately avoids the teal‑green / purple‑gradient "AI" look — the warmth
comes from an earthy complementary accent, not a neon. Argus uses the **amber/brass**
accent variant.

> **Reference implementation / canonical guide:** the `turing-ansible-cluster` repo
> (`docs/BRAND.md` + `docs/assets/turing-cluster/`). Keep the two in sync if the shared
> system changes.

---

## 1. Color palette

| Role | Token | Hex | Notes |
|------|-------|-----|-------|
| **Primary — Niagara** | `niagara` | `#5B89A6` | Brand anchor (PANTONE 17‑4139 TCX). Base of the node/primary gradient. |
| Primary gradient (top→bottom) | `node` | `#6E9DBA → #4E7C97` | Eye outline, iris ring, node‑mesh feeders. |
| Primary line / mesh | `primary-line` | `#4E7C97` | Connectors, hairlines, iris ring. |
| Subtitle / mid blue | `mid` | `#7FA6BC` | Letter‑spaced subtitle, secondary text. |
| **Accent — Amber/brass** | `accent` | `#C5953F` | The one warm pop. Accent wordmark token (`NET`) + rule + the eye's pupil + the category label. |
| Accent gradient (top→bottom) | `cp` | `#CDA052 → #9C6F2E` | The pupil. |
| Ink panel (top→bottom) | `bg` | `#1A2C39 → #0F1C25` | The banner background; theme‑independent surface. |
| Panel border | `border` | `#2C4C61` | 1.5–2px stroke that defines the panel edge. |
| Text — off‑white | `text` | `#EAF2F7` | Wordmark, light shapes, canthus node dots. |
| Warm white | `warm-white` | `#FBEEE3` | The catchlight on the pupil — a subtle warmth tie‑in. |

**Accent variations.** Argus ships the **amber/brass** variant. Niagara + the dark ink stay
constant across the family; only the warm accent varies between repos (all are warm
complements of Niagara, so they harmonize): Terracotta `#C4683F → #974124`, Copper
`#DB9560 → #BE6C3A`, Amber/brass `#CDA052 → #9C6F2E`. Keep any accent a **warm hue
(≈ 20–45°)** — avoid greens and violets, where the "AI" cliché lives.

---

## 2. The panel

Every banner/icon sits on a self‑contained dark panel so it renders identically in GitHub
light **and** dark mode (no `prefers-color-scheme` gymnastics):

- Background: vertical linear gradient `bg` (`#1A2C39 → #0F1C25`).
- Border: `border` (`#2C4C61`), `stroke-width` 1.5 (banner) / 2 (icon).
- Corner radius: `28` on the banner panel, `48` on the square icon.

---

## 3. Typography

The wordmark is a **bold, uppercase** sans with one accent token:

- Font stack: `'Segoe UI','SF Pro Display',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif`
- Wordmark: `font-size` ~62, `font-weight` 800, `letter-spacing` 0.5, fill `text`. The **last
  token** (`NET`) is filled with `accent`.
- Accent rule: a thin (`height` 3, `rx` 1.5) `accent` rectangle under the wordmark at ~0.8
  opacity. Match its width to the wordmark.
- Subtitle: `font-size` ~14.5, `font-weight` 600, `letter-spacing` ~2.2, fill `mid` —
  Argus uses `DISCOVER · DIFF · RECONCILE` (its actual loop).
- Category label: `font-size` ~21, `font-weight` 800, wide `letter-spacing` ~7, fill
  `accent` — Argus uses `SOURCE OF TRUTH`.

> SVG `<text>` collapses leading whitespace, so put a gap **before** the accent tspan with
> `dx="20"`, not a literal space.

---

## 4. Logo lockup & README layout

```markdown
# Argus

![Argus Net](docs/assets/argus/logos/argus_logo_horizontal.svg)

[![CI](...)](...) [![…](...)](...)

One‑line description of the project.
```

**Asset paths / naming** (keep this convention across repos):

```
docs/assets/argus/
├── logos/argus_logo_horizontal.svg   # banner used in the README
└── icons/argus_icon.svg              # square mark (favicon/social)
docs/assets/buttons/                  # sibling cross-link buttons (btn_<repo>.svg)
```

Lockup geometry: **icon on the left, wordmark + subtitle to its right**, both vertically
centered on the panel. Balance the side margins (~64–85px each).

---

## 5. Iconography

The **glyph is bespoke per project** — it should say something about what the project *is*.
Argus is the **all‑seeing** keeper of your network's truth (Argus Panoptes), so the mark is
an **eye**: an almond outline in Niagara, a faint iris ring, an **amber pupil** with a
`warm-white` catchlight, two `text` "canthus" node dots at the eye corners, and a faint
`primary-line` mesh feeding the iris (the network angle). Keep it geometric and legible at
32px; one accent element only (the pupil).

---

## 6. Family

All repos share the system above; each gets its own glyph + warm accent. Cross‑link buttons
(`docs/assets/buttons/btn_<repo>.svg`, 372×72) embed each repo's glyph + a mono slug.

| Repo | Role | Glyph | Accent |
|------|------|-------|--------|
| [Aria](https://github.com/freed-dev-llc/aria) | Voice assistant | voice waveform | Terracotta `#C4683F` |
| [Argus](https://github.com/freed-dev-llc/argus) | Network source‑of‑truth tooling | all‑seeing eye | Amber `#C5953F` |
| [Leeloo](https://github.com/freed-dev-llc/leeloo) | Kimi‑powered agent | fifth‑element spark | Copper `#D2814E` |
| [Elara](https://github.com/freed-dev-llc/elara) | Hosted Hermes messenger (Telegram) | paper‑plane | Rose‑clay `#CC7A5C` |

Argus is the shared tooling the agents run on; the agents cross‑link to each other and to
Argus.

---

## 7. Tooling & checks

- **Preview before commit.** `rsvg-convert -z 2 -b '#ffffff' logo.svg -o /tmp/logo.png`
  (also try `-b '#0d1117'` for GitHub dark). `inkscape`, `resvg`, `cairosvg` work too.
- **Validate** well‑formedness: `python3 -c "import xml.dom.minidom as m; m.parse('logo.svg')"`.
- Keep text as `<text>` (not paths) so wordmarks stay editable.

---

*Palette anchored on PANTONE 17‑4139 TCX (Niagara). Shared family reference:
`turing-ansible-cluster/docs/BRAND.md`.*
