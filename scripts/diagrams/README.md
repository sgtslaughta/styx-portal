# Diagram tooling

Docs diagrams live in `docs/assets/diagrams/` as `<name>.mmd` (Mermaid draft), `<name>.excalidraw` (editable scene) and generated `<name>-light.svg` / `<name>-dark.svg`.

- `from-mermaid.sh [name...]` extracts any ```mermaid blocks from README/docs (rewriting them to image links), converts `.mmd` to `.excalidraw`, then calls `render.sh`. Overwrites `.excalidraw`.
- `render.sh [name...]` renders `.excalidraw` to the light and dark SVGs (fonts embedded, no background, padding 16). Edit a scene on excalidraw.com, save it back, run this.
- Everything runs in `mcr.microsoft.com/playwright` via Docker (needs Docker only; nothing is installed on the host). `package.json` pins the exact versions.
- `page.js` is the browser-side code (convert, classDef colours, dark-mode colour compensation); `run.mjs` drives it; `extract.mjs` handles the Markdown.
- Known limits: the converter lays out edge labels without a background, so some labels sit on lines; hand-edit in Excalidraw if one is unreadable.
