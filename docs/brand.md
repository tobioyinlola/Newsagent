# Cover Founder brand in the web app

Source: the Cover Founder brand guideline PDF (v1.0, 2026). Implemented in `frontend/src/index.css` (tokens),
`frontend/src/components/Logo.tsx` and `ui.tsx`.

| Token | Value | Use |
| --- | --- | --- |
| `ink` | `#222222` | headers, headlines, borders, dark grounds |
| `navy` | `#191A30` | paragraph text (body) |
| `brand-green` (Pastel Green) | `#C0FE73` | primary buttons, active nav, logo on dark |
| `brand-red` (Vivid Red) | `#EB464B` | destructive buttons, error borders |
| `brand-purple` (Gray Purple) | `#634EA0` | focus rings, info notices, "current step" |
| `brand-aqua` / `brand-peach` | `#0CC0DF` / `#FFBD59` | secondary; peach marks the "Featured" disclosure and warnings |
| tints | `lime-tint`, `lilac`, `peach-tint`, `red-tint` | quiet notice backgrounds only |

- **Type:** Inter everywhere (headings Bold/ExtraBold, body Regular/Medium), on the site, in the back office, in emails
  (with a Helvetica/Arial fallback) and in the video graphics. Self-hosted through `@fontsource/inter`; no third-party font CDN.
- **Logo:** the real vector paths from the guideline (page 14). The full logo is used at 200px and up (sign-in screens);
  the CF symbol is used below that (header), as the guideline requires. Colours stay within approved pairs: green on ink,
  ink on white. No gradients, shadows or transparency on the mark.
- **Motif:** the olive diagonal stripes (`.cf-stripes`) on the dark sign-in screens.
- **Accessibility:** ink on green is 15:1, ink on red 4.6:1, white on purple 6.9:1; focus rings are 3px purple.
  The guideline's "High Contrast" mode is not built yet.

The channel name in rendered videos and on the founder page is **Cover Founder** (`CHANNEL_IDENTITY` in
`backend/app/pipeline/steps.py`, defaults in `backend/renderer/src/compositions`). It is locked: no field edits it.
Not changed on purpose: the mandatory "Featured" / "AI-generated anchor" labels (hard rule 2), and the startup
brand-kit editor, which is the *startup's* look. 

## Video graphics (`backend/renderer/src/compositions`)
- `theme.tsx` holds the palette, the CF symbol and the striped ground; `Chrome.tsx` is the channel bug, the mandatory
  disclosures and the ticker, shared by every composition so none can drop a disclosure.
- Ground: ink `#222` with olive stripes. Channel bug: CF symbol in green + "COVER FOUNDER" in Inter Bold. "Featured"
  tag: Peach with ink text. Ticker: ink with a green rule, Inter. "Featured startup" banner: Pastel Green, Inter Bold.
- Lower thirds: ink panel, white Inter Bold title, green Inter subtitle. The **startup's own accent colour** is only the
  marker bar beside the lower third (and not the ground), so every video reads as a Cover Founder video.
- Fonts (Inter Regular/Bold) are bundled in `backend/renderer/public/fonts` and loaded before any frame is
  captured, so a render never falls back to another font and needs no network.

## Answers column and back office (added)
Live-interview answers use the `column` layout: the founder's video on the left, a dark panel on the right with the question
label in Pastel Green, the question, the founder's name and title, then their words revealed line by line in sync. The back
office (`frontend/src/admin/`) uses the same tokens in a denser, operator-oriented layout.

## Presenter footage (added)
Presenter clips play full frame under the same channel bug, "Featured" tag, "AI-generated anchor" label and ticker as every other scene.
