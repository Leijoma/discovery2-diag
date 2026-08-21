# D2 Diag — UI prototype

Interactive design prototype for the Discovery 2 diagnostic tool. Phone-first,
responsive to desktop. Built on Astryx (facebook/astryx, neutral theme).

## Files

| File | What it is |
| --- | --- |
| `D2 Diag Phone.dc.html` | The whole prototype — markup + logic in one file. Open it directly in a browser, no build step. |
| `astryx-theme.css` | Astryx neutral theme tokens (light + dark pairs) adapted from facebook/astryx `packages/themes/neutral` (MIT). This is the visual contract. |
| `support.js` | Runtime that renders the component file. Prototype only — not needed in a real app. |

## Screens

- **Connect** — cable/port/baud readout, module picker (tapping a module runs the
  handshake and drops into its data), animated fast-init → session 0xA0 →
  SecurityAccess trace, error state with hints.
- **Faults** — Current / Logged groups with raw `byte.bit` references, detail
  sheet (meaning, occurrence, confidence, source, checks), write-to-file,
  clear behind a confirm dialog.
- **Inputs** — all live signals at 1 Hz with per-channel normal ranges and info
  panels; below them a 60 s trend chart with a dropdown picking up to four
  channels to plot. Chart history is session-only and is stated as such in the
  UI — CSV logging is the way to keep it.
- **Outputs** — actuator tests per module, verified vs unverified.
- **Utilities** — identifier reads, routines, raw block dump, and the file list
  where logs and reports land.

## Behaviour worth keeping in the real app

1. **First-start opt-in.** Nothing connects and nothing is shared until the user
   answers both questions (mode, data sharing). Sharing defaults to off and the
   Continue button stays disabled until it is answered explicitly.
2. **Trusted vs Experimental.** Experimental modules, output tests and routines
   are always *visible* but greyed out and locked in Trusted mode, with a line
   saying what unlocks them. Preferences persist in `localStorage` under
   `d2diag.prefs`.
3. **One session at a time.** The K-line is shared; connecting to a module ends
   any other session. The UI never implies parallel module access.
4. **Nothing disappears silently.** Unmapped fault bits are reported by
   `byteN.bitM` rather than dropped, and suspect decodes (e.g. injector 6 on a
   5-cylinder engine) are labelled as suspect instead of hidden.
5. **Destructive writes confirm.** Clearing fault memory shows the entry count,
   the target ECU, the actual command, and that it cannot be undone.

## Themes

`data-theme="dark"` (default) or `"light"` on `<html>`. Two themes only.

For production, install the real Astryx packages rather than this token file:
https://astryx.atmeta.com/docs/getting-started

## Substitutions and gaps

- Live values are synthetic (sine drift within each signal's range) so the UI can
  be demonstrated without a car attached.
- Faults, signal scaling and command bytes come from the repo's references and
  signal store. **Outputs and Utilities entries are placeholders** — they were
  written to shape the UI, not from validated source. Replace them from the real
  routine definitions.
