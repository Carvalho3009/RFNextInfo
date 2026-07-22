# RF Loot Editor — Agent Instructions

## Stack
- React + TypeScript + Vite
- Electron with `electron/main.cjs` and `electron/preload.cjs`
- SQLite service in `electron/services/database.cjs`
- Main UI orchestration in `src/App.tsx`
- CSS in `src/App.css`

## Project rules
- Do not rewrite the whole app unless explicitly requested.
- Prefer small, scoped changes.
- Before editing more than 3 files, propose a plan first.
- Keep IPC handlers in sync:
  - renderer call in `src/App.tsx`
  - API bridge in `electron/preload.cjs`
  - handler in `electron/main.cjs`
  - DB/service logic in `electron/services/database.cjs`
- Do not break profile isolation. Each profile uses its own DB under `electron/profiles/<profile>/`.
- For Excel writes, only write to the intended sheet and intended cells.
- Preserve existing localStorage keys unless migration is explicitly required.
- Avoid loading full large tables into React state when SQLite pagination/filtering can be used.
- Maintain compatibility with manual validation; there is no robust automated test suite yet.

## Common workflows
### Adding a new UI feature
1. Update `src/App.tsx`.
2. Add CSS only in `src/App.css`.
3. If data is needed from SQLite, add IPC bridge in preload/main.
4. Add DB logic in `database.cjs`.
5. Verify build.

### Adding IPC
Always update all three:
- `electron/preload.cjs`
- `electron/main.cjs`
- caller in `src/App.tsx`

### Table/filter changes
- Preserve pagination.
- Preserve column visibility/width state.
- Preserve current filter context when possible.
- Do not bypass SQLite filtering for large datasets.

## Known fragile areas
- Auto-fit of visual column “2”.
- Excel multi-sheet write flow, especially `BoxItemOut`.
- Native select styling limitations.
- Large table performance.
- App.tsx is large and regression-prone.

## Validation checklist
Before finishing:
- Run `npm run build`.
- If Electron handlers changed, verify no “No handler registered” error.
- If filters changed, verify pagination still works.
- If Excel write changed, verify only target sheet is modified.
- Summarize changed files and risk areas.

When working on React/Electron/IPC architecture, follow the local skill:
.codex/skills/rf-react-electron/SKILL.md