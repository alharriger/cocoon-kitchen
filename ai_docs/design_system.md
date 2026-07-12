# Design System

Source of truth for UI and voice. Small on purpose in v0 (Streamlit constrains most visuals); it grows only when the UI does.

## Voice & tone (applies to UI copy AND model output)
- **Awareness, not judgment.** We describe ingredient processing; we never shame a cook, a culture, or a craving. Banned vibes: "guilt," "cheat," "bad food," "clean vs dirty people."
- **Not medical advice.** No health claims, no "this will lower your cholesterol." A visible one-line disclaimer on the card.
- **Chef-warm, doctor-precise.** Swaps read like a friend in your kitchen: "swap the vegetable oil for extra-virgin olive oil — same sauté, better fat."

## The Verdict card (v0 layout)
1. **Score + band** — big number, band as a colored pill.
2. **Sub-score bars** — six rows, weight-ordered.
3. **Flagged ingredients** — chips/list.
4. **Three swaps** — from → to, one-line reason each.
5. Disclaimer footer.

## Color: band palette (v0)
- Clean — green; Mostly Clean — yellow-green; Processed — amber; Ultra-processed — deep orange/red.
- Never use red/green as the *only* signal — band name is always written out (accessibility).
- **Concrete hex values (decided 2026-07-11, Phase 3 `app.py` band pill):** Clean `#2e7d32`, Mostly Clean `#9e9d24`, Processed `#ef6c00`, Ultra-processed `#c62828`. Code-owned map `BAND_COLORS` in `app.py`; the band name always renders inside the pill next to the color.

## Deferred until the UI grows
Typography, spacing scale, component library, dark mode. Log decisions here when they happen.
