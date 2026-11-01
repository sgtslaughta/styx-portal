# UI rework "Glance": design spec

Approved with the owner on 2026-11-01 through browser mockups. The mockups are the visual source of truth:
`docs/design/ui-rework-2026-11/c5-glance.html` (app, all admin pages) and `login-waves.html` (login).
Open them with a browser straight from disk. Screenshots are in `docs/design/ui-rework-2026-11/shots/`.

## Goals

Clean, intuitive and sleek. It must not overwhelm plain users, while admins still reach every detail. Use space efficiently, and avoid long scrolls and extra clicks.

## Theme

- Keep the Styx teal palette (`globals.css` tokens). Add **metallic gold** ("obol") as the only accent:
  - `--obol`: `linear-gradient(135deg, #6E4C16 0%, #B8862F 22%, #F1DA9A 46%, #C9A04E 58%, #8A6420 80%, #D9B565 100%)`
  - `--obol-edge`: `linear-gradient(135deg, #8A6420, #F1DA9A 45%, #A9792C 70%, #E6C67A)`
- Gold is used for: the active-tab underline (shell tabs and admin side nav), section-break rules, the one primary action per view (`btn-gold`), input focus rings, and "changed" markers. It is never used for decoration elsewhere.
- **Section break** = heading + a 1px brushed-gold hairline with a drop shadow, fading out to the right (`.sec-head .rule` in the mockup).
- **Header**: keep the existing diagonal "river" lines, but drawn in brushed gold, with a dark shadow line beside each one. They fade out to the right. A soft frosted patch (backdrop blur 5px, radial mask) sits behind the logo and the nav labels. The header was tried with wave lines and the owner rejected it, so do not use wave lines in the header.
- **Glass button**: a frosted pill with a lit top edge. A water-ripple simulation (`ripple.js`, height-field) draws light glints on it when hovered or pressed.
- **Chart palette** (passed the dataviz validator, adjacent pairs, both modes). Order is fixed: teal, gold, violet, coral, blue, then grey for "Others".
  - Dark: `#0596A3 #B9852A #8573DE #D65B3C #4F86E0`, Others `#56676C`
  - Light: `#008E9C #A87423 #6B58C9 #C2512F #3A6FCC`, Others `#9AA6A9`

## Home

The two top-level tabs are **Home** and **Admin** (admin only). The Template gallery tab is removed.

Sections, in order, each with a gold section break:
1. **Recent**: the only place with large live thumbnails (16:10). Shows the last 3 things the user opened (desktops or containers). The glass Resume/Connect button sits on the thumbnail, and the thumbnail refracts like water under the cursor.
2. **Desktops**: compact tiles (icon, name, status line). The glass action button appears on hover, or always on touch screens.
3. **Apps**: a dock of icons. "Needs setup" shows a red dot (admins only).
4. **Containers**: rows (icon, name, status, glass action). The **New container** button (solid teal with a "+" box) sits at the right of this section's heading.

The **status rail** (admins only) is pinned to the right, full height, and collapses to a 56px strip showing CPU %, live count and a "to check" badge. Its state is stored in localStorage `styxRail`, it starts collapsed on screens 900px wide or narrower, and it auto-collapses on Admin pages.

## New container drawer

A right-hand drawer, `min(760px, 100vw)`, with a scrim, closed by Esc. It has two steps:
- **Pick step**:
  - A search box and category pills.
  - **Your setups**: shared templates, one click to launch.
  - **LinuxServer catalog**: the primary grid of logo, name, category, two-line description, and a "You have a saved setup" badge.
  - A "Use another image" field for any `registry/image:tag`.
- **Launch step**:
  - Name.
  - **Size presets** Light / Standard / Heavy (defaults below; admins can edit them).
  - "Keep my profile".
  - "When idle" (Stop after 30 min, Pause after 30 min, or Keep running).
  - "Advanced" folded away: environment, volumes and ports, prefilled from the LSIO metadata.
  - "Save as a setup" (admins only).

Setups are **shared** (templates with `shared=True`). Admins create and edit them; users launch them.

Size presets live in setting `CONTAINER_SIZE_PRESETS`, a JSON list. Default:
`[{"id":"light","label":"Light","cpus":2,"memory_gb":2,"gpu":false},{"id":"standard","label":"Standard","cpus":4,"memory_gb":4,"gpu":false},{"id":"heavy","label":"Heavy","cpus":6,"memory_gb":8,"gpu":true}]`

## Admin

- **Side nav**: 210px wide and sticky, with a "Find a setting" filter. Groups: Monitoring (Overview, Health, Sessions, Logs, Relay cost*), People (Users and groups, Sign-in providers), Infrastructure (Workstations, Apps, Images and setups, Streaming), Settings (Security and limits, Sessions and timeouts), My account (Sign-in card, Connected accounts). The active item gets the gold underline. (*Relay cost appears only when `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_ANALYTICS_TOKEN` are both set.)
- **Content width**: up to 1640px.
- **Settings pages**:
  - Groups render as bordered cards in a grid, `repeat(auto-fill, minmax(360px, 1fr))`.
  - Each row is laid out as `label | 138px control | 22px reset slot`. The reset slot is always reserved, so rows never shift.
  - Numbers show human units (min, hours, Mbps, per min). Browser number spinners are hidden.
  - Help appears as a "?" tooltip.
  - A changed field gets a gold border and a ↺ reset button.
  - **Saving happens only when Save is clicked**: a floating pill at the bottom centre reads "N unsaved changes · Discard · Save changes" and is hidden when there are no changes.
- **Users and groups**: one dense table.
  - The role is changed from a dropdown inside the row.
  - Filter segments: All, Admins, Locked, Invites.
  - Locked rows are tinted, with Unlock in the row.
  - Row actions appear on hover, and rows have checkboxes.
- **Streaming**:
  - "Defaults for every workstation" card: segmented Connection, Codec and Frame rate controls; max bitrate (Mbps); quality (CRF); switches for Sharpen still screens, Full-motion encoding and Full colour 4:4:4.
  - "Relay for remote viewers (TURN)" card: provider (segmented), IDs, a Replace token button, a status line with Check setup, and a usage meter.
  - "Per workstation" table: each value shows "Default (X)" unless overridden; overrides are highlighted gold; a live "Streaming now" column.

## Overview (Monitoring)

- **Five tiles**: CPU, Memory, Disk and Live sessions each show a value, a 24h **sparkline** and a one-line note. Health shows a value and a 24-cell hourly pass/warn strip.
- **Three charts** in a row, all the same height:
  - **Server load**: CPU and memory lines, with 24h / 7d / 30d buttons, a crosshair and a tooltip.
  - **Sessions per day**: 14 days of bars.
  - **Streaming time**: stacked horizontal bars per workstation, split by user, last 7 days.
- **Lists**: Needs a look (each item with its action), a Relay cost card (only when the CF analytics token is set), and Active now (each session with an End button).
- **Top-5 rule** for every breakdown: the 5 largest entities get colours, and everything else folds into a grey "Others" segment or an "Others · N more" row.

## Relay cost page (only when the CF analytics token is set)

- **Period**: Last month, This month or 6 months.
- **Tiles**: used / free allowance, projected month-end, estimated cost, budget left, and % of sessions relayed.
- **Charts**: relay GB per day (30 days); GB per month (6 months) with a dashed budget line; and three horizontal-bar charts: by user (top 5), by workstation (top 5), and why sessions were relayed.
- **Table**: a "Show as table" option.

## Login

- **Split layout**:
  - Waves panel: `minmax(0, 1fr)`.
  - Sign-in panel: `minmax(400px, min(40vw, 620px))`.
- **Waves panel**:
  - 28 brushed-gold perspective wave lines below 42% of the panel height. They flow slowly and continuously, with **no cursor interaction**.
  - A specular band drifts along the lines.
  - **Light mode** keeps the dark underline and uses a dark bronze edge highlight (the inverted look).
  - A "calm" fade sits behind the headline.
  - The "sun" is a radial glow plus a separate **Bayer 8×8 dither** layer (patchy, 2-scale block noise, 5px cells, 1px round dots), stopping 18px above the horizon.
- **Headline**: "Cross over to your workspaces." There is no subtitle and no gold rule. It reveals uniformly as one block: `blur(16px)` with red/cyan fringes clearing to sharp over 2.2s. There is no transform and no `will-change`, because those caused an end-of-animation jump.
- **Sign-in panel**:
  - **Glyph beams**: an IBM Plex Mono glyph grid with Greek letters, and narrow 45° beams swept diagonally (85px/s) with per-glyph shimmer and scramble. Beam cores turn champagne. Glyphs calm (fade out) behind the logo and the form. It redraws at about 30fps.
  - The logo (classic teal Waves icon) is at the top-left of the panel.
  - The glass teal Sign in button has gold edges and water glints.
- **Reduced motion**: every animation becomes a still frame.
