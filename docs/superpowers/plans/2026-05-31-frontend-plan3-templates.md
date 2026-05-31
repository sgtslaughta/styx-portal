# Frontend Rework — Plan 3: Templates & Registry

> **For agentic workers:** Execute task-by-task. NO test runner — verify each task with `cd /home/user/code/remote-access/frontend && npm run lint`, `npm run build` at end. Commit per task. PRESERVE all behavior (launch/save flow, registry hover-preview, GPU/Selkies config).

**Goal:** Decompose `launch-modal.tsx` (490 lines), remove its hardcoded badge colors, replace `template-card.tsx`'s native `confirm()` with `ConfirmDialog`, and standardize the registry search field on `SearchSortBar`. The registry mouse-following iframe preview is a recent, deliberate feature — DO NOT remove or restructure it.

**Primitives:** `@/components/common/confirm-dialog`, `@/components/common/search-sort-bar`, `@/lib/status` (not needed here), tokens `text-success`/`text-warning`/`border-success`/`border-warning`.

---

## Task 1: Extract GpuIndicator to its own file + token colors

**Files:**
- Create: `frontend/src/components/templates/launch-gpu-indicator.tsx`
- Modify: `frontend/src/components/templates/launch-modal.tsx`

- [ ] **Step 1:** Move the `GpuIndicator` function (currently lines ~364–426 of launch-modal.tsx) verbatim into `launch-gpu-indicator.tsx`. Add the needed imports at the top of the new file: `import { useState } from "react";`, `import { Badge } from "@/components/ui/badge";`, `import { Switch } from "@/components/ui/switch";`, `import { Gpu } from "lucide-react";`. Export it: `export function GpuIndicator(...)`.
- [ ] **Step 2:** In the moved code, change the two hardcoded badge colors to tokens:
  - `text-green-600 border-green-600/30` → `text-success border-success/30`
  - `text-yellow-600 border-yellow-600/30` → `text-warning border-warning/30`
- [ ] **Step 3:** In launch-modal.tsx, delete the `GpuIndicator` function definition and add `import { GpuIndicator } from "./launch-gpu-indicator";`. Remove now-unused imports from launch-modal (e.g. `Gpu` from lucide if no longer used there — check first).
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/templates/launch-gpu-indicator.tsx src/components/templates/launch-modal.tsx
git commit -m "refactor(templates): extract GpuIndicator, token badge colors"
```

---

## Task 2: Extract SelkiesSettings to its own file

**Files:**
- Create: `frontend/src/components/templates/launch-selkies-settings.tsx`
- Modify: `frontend/src/components/templates/launch-modal.tsx`

- [ ] **Step 1:** Move the `SelkiesSettings` function (currently lines ~428–490) verbatim into `launch-selkies-settings.tsx`. Add imports: `import { useState } from "react";`, `import { Button } from "@/components/ui/button";`, `import { Badge } from "@/components/ui/badge";`, `import { Input } from "@/components/ui/input";`, `import { SELKIES_DEFAULTS, SELKIES_GROUPS } from "@/lib/selkies-defaults";`. Export it.
- [ ] **Step 2:** In launch-modal.tsx, delete the `SelkiesSettings` function and add `import { SelkiesSettings } from "./launch-selkies-settings";`. Remove now-unused imports from launch-modal (`SELKIES_DEFAULTS`, `SELKIES_GROUPS` if only used by SelkiesSettings; check `Badge` is still used elsewhere in launch-modal before removing).
- [ ] **Step 3:** Verify `npm run lint` (confirm launch-modal is now ~370 lines and no unused-import or missing-import errors). Commit:
```bash
git add src/components/templates/launch-selkies-settings.tsx src/components/templates/launch-modal.tsx
git commit -m "refactor(templates): extract SelkiesSettings to own file"
```

---

## Task 3: template-card destroy → ConfirmDialog

**Files:**
- Modify: `frontend/src/components/templates/template-card.tsx`

- [ ] **Step 1:** Add `import { useState } from "react";` and `import { ConfirmDialog } from "@/components/common/confirm-dialog";`.
- [ ] **Step 2:** Add state `const [confirmOpen, setConfirmOpen] = useState(false);`. Change `handleDelete` to stop propagation and open the dialog instead of calling `confirm()`:
```tsx
  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    setConfirmOpen(true);
  }
  function doDelete() {
    deleteTemplate.mutate(template.id, {
      onError: (err) => toast.error(`Delete failed: ${err.message}`),
      onSuccess: () => toast.success(`Deleted ${template.display_name}`),
    });
  }
```
- [ ] **Step 3:** Add the dialog at the end of the returned JSX (inside the root div, after the button row):
```tsx
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete template "${template.display_name}"?`}
        description="This removes the template definition. Running instances are unaffected."
        confirmLabel="Delete"
        variant="destructive"
        confirmPhrase={template.display_name}
        onConfirm={doDelete}
      />
```
Note: ConfirmDialog renders its own portal Dialog; placing it inside the card's clickable root is fine because the dialog uses a portal — but ensure the trigger button's `e.stopPropagation()` prevents the card's `onLaunch`/select. (The card root here has no onClick, so no conflict — verify.)
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/templates/template-card.tsx
git commit -m "refactor(templates): card delete uses ConfirmDialog type-to-confirm"
```

---

## Task 4: registry-browser search → SearchSortBar

**Files:**
- Modify: `frontend/src/components/templates/registry-browser.tsx`

DO NOT touch `RegistryCard` (the hover iframe preview). Only standardize the top search/filter bar.

- [ ] **Step 1:** Replace the top bar block (the `<div className="mb-4 flex flex-wrap items-center gap-3">…</div>` containing the search Input and category Buttons) with `SearchSortBar` wrapping the category Buttons as children:
```tsx
      <div className="mb-4">
        <SearchSortBar query={search} onQueryChange={setSearch} placeholder="Search images…">
          <div className="flex flex-wrap gap-1">
            {CATEGORIES.map((cat) => (
              <Button key={cat} variant={category === cat ? "default" : "ghost"} size="sm" onClick={() => setCategory(cat)} className="text-xs">
                {cat}
              </Button>
            ))}
          </div>
        </SearchSortBar>
      </div>
```
- [ ] **Step 2:** Add `import { SearchSortBar } from "@/components/common/search-sort-bar";`. Remove the now-unused `Search` and `Input` imports IF they are no longer referenced anywhere in the file (Search/Input are used only in the removed block — confirm and remove).
- [ ] **Step 3:** Verify `npm run lint`. Commit:
```bash
git add src/components/templates/registry-browser.tsx
git commit -m "refactor(templates): registry search uses shared SearchSortBar"
```

---

## Phase Verification

- [ ] **Step 1:** `npm run build` — must pass.
- [ ] **Step 2:** `grep -rnE "confirm\(|green-600|yellow-600" src/components/templates/` — expect NO matches.
- [ ] **Step 3:** Report final line counts: `wc -l src/components/templates/launch-modal.tsx src/components/templates/launch-gpu-indicator.tsx src/components/templates/launch-selkies-settings.tsx`.
- [ ] **Step 4:** Manual smoke: open registry → search/filter works, hover preview still works; import an image → launch modal opens with all tabs (Resources/Env/Volumes/Ports/Security/Selkies), GPU indicator shows; Save & Launch + Save as Template both work; My Templates → delete shows type-to-confirm dialog.

## Notes for executor
- Do NOT modify use-templates.ts, use-instances.ts, use-gpu.ts, the API client, or env-editor.tsx (env-editor is already clean).
- Preserve the launch modal's full form state and `buildTemplateData`/`upsertTemplate`/`handleSaveAndLaunch`/`handleSaveTemplate` logic exactly.
- The launch modal stays a centered Dialog (not a Drawer) — it's a wide multi-tab form.
