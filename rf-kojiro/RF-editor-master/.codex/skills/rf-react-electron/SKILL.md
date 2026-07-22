---

name: rf-react-electron
description: Use this skill when working on the RF Loot Editor React + Electron + TypeScript app, especially for IPC, preload, main process, SQLite integration, profiles, table performance, Excel writing, and UI changes.
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# RF React Electron Skill

## Project context

This project is RF Loot Editor, a desktop tool for editing RF Online loot-related data.

Stack:

* React
* TypeScript
* Vite
* Electron
* CommonJS Electron files:

  * `electron/main.cjs`
  * `electron/preload.cjs`
* SQLite service:

  * `electron/services/database.cjs`
* Main UI:

  * `src/App.tsx`
* CSS:

  * `src/App.css`

## Communication language

Always answer the user in Portuguese.

Technical names, file names, function names and error messages may remain in English.

## Core architecture

The app uses this flow:

```txt
React renderer
→ window.electronAPI
→ electron/preload.cjs
→ ipcRenderer.invoke(...)
→ electron/main.cjs
→ ipcMain.handle(...)
→ electron/services/database.cjs
→ SQLite / files / Excel
```

The renderer must not access Node.js directly.

## Mandatory Electron rules

* Do not use `require()` inside React files.
* Do not use `ipcRenderer` directly inside React files.
* Do not use `fs`, `path`, `sqlite`, `xlsx`, or Electron APIs directly inside React.
* React must call only APIs exposed through `window.electronAPI`.
* Keep `contextIsolation` enabled.
* Keep Node access inside Electron main/preload/service files.
* Keep IPC channel names consistent between:

  * `src/App.tsx`
  * `electron/preload.cjs`
  * `electron/main.cjs`
  * `electron/services/database.cjs`

## Current preload pattern

The project exposes APIs through:

```js
contextBridge.exposeInMainWorld("electronAPI", {
  someFunction: async (payload) => {
    return await ipcRenderer.invoke("some-channel", payload);
  },
});
```

React should consume them like:

```ts
await window.electronAPI.someFunction(payload);
```

Never consume them like:

```ts
ipcRenderer.invoke("some-channel", payload);
```

or:

```ts
require("electron");
```

## Adding a new IPC feature

When adding a new feature that needs backend access, update all relevant layers.

### 1. React caller

In `src/App.tsx`, call:

```ts
await window.electronAPI.myFeature(payload);
```

### 2. Preload bridge

In `electron/preload.cjs`, expose:

```js
myFeature: async (payload) => {
  return await ipcRenderer.invoke("my-feature", payload);
},
```

### 3. Main handler

In `electron/main.cjs`, register:

```js
ipcMain.handle("my-feature", async (_event, payload) => {
  return await someServiceFunction(payload);
});
```

### 4. Service/database layer

If the feature touches SQLite or files, put the logic in:

```txt
electron/services/database.cjs
```

or another appropriate service file.

Do not put large database/file logic directly inside React.

## Debugging IPC issues

If a button does nothing or a feature silently fails, check in this order:

1. Does the React handler actually run?
2. Does React call `window.electronAPI.someFunction()`?
3. Is `someFunction` exposed in `electron/preload.cjs`?
4. Does preload invoke the correct IPC channel?
5. Does `electron/main.cjs` register `ipcMain.handle("same-channel")`?
6. Does the handler throw an error?
7. Is the error being swallowed in React?
8. Is there a console error in DevTools?
9. Is there a terminal error in the Electron process?

If Electron shows:

```txt
No handler registered for ...
```

then preload is invoking a channel that does not exist in `main.cjs`.

## CommonJS / ESM rules

The Electron files currently use `.cjs`.

Therefore:

* Keep `electron/main.cjs` as CommonJS.
* Keep `electron/preload.cjs` as CommonJS.
* Use `require()` in `.cjs` Electron files when needed.
* Use `import/export` in React/TypeScript files.
* Do not convert the Electron files to ESM unless explicitly requested.

If the project has `"type": "module"` in `package.json`, `.cjs` files are still valid CommonJS files.

## React rules

* Prefer small, scoped changes.
* Avoid rewriting `src/App.tsx` entirely.
* Do not move large parts of the app unless explicitly requested.
* Preserve existing localStorage keys unless migration is explicitly required.
* Preserve pagination, filters, column visibility, and column width state.
* Avoid loading full large tables into React state if SQLite pagination/filtering can be used.
* Keep UI behavior predictable and easy to manually validate.

## CSS rules

* Put CSS changes in `src/App.css`.
* Avoid adding new styling systems unless explicitly requested.
* Preserve current layout unless the user asks for a redesign.
* Be careful with native select styling limitations.

## SQLite/profile rules

* Do not break profile isolation.
* Each profile uses its own database/files under:

```txt
electron/profiles/<profile>/
```

* Never accidentally mix data between profiles.
* When adding database operations, ensure they operate on the active/intended profile.
* Prefer SQLite filtering/pagination for large datasets.
* Avoid full table scans from the renderer when possible.

## Excel rules

When editing Excel files:

* Only write to the intended workbook.
* Only write to the intended sheet.
* Only write to the intended cells/ranges.
* Be especially careful with multi-sheet flows.
* Be especially careful with `BoxItemOut`.
* Do not overwrite unrelated sheets.
* Do not reformat the workbook unless explicitly requested.

## Known fragile areas

Be extra careful around:

* Auto-fit of visual column “2”.
* Excel multi-sheet write flow.
* `BoxItemOut`.
* Native select styling.
* Large table performance.
* `src/App.tsx`, because it is large and regression-prone.
* IPC synchronization between renderer, preload, main and database service.

## Before editing

Before making changes, inspect:

```txt
package.json
electron/main.cjs
electron/preload.cjs
src/App.tsx
electron/services/database.cjs
```

Only inspect files relevant to the task when the task is small.

Before editing more than 3 files, propose a short plan.

## Validation checklist

Before finishing, when possible:

* Run `npm run build`.
* If IPC changed, verify there is no `No handler registered` error.
* If filters changed, verify pagination still works.
* If Excel writing changed, verify only the target sheet is modified.
* If profile logic changed, verify the correct profile is used.
* Summarize changed files.
* Mention risk areas honestly.

## Response style

When reporting back:

* Be direct.
* Use Portuguese.
* Say which files changed.
* Say what was fixed or added.
* Mention any command run.
* Mention any command that failed.
* Do not give long theoretical explanations unless the user asks.

## Preferred task behavior

For bug fixes:

1. Reproduce or identify the broken flow.
2. Find the smallest likely cause.
3. Patch only what is necessary.
4. Validate with build or manual reasoning.
5. Explain the result.

For new features:

1. Identify whether it needs React only or IPC/backend too.
2. If IPC/backend is needed, update all layers consistently.
3. Keep database/file logic outside React.
4. Preserve existing behavior.
5. Validate.

For refactors:

* Avoid broad refactors unless explicitly requested.
* Do not refactor unrelated code while fixing a bug.
* Do not rename public APIs casually.
* Do not change storage formats without migration.

## Important project principle

This project does not have a robust automated test suite yet.

Because of that:

* Prefer conservative changes.
* Avoid unnecessary rewrites.
* Preserve existing working behavior.
* Make changes that are easy to manually verify.
