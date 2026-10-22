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

- **Type:** Space Mono Bold for headings, Roboto Regular/Medium/Bold for everything else. Both are self-hosted through
  `@fontsource` (the CSP only allows `font-src 'self'`).
- **Logo:** the real vector paths from the guideline (page 14). The full logo is used at 200px and up (sign-in screens);
  the CF symbol is used below that (header), as the guideline requires. Colours stay within approved pairs: green on ink,
  ink on white. No gradients, shadows or transparency on the mark.
- **Motif:** the olive diagonal stripes (`.cf-stripes`) on the dark sign-in screens.
- **Accessibility:** ink on green is 15:1, ink on red 4.6:1, white on purple 6.9:1; focus rings are 3px purple.
  The guideline's "High Contrast" mode is not built yet.

Not changed on purpose: the mandatory "Featured" / "AI-generated anchor" labels and the fictional channel identity used
inside the rendered videos (backend, hard rules 1 and 2), and the startup brand-kit editor, which is the *startup's* look.
