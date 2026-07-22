const { app, BrowserWindow, ipcMain, dialog, screen } = require("electron");
const fs = require("fs/promises");
const fsSync = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const XLSX = require("xlsx");
const yauzl = require("yauzl");

let clearItemsBySource;
let replaceSourceColumns;
let listSourceColumns;
let replaceExcelFileState;
let listExcelFileState;
let getExcelFilePath;
let getItemsForEdit;
let setAppSetting;
let getAppSetting;
let replaceItemsFromSource;
let countItems;
let countItemEffects;
let listSourceFiles;
let listItems;
let listItemColumnValues;
let listEffectDictionaries;
let setSourceDictionary;
let listEffectDictionary;
let saveEffectDictionaryEntry;
let deleteEffectDictionaryEntry;
let replaceBossMonsters;
let countBossMonsters;
let generateGrade1WeaponSocketCombines;
let listGeneratedWeaponSocketCombineRows;
let getExtraItemColumnCount;

let mainWindow = null;
let lastWindowState = null;
const hasSingleInstanceLock = app.requestSingleInstanceLock();
const WINDOW_BOUNDS_SETTING_KEY = "window_bounds";
const WINDOW_MAXIMIZED_SETTING_KEY = "window_maximized";
const PROFILE_ROOT = path.join(__dirname, "profiles");
const PROFILE_META_PATH = path.join(PROFILE_ROOT, "profiles.json");
const DEFAULT_PROFILE_ID = "default";
const BACKUP_ROOT = path.join(__dirname, "backups");

async function createFileBackup(filePath, reason = "edit") {
  const source = String(filePath || "").trim();
  if (!source) return "";
  const exists = await fs
    .access(source)
    .then(() => true)
    .catch(() => false);
  if (!exists) return "";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const baseName = path.basename(source);
  const targetDir = path.join(BACKUP_ROOT, baseName);
  await fs.mkdir(targetDir, { recursive: true });
  const backupPath = path.join(targetDir, `${stamp}__${reason}__${baseName}`);
  await fs.copyFile(source, backupPath);
  return backupPath;
}

async function listBackupsForSource(sourceFile) {
  const absolutePath = await resolveExcelPathForSource(String(sourceFile || ""));
  if (!absolutePath) return [];
  const baseName = path.basename(absolutePath);
  const targetDir = path.join(BACKUP_ROOT, baseName);
  const entries = await fs.readdir(targetDir, { withFileTypes: true }).catch(() => []);
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort((a, b) => b.localeCompare(a))
    .map((name) => ({
      name,
      path: path.join(targetDir, name),
      sourcePath: absolutePath,
    }));
}

async function restoreBackupForSource(sourceFile, backupName) {
  const absolutePath = await resolveExcelPathForSource(String(sourceFile || ""));
  if (!absolutePath) throw new Error("Arquivo original nao encontrado.");
  const baseName = path.basename(absolutePath);
  const backupPath = path.join(BACKUP_ROOT, baseName, String(backupName || ""));
  await fs.access(backupPath);
  await fs.copyFile(backupPath, absolutePath);
  await trackExcelSourcePath(sourceFile, absolutePath);
  return { restored: true };
}

async function writeGeneratedRowsToExcel(filePath, sourceFile, rows, options = {}) {
  await createFileBackup(filePath, options.backupReason || "save-generated-rows");
  const workbook = XLSX.readFile(filePath, {
    cellStyles: true,
    cellNF: true,
    cellDates: true,
    bookVBA: true,
  });
  const sourceBaseName = path.basename(sourceFile, path.extname(sourceFile)).toLowerCase();
  const sheetName =
    (options.sheetName &&
      workbook.SheetNames.find(
        (sheet) => String(sheet).trim().toLowerCase() === String(options.sheetName).trim().toLowerCase()
      )) ||
    workbook.SheetNames.find((sheet) => String(sheet).trim().toLowerCase() === sourceBaseName) ||
    workbook.SheetNames[0];
  if (!sheetName) {
    throw new Error(`Aba nao encontrada em ${sourceFile}.`);
  }

  const worksheet = workbook.Sheets[sheetName];
  const currentRange = XLSX.utils.decode_range(worksheet["!ref"] || "A1:A1");
  const columnCount = options.exactColumnCount
    ? Math.max(1, Number(options.columnCount || 0))
    : Math.max(1, Number(options.columnCount || 0), currentRange.e.c + 1);
  const fillEmptyWith = options.fillEmptyWith ?? "";
  const materialEmptyPattern = ["-1", "FFFFFFFF", "-1"];
  const resultEmptyPattern = ["-1", "FFFFFFFF", "0", "4294967295", "4294967295", "-1"];
  const shouldFillCombineMaterials = Boolean(options.fillCombineMaterialPattern);
  const shouldFillCombineResults = Boolean(options.fillCombineResultPattern);
  const generatedRowNumbers = [];

  let sequentialRowIndex = null;
  if (options.placeByCodePrefix) {
    const prefix = String(options.placeByCodePrefix);
    let firstExistingIndex = null;
    for (let rowIndex = currentRange.s.r; rowIndex <= currentRange.e.r; rowIndex += 1) {
      const code = String(worksheet[XLSX.utils.encode_cell({ r: rowIndex, c: 0 })]?.v ?? "");
      if (code.startsWith(prefix)) {
        firstExistingIndex = rowIndex;
        break;
      }
    }
    sequentialRowIndex = firstExistingIndex ?? currentRange.e.r + 1;
  }

  for (const row of rows) {
    const excelRow =
      sequentialRowIndex === null
        ? Number(row.excel_row ?? row.excelRow ?? 0)
        : sequentialRowIndex + 1;
    if (!Number.isFinite(excelRow) || excelRow <= 0) {
      continue;
    }
    if (sequentialRowIndex !== null) {
      sequentialRowIndex += 1;
    }
    generatedRowNumbers.push(excelRow);
    const values = Array.from({ length: columnCount }, () => fillEmptyWith);
    values[0] = String(row.code ?? "");

    if (shouldFillCombineMaterials) {
      for (const columnNumber of [7, 10, 13, 16, 19]) {
        for (let offset = 0; offset < materialEmptyPattern.length; offset += 1) {
          const targetIndex = columnNumber + offset - 1;
          if (targetIndex >= 0 && targetIndex < values.length) {
            values[targetIndex] = materialEmptyPattern[offset];
          }
        }
      }
    }

    if (shouldFillCombineResults) {
      for (let columnNumber = 24; columnNumber + resultEmptyPattern.length - 1 <= columnCount; columnNumber += 6) {
        for (let offset = 0; offset < resultEmptyPattern.length; offset += 1) {
          const targetIndex = columnNumber + offset - 1;
          if (targetIndex >= 0 && targetIndex < values.length) {
            values[targetIndex] = resultEmptyPattern[offset];
          }
        }
      }
    }

    for (let index = 1; index <= columnCount; index += 1) {
      const key = `extra_${String(index).padStart(2, "0")}`;
      const value = row[key];
      if (value !== undefined && value !== null && String(value).trim() !== "") {
        values[index - 1] = String(value);
      }
    }

    for (let columnIndex = 0; columnIndex < values.length; columnIndex += 1) {
      const address = XLSX.utils.encode_cell({
        r: excelRow - 1,
        c: columnIndex,
      });
      const value = values[columnIndex];
      const numericValue = Number(value);
      const isNumber =
        String(value).trim() !== "" &&
        Number.isFinite(numericValue) &&
        /^-?\d+(\.\d+)?$/.test(String(value));
      worksheet[address] = {
        t: isNumber ? "n" : "s",
        v: isNumber ? numericValue : String(value),
      };
    }
  }

  const range = XLSX.utils.decode_range(worksheet["!ref"] || "A1:A1");
  for (const row of rows) {
    const excelRow = Number(row.excel_row ?? row.excelRow ?? 0);
    if (Number.isFinite(excelRow) && excelRow > range.e.r + 1) {
      range.e.r = excelRow - 1;
    }
  }
  if (options.clearRowsAfterLast && generatedRowNumbers.length > 0) {
    const lastGeneratedRowIndex = Math.max(...generatedRowNumbers) - 1;
    for (let rowIndex = lastGeneratedRowIndex + 1; rowIndex <= range.e.r; rowIndex += 1) {
      for (let columnIndex = 0; columnIndex <= range.e.c; columnIndex += 1) {
        delete worksheet[XLSX.utils.encode_cell({ r: rowIndex, c: columnIndex })];
      }
    }
    range.e.r = Math.max(range.s.r, lastGeneratedRowIndex);
  }
  range.e.c = options.exactColumnCount
    ? columnCount - 1
    : Math.max(range.e.c, columnCount - 1);
  worksheet["!ref"] = XLSX.utils.encode_range(range);
  worksheet["!freeze"] = { xSplit: 0, ySplit: 2, topLeftCell: "A3", activePane: "bottomLeft", state: "frozen" };
  worksheet["!pane"] = { xSplit: 0, ySplit: 2, topLeftCell: "A3", activePane: "bottomLeft", state: "frozen" };
  XLSX.writeFile(workbook, filePath);
  if (options.freezeTopRowsWithExcel) {
    freezeTopRowsWithExcel(filePath, [sheetName]);
  }
  return { sheetName };
}

function quotePowerShellString(value) {
  return `'${String(value || "").replace(/'/g, "''")}'`;
}

function freezeTopRowsWithExcel(filePath, sheetNames = []) {
  if (process.platform !== "win32") {
    return { applied: false, reason: "not-windows" };
  }

  const workbookPath = quotePowerShellString(filePath);
  const tempRoot = quotePowerShellString(path.join(app.getPath("temp"), `rf-freeze-${Date.now()}`));
  const script = `
$source = ${workbookPath}
$tempRoot = ${tempRoot}
try {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force }
  New-Item -ItemType Directory -Path $tempRoot | Out-Null
  [System.IO.Compression.ZipFile]::ExtractToDirectory($source, $tempRoot)
  $worksheets = Join-Path $tempRoot "xl\\worksheets"
  $sheetViews = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews>'
  Get-ChildItem $worksheets -Filter "*.xml" | ForEach-Object {
    $xml = Get-Content $_.FullName -Raw -Encoding UTF8
    if ($xml -match '<sheetViews>[\\s\\S]*?</sheetViews>') {
      $xml = [regex]::Replace($xml, '<sheetViews>[\\s\\S]*?</sheetViews>', $sheetViews, 1)
    } elseif ($xml -match '<sheetPr[\\s\\S]*?</sheetPr>') {
      $xml = [regex]::Replace($xml, '(<sheetPr[\\s\\S]*?</sheetPr>)', '$1' + $sheetViews, 1)
    } else {
      $xml = [regex]::Replace($xml, '(<worksheet[^>]*>)', '$1' + $sheetViews, 1)
    }
    Set-Content $_.FullName -Value $xml -Encoding UTF8
  }
  $target = "$source.freeze.tmp"
  if (Test-Path $target) { Remove-Item $target -Force }
  [System.IO.Compression.ZipFile]::CreateFromDirectory($tempRoot, $target)
  Move-Item $target $source -Force
} finally {
  if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
`;
  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
    { encoding: "utf8", windowsHide: true, timeout: 30000 }
  );
  if (result.status !== 0) {
    throw new Error(`Nao foi possivel congelar as 2 primeiras linhas: ${result.stderr || result.error?.message || "erro desconhecido"}`);
  }
  return {
    applied: result.status === 0,
    reason: result.stderr || result.error?.message || "",
  };
}

function ensureProfileStoreSync() {
  const legacyDbPath = path.join(__dirname, "rfloot.db");
  const defaultProfileDbPath = getProfileDbPath(DEFAULT_PROFILE_ID);

  if (!fsSync.existsSync(PROFILE_ROOT)) {
    fsSync.mkdirSync(PROFILE_ROOT, { recursive: true });
  }

  if (!fsSync.existsSync(PROFILE_META_PATH)) {
    const seed = {
      activeProfileId: DEFAULT_PROFILE_ID,
      profiles: [{ id: DEFAULT_PROFILE_ID, name: "Perfil Padrão" }],
    };
    fsSync.writeFileSync(PROFILE_META_PATH, JSON.stringify(seed, null, 2), "utf8");
  }

  ensureProfileDbDirectorySync(DEFAULT_PROFILE_ID);
  if (!fsSync.existsSync(defaultProfileDbPath) && fsSync.existsSync(legacyDbPath)) {
    fsSync.copyFileSync(legacyDbPath, defaultProfileDbPath);
    for (const ext of [".wal", ".shm"]) {
      const from = `${legacyDbPath}${ext}`;
      const to = `${defaultProfileDbPath}${ext}`;
      if (fsSync.existsSync(from)) {
        fsSync.copyFileSync(from, to);
      }
    }
  }
}

function loadProfilesSync() {
  ensureProfileStoreSync();
  try {
    const raw = fsSync.readFileSync(PROFILE_META_PATH, "utf8");
    const parsed = JSON.parse(raw);
    const profiles = Array.isArray(parsed.profiles) ? parsed.profiles : [];
    const pendingDeleteIds = Array.isArray(parsed.pendingDeleteIds)
      ? parsed.pendingDeleteIds.map((value) => String(value))
      : [];
    if (profiles.length === 0) {
      return {
        activeProfileId: DEFAULT_PROFILE_ID,
        profiles: [{ id: DEFAULT_PROFILE_ID, name: "Perfil Padrão" }],
      };
    }
    const activeProfileId =
      typeof parsed.activeProfileId === "string" &&
      profiles.some((profile) => profile.id === parsed.activeProfileId)
        ? parsed.activeProfileId
        : profiles[0].id;
    return { activeProfileId, profiles, pendingDeleteIds };
  } catch {
    return {
      activeProfileId: DEFAULT_PROFILE_ID,
      profiles: [{ id: DEFAULT_PROFILE_ID, name: "Perfil Padrão" }],
      pendingDeleteIds: [],
    };
  }
}

function saveProfilesSync(payload) {
  ensureProfileStoreSync();
  fsSync.writeFileSync(PROFILE_META_PATH, JSON.stringify(payload, null, 2), "utf8");
}

function deleteProfileDirectory(profileId) {
  const profileDir = path.join(PROFILE_ROOT, profileId);
  if (fsSync.existsSync(profileDir)) {
    fsSync.rmSync(profileDir, { recursive: true, force: true });
  }
}

function flushPendingProfileDeletesSync(state) {
  const pending = Array.isArray(state.pendingDeleteIds) ? state.pendingDeleteIds : [];
  if (pending.length === 0) {
    return state;
  }

  const remaining = [];
  for (const profileId of pending) {
    try {
      deleteProfileDirectory(profileId);
    } catch {
      remaining.push(profileId);
    }
  }

  const nextState = {
    ...state,
    pendingDeleteIds: remaining,
  };
  saveProfilesSync(nextState);
  return nextState;
}

function getProfileDbPath(profileId) {
  return path.join(PROFILE_ROOT, profileId, "rfloot.db");
}

function ensureProfileDbDirectorySync(profileId) {
  const profileDir = path.join(PROFILE_ROOT, profileId);
  if (!fsSync.existsSync(profileDir)) {
    fsSync.mkdirSync(profileDir, { recursive: true });
  }
}

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  const profileState = flushPendingProfileDeletesSync(loadProfilesSync());
  const activeProfileId = profileState.activeProfileId || DEFAULT_PROFILE_ID;
  ensureProfileDbDirectorySync(activeProfileId);
  process.env.RF_LOOT_DB_PATH = getProfileDbPath(activeProfileId);
  process.env.RF_LOOT_ACTIVE_PROFILE = activeProfileId;

  ({
    clearItemsBySource,
    replaceSourceColumns,
    listSourceColumns,
    replaceExcelFileState,
    listExcelFileState,
    getExcelFilePath,
    getItemsForEdit,
    setAppSetting,
    getAppSetting,
    replaceItemsFromSource,
    countItems,
    countItemEffects,
    listSourceFiles,
    listItems,
    listItemColumnValues,
    listEffectDictionaries,
    setSourceDictionary,
    listEffectDictionary,
    saveEffectDictionaryEntry,
    deleteEffectDictionaryEntry,
    replaceBossMonsters,
    countBossMonsters,
    generateGrade1WeaponSocketCombines,
    listGeneratedWeaponSocketCombineRows,
    getExtraItemColumnCount,
  } = require("./services/database.cjs"));

  app.on("second-instance", () => {
    if (!mainWindow) {
      return;
    }

    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }

    mainWindow.focus();
  });
}

function createWindow() {
  const bounds = getSafeWindowBounds(lastWindowState);
  mainWindow = new BrowserWindow({
    title: "RF Editor Tool [LIVE-CODE-MARKER]",
    width: bounds.width,
    height: bounds.height,
    x: bounds.x,
    y: bounds.y,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (lastWindowState?.maximized) {
    mainWindow.maximize();
  }

  mainWindow.on("close", () => {
    void saveWindowState(mainWindow);
  });

  mainWindow.loadURL("http://localhost:5173/?live_marker=rf_editor_topbar_v2");
  mainWindow.webContents.on("did-finish-load", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setTitle("RF Editor Tool [LIVE-CODE-MARKER]");
    }
  });
}

if (hasSingleInstanceLock) {
app.whenReady().then(async () => {
  ipcMain.handle("list-profiles", async () => {
    const state = loadProfilesSync();
    return state.profiles.map((profile) => ({
      id: profile.id,
      name: profile.name,
      isActive: profile.id === state.activeProfileId,
    }));
  });

  ipcMain.handle("create-profile", async (_event, payload = {}) => {
    const name = String(payload.name ?? "").trim();
    if (!name) {
      throw new Error("Nome do perfil e obrigatorio.");
    }

    const cloneCurrent = Boolean(payload.cloneCurrent);
    const state = loadProfilesSync();
    const baseId = slugifyProfileName(name) || `perfil-${Date.now()}`;
    let profileId = baseId;
    let suffix = 2;
    while (state.profiles.some((profile) => profile.id === profileId)) {
      profileId = `${baseId}-${suffix}`;
      suffix++;
    }

    ensureProfileDbDirectorySync(profileId);
    if (cloneCurrent) {
      const sourcePath = getProfileDbPath(state.activeProfileId);
      const targetPath = getProfileDbPath(profileId);
      if (fsSync.existsSync(sourcePath)) {
        await fs.copyFile(sourcePath, targetPath);
      }
      for (const ext of [".wal", ".shm"]) {
        const sourceExt = `${sourcePath}${ext}`;
        const targetExt = `${targetPath}${ext}`;
        if (fsSync.existsSync(sourceExt)) {
          await fs.copyFile(sourceExt, targetExt);
        }
      }
    }

    state.profiles.push({
      id: profileId,
      name,
    });
    saveProfilesSync(state);

    return {
      id: profileId,
      name,
      isActive: false,
    };
  });

  ipcMain.handle("rename-profile", async (_event, payload = {}) => {
    const profileId = String(payload.profileId ?? "").trim();
    const name = String(payload.name ?? "").trim();
    if (!profileId || !name) {
      throw new Error("Perfil e nome sao obrigatorios.");
    }

    const state = loadProfilesSync();
    const profile = state.profiles.find((current) => current.id === profileId);
    if (!profile) {
      throw new Error("Perfil invalido.");
    }

    profile.name = name;
    saveProfilesSync(state);
    return {
      id: profile.id,
      name: profile.name,
      isActive: profile.id === state.activeProfileId,
    };
  });

  ipcMain.handle("duplicate-profile", async (_event, payload = {}) => {
    const sourceProfileId = String(payload.sourceProfileId ?? "").trim();
    const name = String(payload.name ?? "").trim();
    if (!sourceProfileId || !name) {
      throw new Error("Perfil de origem e nome sao obrigatorios.");
    }

    const state = loadProfilesSync();
    if (!state.profiles.some((profile) => profile.id === sourceProfileId)) {
      throw new Error("Perfil de origem invalido.");
    }

    const baseId = slugifyProfileName(name) || `perfil-${Date.now()}`;
    let profileId = baseId;
    let suffix = 2;
    while (state.profiles.some((profile) => profile.id === profileId)) {
      profileId = `${baseId}-${suffix}`;
      suffix++;
    }

    ensureProfileDbDirectorySync(profileId);
    const sourcePath = getProfileDbPath(sourceProfileId);
    const targetPath = getProfileDbPath(profileId);
    if (fsSync.existsSync(sourcePath)) {
      await fs.copyFile(sourcePath, targetPath);
    }
    for (const ext of [".wal", ".shm"]) {
      const sourceExt = `${sourcePath}${ext}`;
      const targetExt = `${targetPath}${ext}`;
      if (fsSync.existsSync(sourceExt)) {
        await fs.copyFile(sourceExt, targetExt);
      }
    }

    state.profiles.push({
      id: profileId,
      name,
    });
    saveProfilesSync(state);

    return {
      id: profileId,
      name,
      isActive: false,
    };
  });

  ipcMain.handle("delete-profile", async (_event, profileId) => {
    const targetProfileId = String(profileId ?? "").trim();
    const state = loadProfilesSync();
    const target = state.profiles.find((profile) => profile.id === targetProfileId);

    if (!target) {
      throw new Error("Perfil invalido.");
    }

    if (state.profiles.length <= 1) {
      throw new Error("Nao e possivel excluir o unico perfil.");
    }

    state.profiles = state.profiles.filter((profile) => profile.id !== targetProfileId);
    const pendingDeleteIds = Array.isArray(state.pendingDeleteIds)
      ? state.pendingDeleteIds
      : [];
    const fallbackProfileId = state.profiles[0].id;
    const wasActive = state.activeProfileId === targetProfileId;
    if (wasActive) {
      state.activeProfileId = fallbackProfileId;
    }
    if (!pendingDeleteIds.includes(targetProfileId)) {
      pendingDeleteIds.push(targetProfileId);
    }
    state.pendingDeleteIds = pendingDeleteIds;
    saveProfilesSync(state);

    if (!wasActive) {
      try {
        deleteProfileDirectory(targetProfileId);
        state.pendingDeleteIds = state.pendingDeleteIds.filter((id) => id !== targetProfileId);
        saveProfilesSync(state);
      } catch {
        // Fica pendente para o proximo boot.
      }
    }

    if (wasActive) {
      app.relaunch();
      app.exit(0);
    }

    return true;
  });

  ipcMain.handle("switch-profile", async (_event, profileId) => {
    const nextProfileId = String(profileId ?? "").trim();
    const state = loadProfilesSync();
    if (!state.profiles.some((profile) => profile.id === nextProfileId)) {
      throw new Error("Perfil invalido.");
    }

    state.activeProfileId = nextProfileId;
    saveProfilesSync(state);
    if (mainWindow && !mainWindow.isDestroyed()) {
      await saveWindowState(mainWindow);
    }
    app.relaunch();
    app.exit(0);
    return true;
  });

  ipcMain.handle("restart-app", async () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      await saveWindowState(mainWindow);
    }
    app.relaunch();
    app.exit(0);
    return true;
  });

  ipcMain.handle("test", async () => {
    return "Resposta do Electron";
  });

  ipcMain.handle("count-items", async () => {
    const [items, effects] = await Promise.all([
      countItems(),
      countItemEffects(),
    ]);

    return {
      items,
      effects,
    };
  });

  ipcMain.handle("list-source-files", async () => {
    return await listSourceFiles();
  });

  ipcMain.handle("list-source-columns", async (_event, sourceFile) => {
    return await listSourceColumns(sourceFile);
  });

  ipcMain.handle("generate-grade1-weapon-socket-combines", async () => {
    return await generateGrade1WeaponSocketCombines();
  });

  ipcMain.handle("save-generated-weapon-socket-combines", async () => {
    const { combineRows, linkedRows } = await listGeneratedWeaponSocketCombineRows();
    if (combineRows.length === 0 || linkedRows.length === 0) {
      throw new Error("Gere as combinações antes de salvar no Excel.");
    }

    const combinePath = await resolveExcelPathForSource("CombineTable2.xlsx");
    const linkedPath = await resolveExcelPathForSource("LinkedCombines.xlsx");
    if (!combinePath) {
      throw new Error("CombineTable2.xlsx original nao encontrado.");
    }
    if (!linkedPath) {
      throw new Error("LinkedCombines.xlsx original nao encontrado.");
    }

    await writeGeneratedRowsToExcel(combinePath, "CombineTable2.xlsx", combineRows, {
      backupReason: "save-grade1-weapon-combines",
      fillEmptyWith: "",
      fillCombineMaterialPattern: true,
      fillCombineResultPattern: true,
      clearRowsAfterLast: true,
      freezeTopRowsWithExcel: true,
      columnCount: getExtraItemColumnCount(),
    });
    const linkedInputRows = linkedRows.filter((row) => String(row.code || "").startsWith("LL"));
    const linkedResultRows = linkedRows.filter((row) => String(row.code || "").startsWith("LR"));
    await writeGeneratedRowsToExcel(linkedPath, "LinkedCombines.xlsx", linkedInputRows, {
      backupReason: "save-grade1-linked-combines",
      sheetName: "LinkedStuff",
      fillEmptyWith: "-1",
      clearRowsAfterLast: true,
      placeByCodePrefix: "LLwgb",
      freezeTopRowsWithExcel: true,
      exactColumnCount: true,
      columnCount: 101,
    });
    await writeGeneratedRowsToExcel(linkedPath, "LinkedCombines.xlsx", linkedResultRows, {
      backupReason: "save-grade1-linked-combines-result",
      sheetName: "LinkedResult",
      fillEmptyWith: "-1",
      clearRowsAfterLast: true,
      placeByCodePrefix: "LRwgb",
      freezeTopRowsWithExcel: true,
      exactColumnCount: true,
      columnCount: 101,
    });

    await trackExcelSourcePath("CombineTable2.xlsx", combinePath);
    await trackExcelSourcePath("LinkedCombines.xlsx", linkedPath);

    return {
      combineRows: combineRows.length,
      linkedRows: linkedRows.length,
    };
  });

  ipcMain.handle("list-source-sheets", async (_event, sourceFile) => {
    const absolutePath = await resolveExcelPathForSource(String(sourceFile ?? ""));
    if (!absolutePath) {
      return [];
    }
    const workbook = XLSX.readFile(absolutePath, { bookSheets: true });
    return workbook.SheetNames ?? [];
  });

  ipcMain.handle("import-source-sheet", async (event, payload) => {
    const sourceFile = String(payload?.sourceFile ?? "");
    const sheetName = String(payload?.sheetName ?? "");
    if (!sourceFile || !sheetName) {
      throw new Error("Source e aba sao obrigatorios.");
    }

    const absolutePath = await resolveExcelPathForSource(sourceFile);
    if (!absolutePath) {
      throw new Error("Arquivo Excel original nao encontrado para este source.");
    }

    const normalized = stripSheetSuffix(sourceFile).replaceAll("\\", "/");
    const base = normalized.replace(/\.xlsx$/i, "");
    const targetSource = `${base}::${sheetName}.xlsx`;
    return await importExcelFile(absolutePath, targetSource, {
      event,
      fileIndex: 1,
      fileCount: 1,
      forcedSheetName: sheetName,
    });
  });

  ipcMain.handle("delete-source-file", async (_event, sourceFile) => {
    await clearItemsBySource(sourceFile);
  });

  ipcMain.handle("list-items", async (_event, options) => {
    return await listItems(options);
  });

  ipcMain.handle("list-item-column-values", async (_event, options) => {
    return await listItemColumnValues(options);
  });

  ipcMain.handle("list-effect-dictionaries", async () => {
    return await listEffectDictionaries();
  });

  ipcMain.handle("set-source-dictionary", async (_event, sourceFile, dictionaryKey) => {
    await setSourceDictionary(sourceFile, dictionaryKey);
  });

  ipcMain.handle("list-effect-dictionary", async (_event, options) => {
    return await listEffectDictionary(options);
  });

  ipcMain.handle("save-effect-dictionary-entry", async (_event, entry) => {
    return await saveEffectDictionaryEntry(entry);
  });

  ipcMain.handle("delete-effect-dictionary-entry", async (_event, id) => {
    await deleteEffectDictionaryEntry(id);
  });

  ipcMain.handle("scan-excel-directory", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory"],
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    const directoryPath = result.filePaths[0];
    const files = await findExcelFiles(directoryPath);

    return {
      directoryPath,
      files: files.map((filePath) => ({
        filePath,
        relativePath: path.relative(directoryPath, filePath),
      })),
    };
  });

  ipcMain.handle("import-boss-directory", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory"],
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    const directoryPath = result.filePaths[0];
    const files = await findBossTextFiles(directoryPath);
    const entries = [];

    for (const filePath of files) {
      const content = await fs.readFile(filePath, "utf8");
      const sourceFile = path.relative(directoryPath, filePath);

      for (const code of parseMonsterCodes(content)) {
        entries.push({
          code,
          sourceFile,
        });
      }
    }

    const summary = await replaceBossMonsters(entries);

    return {
      directoryPath,
      files: files.length,
      codes: entries.length,
      inserted: summary.inserted,
      totalBosses: await countBossMonsters(),
    };
  });

  ipcMain.handle("import-excel-files", async (event, files) => {
    const importedFiles = [];
    let totalInserted = 0;
    let totalEffectsInserted = 0;
    let totalSkippedRows = 0;

    for (let index = 0; index < files.length; index++) {
      const file = files[index];
      const result = await importExcelFile(file.filePath, file.sourceFile, {
        event,
        fileIndex: index + 1,
        fileCount: files.length,
      });
      importedFiles.push(result);
      totalInserted += result.inserted;
      totalEffectsInserted += result.effectsInserted;
      totalSkippedRows += result.skippedRows;
    }

    return {
      files: importedFiles,
      inserted: totalInserted,
      effectsInserted: totalEffectsInserted,
      skippedRows: totalSkippedRows,
    };
  });

  ipcMain.handle("save-excel-watch-state", async (_event, payload) => {
    const directoryPath = String(payload?.directoryPath ?? "");
    const files = Array.isArray(payload?.files) ? payload.files : [];
    const states = [];

    for (const file of files) {
      try {
        const stat = await fs.stat(file.filePath);
        states.push({
          sourceFile: file.sourceFile,
          absolutePath: file.filePath,
          lastMtimeMs: Math.trunc(stat.mtimeMs),
        });
      } catch {
        // Ignora arquivos que nao puderam ser lidos.
      }
    }

    await replaceExcelFileState(states);
    await setAppSetting("excel_watch_directory", directoryPath);
  });

  ipcMain.handle("check-excel-updates", async () => {
    const watchDirectory = await getAppSetting("excel_watch_directory");
    const fileStates = await listExcelFileState();
    const outdatedFiles = [];
    const missingFiles = [];

    for (const fileState of fileStates) {
      try {
        const stat = await fs.stat(fileState.absolutePath);
        const currentMtimeMs = Math.trunc(stat.mtimeMs);

        if (currentMtimeMs > Number(fileState.lastMtimeMs || 0)) {
          outdatedFiles.push({
            sourceFile: fileState.sourceFile,
            absolutePath: fileState.absolutePath,
            previousMtimeMs: fileState.lastMtimeMs,
            currentMtimeMs,
          });
        }
      } catch {
        missingFiles.push({
          sourceFile: fileState.sourceFile,
          absolutePath: fileState.absolutePath,
        });
      }
    }

    return {
      watchDirectory,
      trackedFiles: fileStates.length,
      outdatedFiles,
      missingFiles,
    };
  });

  ipcMain.handle("list-rf-icon-sheets", async () => {
    const iconsDir = path.join(process.cwd(), "public", "rf-icons");
    const filesInDir = await safeReadDir(iconsDir);
    if (filesInDir.some((name) => /\.dds$/i.test(name)) && !filesInDir.some((name) => /\.png$/i.test(name))) {
      convertDdsToPngBatch(iconsDir, filesInDir.filter((name) => /\.dds$/i.test(name)));
    }
    const result = [];
    const files = await safeReadDir(iconsDir);
    for (const fileName of files) {
      if (!/\.dds$/i.test(fileName)) {
        continue;
      }
      const fullPath = path.join(iconsDir, fileName);
      try {
        const fd = await fs.open(fullPath, "r");
        const header = Buffer.alloc(128);
        await fd.read(header, 0, 128, 0);
        await fd.close();
        if (header.toString("ascii", 0, 4) !== "DDS ") {
          continue;
        }
        const height = header.readUInt32LE(12);
        const width = header.readUInt32LE(16);
        result.push({
          fileName,
          width,
          height,
          cols: Math.max(1, Math.floor(width / 64)),
          rows: Math.max(1, Math.floor(height / 64)),
        });
      } catch {
        // ignora arquivos invalidos
      }
    }
    return result;
  });

  ipcMain.handle("reset-excel-updates-baseline", async () => {
    const fileStates = await listExcelFileState();
    const nextStates = [];
    for (const fileState of fileStates) {
      try {
        const stat = await fs.stat(fileState.absolutePath);
        nextStates.push({
          sourceFile: fileState.sourceFile,
          absolutePath: fileState.absolutePath,
          lastMtimeMs: Math.trunc(stat.mtimeMs),
        });
      } catch {
        // ignora ausentes
      }
    }
    await replaceExcelFileState(nextStates);
    return { reset: nextStates.length };
  });

  ipcMain.handle("list-source-backups", async (_event, sourceFile) => {
    return await listBackupsForSource(sourceFile);
  });

  ipcMain.handle("restore-source-backup", async (_event, payload) => {
    return await restoreBackupForSource(payload?.sourceFile, payload?.backupName);
  });

  ipcMain.handle("save-itemlooting-edits", async (_event, payload) => {
    const sourceFile = String(payload?.sourceFile ?? "");
    const edits = Array.isArray(payload?.edits) ? payload.edits : [];

    if (!sourceFile || edits.length === 0) {
      return { saved: 0 };
    }

    const absolutePath = await resolveExcelPathForSource(sourceFile);

    if (!absolutePath) {
      throw new Error("Arquivo Excel original nao encontrado para este source.");
    }

    const itemIds = edits.map((edit) => edit.itemId);
    const rows = await getItemsForEdit(sourceFile, itemIds);
    const rowById = new Map(rows.map((row) => [row.id, row]));
    await createFileBackup(absolutePath, "save-itemlooting-edits");
    const workbook = XLSX.readFile(absolutePath);
    const preferredSheet = extractSheetNameFromSource(sourceFile);
    const sheetName =
      (preferredSheet && workbook.SheetNames.includes(preferredSheet)
        ? preferredSheet
        : workbook.SheetNames[0]) || "";
    const worksheet = workbook.Sheets[sheetName];
    let saved = 0;

    for (const edit of edits) {
      const row = rowById.get(Number(edit.itemId));

      if (!row || !row.excelRow) {
        continue;
      }

      const columnIndex = getEditableColumnIndex(edit.columnKey);

      if (columnIndex === null) {
        continue;
      }

      const address = XLSX.utils.encode_cell({
        r: Number(row.excelRow) - 1,
        c: columnIndex,
      });
      const nextValue = String(edit.value ?? "");
      const numericValue = Number(nextValue.replace(",", "."));
      const isNumber = nextValue.trim() !== "" && Number.isFinite(numericValue);

      worksheet[address] = {
        t: isNumber ? "n" : "s",
        v: isNumber ? numericValue : nextValue,
        s: {
          fill: {
            patternType: "solid",
            fgColor: {
              rgb: "FFFDE68A",
            },
          },
        },
      };
      saved++;
    }

    // BoxItemOut rows must keep full width filled (avoid trailing empty cells).
    if (/boxitemout/i.test(String(sheetName || ""))) {
      const range = XLSX.utils.decode_range(worksheet["!ref"] || "A1:A1");
      const targetRows = new Set(
        edits
          .map((edit) => rowById.get(Number(edit.itemId)))
          .filter((row) => row && Number(row.excelRow) > 0)
          .map((row) => Number(row.excelRow) - 1)
      );
      for (const rowIndex of targetRows) {
        for (let columnIndex = 1; columnIndex <= range.e.c; columnIndex += 1) {
          const address = XLSX.utils.encode_cell({ r: rowIndex, c: columnIndex });
          const current = worksheet[address];
          const currentValue = current?.v;
          const isEmpty =
            currentValue === undefined ||
            currentValue === null ||
            String(currentValue).trim() === "";
          if (!isEmpty) {
            continue;
          }
          worksheet[address] = { t: "n", v: -1 };
        }
      }
    }

    XLSX.writeFile(workbook, absolutePath);
    await trackExcelSourcePath(sourceFile, absolutePath);
    return { saved };
  });

  ipcMain.handle("upsert-boxitemout-box", async (_event, payload) => {
    const sourceFile = String(payload?.sourceFile ?? "");
    const sheetName = String(payload?.sheetName ?? "BoxItemOut");
    const boxCode = String(payload?.boxCode ?? "").trim();
    const rewards = Array.isArray(payload?.rewards) ? payload.rewards : [];

    if (!sourceFile || !boxCode) {
      throw new Error("Source e codigo da box sao obrigatorios.");
    }

    const absolutePath = await resolveExcelPathForSource(sourceFile);
    if (!absolutePath) {
      throw new Error("Arquivo Excel original nao encontrado para este source.");
    }

    await createFileBackup(absolutePath, "upsert-boxitemout-box");
    const workbook = XLSX.readFile(absolutePath, {
      cellStyles: true,
      cellNF: true,
      cellDates: true,
      bookVBA: true,
    });
    const targetSheetName =
      (sheetName && workbook.SheetNames.includes(sheetName) ? sheetName : workbook.SheetNames[0]) || "";
    const worksheet = workbook.Sheets[targetSheetName];
    const rows = XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: "" });
    const headerIndex = findHeaderRowIndex(rows, sourceFile);
    const dataStart = headerIndex + 1;

    const normalizedRewards = rewards
      .map((reward) => ({
        itemCode: String(reward?.itemCode ?? "").trim(),
        quantity: Math.max(0, Math.trunc(Number(reward?.quantity ?? 0) || 0)),
        chance: Math.max(0, Math.trunc(Number(reward?.chance ?? 0) || 0)),
      }))
      .filter((reward) => reward.itemCode);

    const currentRange = XLSX.utils.decode_range(worksheet["!ref"] || "A1:A1");
    const minColumns = 64; // legacy safe floor
    const targetColumns = Math.max(minColumns, currentRange.e.c + 1, 184);
    const row = Array.from({ length: targetColumns }, () => "-1");
    row[0] = boxCode;
    for (let index = 0; index < normalizedRewards.length; index += 1) {
      const base = 1 + index * 3;
      if (base + 2 >= row.length) {
        break;
      }
      row[base] = normalizedRewards[index].itemCode;
      row[base + 1] = String(normalizedRewards[index].quantity);
      row[base + 2] = String(normalizedRewards[index].chance);
    }

    let targetIndex = -1;
    for (let index = dataStart; index < rows.length; index += 1) {
      if (String(rows[index]?.[0] ?? "").trim() === boxCode) {
        targetIndex = index;
        break;
      }
    }

    const isInsert = targetIndex === -1;
    if (isInsert) {
      targetIndex = rows.length;
    }

    for (let columnIndex = 0; columnIndex < row.length; columnIndex += 1) {
      const address = XLSX.utils.encode_cell({
        r: targetIndex,
        c: columnIndex,
      });
      const value = row[columnIndex];
      const numericValue = Number(value);
      const isNumber = value !== "" && Number.isFinite(numericValue) && /^-?\d+(\.\d+)?$/.test(String(value));
      worksheet[address] = {
        t: isNumber ? "n" : "s",
        v: isNumber ? numericValue : String(value),
      };
    }

    const range = XLSX.utils.decode_range(worksheet["!ref"] || "A1:A1");
    if (targetIndex > range.e.r) {
      range.e.r = targetIndex;
    }
    if (row.length - 1 > range.e.c) {
      range.e.c = row.length - 1;
    }
    worksheet["!ref"] = XLSX.utils.encode_range(range);

    XLSX.writeFile(workbook, absolutePath);
    await trackExcelSourcePath(sourceFile, absolutePath);

    await importExcelFile(
      absolutePath,
      sourceFile,
      {
        fileIndex: 1,
        fileCount: 1,
        forcedSheetName: targetSheetName,
      }
    );

    return {
      row: targetIndex + 1,
      inserted: isInsert,
      rewards: normalizedRewards.length,
    };
  });

  ipcMain.handle("import-items", async (event) => {
    const result = await dialog.showOpenDialog({
      properties: ["openFile"],
      filters: [
        {
          name: "Excel",
          extensions: ["xlsx"],
        },
      ],
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    const filePath = result.filePaths[0];
    const parentFolder = path.basename(path.dirname(filePath));
    const fileName = path.basename(filePath);
    const sourceFile = /^\d+_/.test(parentFolder)
      ? path.join(parentFolder, fileName)
      : fileName;

    const forcedSheetName = /boxitem/i.test(sourceFile) ? "BoxItemOut" : undefined;

    return await importExcelFile(filePath, sourceFile, {
      event,
      fileIndex: 1,
      fileCount: 1,
      forcedSheetName,
    });
  });

  ipcMain.handle("import-csv", async (event) => {
    const result = await dialog.showOpenDialog({
      properties: ["openFile"],
      filters: [{ name: "CSV", extensions: ["csv"] }],
    });

    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }

    const filePath = result.filePaths[0];
    const fileName = path.basename(filePath);
    const sourceFile = fileName;

    return await importExcelFile(filePath, sourceFile, {
      event,
      fileIndex: 1,
      fileCount: 1,
      forceHeaderRowIndex: 0,
    });
  });

  ipcMain.handle("reimport-source-file", async (event, sourceFile) => {
    const source = String(sourceFile ?? "").trim();
    if (!source) {
      throw new Error("Nenhum arquivo selecionado para reimportar.");
    }

    let filePath = await resolveExcelPathForSource(source);
    if (!filePath) {
      const result = await dialog.showOpenDialog({
        properties: ["openFile"],
        filters: [{ name: "Excel", extensions: ["xlsx"] }],
      });

      if (result.canceled || result.filePaths.length === 0) {
        return null;
      }

      filePath = result.filePaths[0];
    }

    const forcedSheetName = extractSheetNameFromSource(source) || (/boxitem/i.test(source) ? "BoxItemOut" : undefined);
    return await importExcelFile(filePath, source, {
      event,
      fileIndex: 1,
      fileCount: 1,
      forcedSheetName,
    });
  });

  lastWindowState = await loadWindowState();
  createWindow();
});
}

function convertDdsToPngBatch(iconsDir, ddsFiles) {
  // Requer texconv no PATH. Se nao existir, segue sem quebrar.
  const check = spawnSync("texconv", ["-h"], { encoding: "utf8", windowsHide: true });
  if (check.error) {
    return;
  }
  for (const ddsFile of ddsFiles) {
    const sourcePath = path.join(iconsDir, ddsFile);
    const pngName = ddsFile.replace(/\.dds$/i, ".png");
    const pngPath = path.join(iconsDir, pngName);
    if (fsSync.existsSync(pngPath)) {
      continue;
    }
    spawnSync(
      "texconv",
      ["-y", "-ft", "png", "-o", iconsDir, sourcePath],
      { encoding: "utf8", windowsHide: true }
    );
  }
}

async function safeReadDir(dir) {
  try {
    return await fs.readdir(dir);
  } catch {
    return [];
  }
}

function stripSheetSuffix(sourceFile) {
  const normalized = String(sourceFile ?? "");
  return normalized.replace(/::[^/\\]+\.xlsx$/i, ".xlsx");
}

function extractSheetNameFromSource(sourceFile) {
  const normalized = String(sourceFile ?? "");
  const match = normalized.match(/::([^/\\]+)\.xlsx$/i);
  return match ? match[1] : "";
}

async function resolveExcelPathForSource(sourceFile) {
  const source = String(sourceFile ?? "").trim();
  if (!source) {
    return null;
  }

  const direct = await getExcelFilePath(source);
  if (direct) {
    return direct;
  }

  const stripped = stripSheetSuffix(source);
  if (stripped !== source) {
    return await getExcelFilePath(stripped);
  }

  const baseName = path.basename(source);
  if (/^linkedcombines\.xlsx$/i.test(baseName)) {
    const combinePath = await getExcelFilePath("CombineTable2.xlsx") || await getExcelFilePath("CombineTable.xlsx");
    if (combinePath) {
      const siblingPath = path.join(path.dirname(combinePath), baseName);
      const exists = await fs.access(siblingPath).then(() => true).catch(() => false);
      if (exists) {
        await trackExcelSourcePath(source, siblingPath);
        return siblingPath;
      }
    }
  }

  return null;
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

async function findExcelFiles(directoryPath) {
  const entries = await fs.readdir(directoryPath, {
    withFileTypes: true,
  });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directoryPath, entry.name);

    if (entry.isDirectory()) {
      files.push(...await findExcelFiles(entryPath));
      continue;
    }

    if (entry.isFile() && entry.name.toLowerCase().endsWith(".xlsx")) {
      files.push(entryPath);
    }
  }

  return files.sort((first, second) => first.localeCompare(second));
}

async function findBossTextFiles(directoryPath) {
  const entries = await fs.readdir(directoryPath, {
    withFileTypes: true,
  });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directoryPath, entry.name);

    if (entry.isDirectory()) {
      files.push(...await findBossTextFiles(entryPath));
      continue;
    }

    if (entry.isFile() && /\.(txt|ini)$/i.test(entry.name)) {
      files.push(entryPath);
    }
  }

  return files.sort((first, second) => first.localeCompare(second));
}

function parseMonsterCodes(content) {
  const codes = new Set();
  const matches = content.match(/[A-Za-z0-9_-]+/g) ?? [];

  for (const match of matches) {
    const code = match.trim();

    if (code) {
      codes.add(code);
    }
  }

  return [...codes];
}

async function importExcelFile(filePath, sourceFile, progressContext = {}) {
  emitImportProgress(progressContext, {
    stage: "reading",
    sourceFile,
    inserted: 0,
    total: 0,
    effectsInserted: 0,
  });

  const isCombineImport = isCombineSourceFile(sourceFile);
  let firstSheetName = "";
  let rows = [];
  let importColumnLimit = getImportColumnLimit(sourceFile);

  if (isCombineImport) {
    const limited = await readLimitedXlsxRows(filePath, sourceFile, importColumnLimit);
    firstSheetName = limited.sheetName;
    rows = limited.rows;
  } else {
    const workbookInfo = XLSX.readFile(filePath, { bookSheets: true });
    const requestedSheetName = String(progressContext.forcedSheetName || "").trim();
    const normalizedRequested = requestedSheetName.toLowerCase();
    const sourceBaseName = path.basename(String(sourceFile || ""), path.extname(String(sourceFile || ""))).toLowerCase();
    firstSheetName =
      (requestedSheetName &&
        (workbookInfo.SheetNames.find((sheet) => String(sheet).trim() === requestedSheetName) ||
          workbookInfo.SheetNames.find(
            (sheet) => String(sheet).trim().toLowerCase() === normalizedRequested
          ))) ||
      workbookInfo.SheetNames.find((sheet) => String(sheet).trim().toLowerCase() === sourceBaseName) ||
      workbookInfo.SheetNames[0];
    importColumnLimit = getImportColumnLimit(sourceFile, firstSheetName);
    const workbook = XLSX.readFile(filePath, { sheets: firstSheetName });
    const worksheet = workbook.Sheets[firstSheetName];
    const limitedRange = getLimitedWorksheetRange(worksheet, importColumnLimit);
    rows = XLSX.utils.sheet_to_json(worksheet, {
      header: 1,
      defval: "",
      range: limitedRange,
    });
  }
  const isBoxItemOutSheet = /boxitemout/i.test(String(firstSheetName || ""));

  const headerIndex =
    Number.isInteger(progressContext.forceHeaderRowIndex)
      ? progressContext.forceHeaderRowIndex
      : findHeaderRowIndex(rows, sourceFile);
  const headerRow = rows[headerIndex] ?? [];
  const headers = buildHeaderMap(headerRow);

  const parsedItems = [];
  let skippedRows = 0;
  const totalRows = Math.max(rows.length - headerIndex - 1, 0);

  emitImportProgress(progressContext, {
    stage: "parsing",
    sourceFile,
    inserted: 0,
    total: totalRows,
    effectsInserted: 0,
  });

  for (let i = headerIndex + 1; i < rows.length; i++) {
    const row = rows[i];
    const isBoxItem = /boxitem/i.test(sourceFile);
    const isCombineTable = isCombineTableSourceFile(sourceFile);
    const isLinkedCombines = isLinkedCombinesSourceFile(sourceFile);
    const rawColumns = readFirstColumns(row, importColumnLimit);
    const code = readCell(row, headers, "Code") || rawColumns[0] || `row-${i + 1}`;

    if (isBoxItemOutSheet && rawColumns.every((value) => !String(value ?? "").trim())) {
      break;
    }

    if (
      (isCombineTable || isLinkedCombines) &&
      parsedItems.length > 0 &&
      rawColumns.every((value) => !String(value ?? "").trim())
    ) {
      break;
    }

    if (!row || rawColumns.every((value) => !value)) {
      skippedRows++;
      continue;
    }

    if (isBoxItemOutSheet && !String(rawColumns[0] ?? "").trim()) {
      skippedRows++;
      continue;
    }

    if (isBoxItem && !String(rawColumns[0] ?? "").trim()) {
      skippedRows++;
      continue;
    }

    parsedItems.push({
      excelRow: i + 1,
      code,
      name: readCell(row, headers, "Name") || rawColumns[1] || "",
      model: readCell(row, headers, "Model") || rawColumns[2] || "",
      icon: readCell(row, headers, "Icon") || rawColumns[3] || "",
      kindClt: readCell(row, headers, "KindClt") || rawColumns[4] || "",
      grade: readCell(row, headers, "Grade") || rawColumns[5] || "",
      type: readCell(row, headers, "Type") || rawColumns[6] || "",
      subtype: readCell(row, headers, "SubType") || rawColumns[7] || "",
      levelLim: readCell(row, headers, "LevelLim") || rawColumns[8] || "",
      money: readCell(row, headers, "Money") || rawColumns[9] || "",
      upgrade: readCell(row, headers, "Upgrade") || rawColumns[10] || "",
      tooltip: readCell(row, headers, "ToolTip") || rawColumns[11] || "",
      ...Object.fromEntries(
        rawColumns.map((value, index) => [`extra${index + 1}`, value])
      ),
      effects: readEffects(row, headers),
    });

    if (parsedItems.length === 1 || parsedItems.length % 1000 === 0) {
      emitImportProgress(progressContext, {
        stage: "parsing",
        sourceFile,
        inserted: parsedItems.length,
        total: totalRows,
        effectsInserted: 0,
      });
    }
  }

  emitImportProgress(progressContext, {
    stage: "saving",
    sourceFile,
    inserted: 0,
    total: parsedItems.length,
    effectsInserted: 0,
  });

  if (parsedItems.length === 0) {
    throw new Error(
      `Nenhuma linha importada de ${sourceFile}. Confira se a aba correta esta selecionada no Excel.`
    );
  }

  const importResult = await replaceItemsFromSource(sourceFile, parsedItems, {
    onProgress: (progress) => {
      emitImportProgress(progressContext, {
        stage: "saving",
        sourceFile,
        ...progress,
      });
    },
  });

  await replaceSourceColumns(sourceFile, buildSourceColumns(headerRow, sourceFile));
  await trackExcelSourcePath(sourceFile, filePath);

  emitImportProgress(progressContext, {
    stage: "done",
    sourceFile,
    inserted: importResult.inserted,
    total: importResult.inserted,
    effectsInserted: importResult.effectsInserted,
  });

  return {
    fileName: sourceFile,
    inserted: importResult.inserted,
    effectsInserted: importResult.effectsInserted,
    skippedRows,
  };
}

async function trackExcelSourcePath(sourceFile, absolutePath) {
  const source = String(sourceFile ?? "").trim();
  const file = String(absolutePath ?? "").trim();
  if (!source || !file) {
    return;
  }

  const current = await listExcelFileState();
  const bySource = new Map(current.map((entry) => [String(entry.sourceFile), entry]));
  let mtime = Date.now();
  try {
    const stat = await fs.stat(file);
    mtime = Math.trunc(stat.mtimeMs);
  } catch {
    // Mantem fallback com timestamp atual.
  }

  bySource.set(source, {
    sourceFile: source,
    absolutePath: file,
    lastMtimeMs: mtime,
  });

  const stripped = stripSheetSuffix(source);
  if (stripped && stripped !== source) {
    bySource.set(stripped, {
      sourceFile: stripped,
      absolutePath: file,
      lastMtimeMs: mtime,
    });
  }

  await replaceExcelFileState([...bySource.values()]);
}

function getEditableColumnIndex(columnKey) {
  const match = /^extra(\d+)$/i.exec(String(columnKey ?? ""));

  if (!match) {
    return null;
  }

  const index = Number(match[1]) - 1;
  return Number.isInteger(index) && index >= 0 && index < 15 ? index : null;
}

function emitImportProgress(context, progress) {
  if (!context.event) {
    return;
  }

  context.event.sender.send("import-progress", {
    fileIndex: context.fileIndex ?? 1,
    fileCount: context.fileCount ?? 1,
    ...progress,
  });
}

function findHeaderRowIndex(rows, sourceFile = "") {
  if (hasHeaderValues(rows[1])) {
    return 1;
  }

  let bestIndex = 0;
  let bestScore = -1;

  for (let index = 0; index < Math.min(rows.length, 12); index++) {
    const headers = buildHeaderMap(rows[index] ?? []);
    let score = 0;

    for (const field of [
      "Code",
      "Name",
      "Model",
      "Icon",
      "KindClt",
      "Grade",
      "Type",
      "SubType",
      "LevelLim",
      "Money",
      "Upgrade",
      "ToolTip",
    ]) {
      if (headers.has(normalizeHeader(field))) {
        score++;
      }
    }

    if (headers.has(normalizeHeader("Code"))) {
      score += 3;
    }

    if (headers.has(normalizeHeader("Name"))) {
      score += 3;
    }

    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  }

  return bestIndex;
}

function hasHeaderValues(row) {
  return Array.isArray(row) && row.some((value) => String(value ?? "").trim());
}

function buildHeaderMap(headerRow) {
  const headers = new Map();

  for (let index = 0; index < headerRow.length; index++) {
    const header = normalizeHeader(headerRow[index]);

    if (header) {
      headers.set(header, index);
    }
  }

  for (const [field, aliases] of Object.entries(headerAliases)) {
    const normalizedField = normalizeHeader(field);

    if (headers.has(normalizedField)) {
      continue;
    }

    for (const alias of aliases) {
      const normalizedAlias = normalizeHeader(alias);

      if (headers.has(normalizedAlias)) {
        headers.set(normalizedField, headers.get(normalizedAlias));
        break;
      }
    }
  }

  return headers;
}

const headerAliases = {
  Code: ["ItemCode", "Item Code", "Code"],
  Name: ["ItemName", "Item Name", "Name"],
  Model: ["ItemModel", "Item Model", "Model"],
  Icon: ["ItemIcon", "Item Icon", "Icon", "IconID", "Icon Id", "Icon_Id"],
  KindClt: ["ItemKindClt", "KindClt", "Kind", "ItemKind"],
  Grade: ["ItemGrade", "Item Grade", "Grade"],
  Type: ["ItemType", "Item Type", "Type"],
  SubType: ["ItemSubType", "Item SubType", "Sub Type", "SubType"],
  LevelLim: ["ItemLevelLim", "LevelLim", "Level Limit", "LevelLimit", "LevelLimitation"],
  Money: ["ItemMoney", "Money", "Price", "SellPrice"],
  Upgrade: ["ItemUpgrade", "Upgrade"],
  ToolTip: ["ItemToolTip", "ToolTip", "Tooltip", "Tip"],
  Eff1Code: ["Eff1Code", "EffCode1", "EffCod", "Effect1Code", "EffectCode1"],
  Eff1Unit: ["Eff1Unit", "EffUnit1", "Effect1Unit", "EffectUnit1"],
  Eff2Code: ["Eff2Code", "EffCode2", "EffCod2", "Effect2Code", "EffectCode2"],
  Eff2Unit: ["Eff2Unit", "EffUnit2", "Effect2Unit", "EffectUnit2"],
  Eff3Code: ["Eff3Code", "EffCode3", "EffCod3", "Effect3Code", "EffectCode3"],
  Eff3Unit: ["Eff3Unit", "EffUnit3", "Effect3Unit", "EffectUnit3"],
  Eff4Code: ["Eff4Code", "EffCode4", "EffCod4", "Effect4Code", "EffectCode4"],
  Eff4Unit: ["Eff4Unit", "EffUnit4", "Effect4Unit", "EffectUnit4"],
};

function readCell(row, headers, headerName) {
  const index = headers.get(normalizeHeader(headerName));

  if (index === undefined) {
    return "";
  }

  return String(row?.[index] ?? "").trim();
}

function readFirstColumns(row, count) {
  return Array.from({ length: count }, (_value, index) =>
    String(row?.[index] ?? "").trim()
  );
}

function getImportColumnLimit(sourceFile, sheetName = "") {
  const source = `${getSourceBaseFileName(sourceFile)} ${sheetName || ""}`;
  if (/boxitemout/i.test(source)) return 184;
  if (/boxitem/i.test(source)) return 64;
  if (isLinkedCombinesSourceFile(sourceFile)) return 80;
  if (isCombineTableSourceFile(sourceFile)) return 160;
  if (/item\.xlsx\b/i.test(source)) return 80;
  return 15;
}

function getSourceBaseFileName(sourceFile) {
  return path.basename(String(sourceFile || "").replace(/\\/g, "/"));
}

function isCombineTableSourceFile(sourceFile) {
  return /^combinetable2?\.xlsx$/i.test(getSourceBaseFileName(sourceFile));
}

function isLinkedCombinesSourceFile(sourceFile) {
  return /^linkedcombines?\.xlsx$/i.test(getSourceBaseFileName(sourceFile));
}

function isCombineSourceFile(sourceFile) {
  return isCombineTableSourceFile(sourceFile) || isLinkedCombinesSourceFile(sourceFile);
}

async function readLimitedXlsxRows(filePath, sourceFile, columnLimit) {
  const entries = await readXlsxEntries(filePath, [
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/sharedStrings.xml",
  ]);
  const workbookXml = entries.get("xl/workbook.xml") || "";
  const relsXml = entries.get("xl/_rels/workbook.xml.rels") || "";
  const sharedStrings = parseSharedStrings(entries.get("xl/sharedStrings.xml") || "");
  const sheets = parseWorkbookSheets(workbookXml, relsXml);
  const sourceBaseName = path.basename(String(sourceFile || ""), path.extname(String(sourceFile || ""))).toLowerCase();
  const selectedSheet =
    sheets.find((sheet) => sheet.name.trim().toLowerCase() === sourceBaseName) ||
    sheets[0];

  if (!selectedSheet?.path) {
    return { sheetName: selectedSheet?.name || "", rows: [] };
  }

  const sheetEntries = await readXlsxEntries(filePath, [selectedSheet.path]);
  const sheetXml = sheetEntries.get(selectedSheet.path) || "";
  return {
    sheetName: selectedSheet.name,
    rows: parseWorksheetRows(sheetXml, sharedStrings, columnLimit),
  };
}

function readXlsxEntries(filePath, wantedEntries) {
  const wanted = new Set(wantedEntries);
  const found = new Map();

  return new Promise((resolve, reject) => {
    yauzl.open(filePath, { lazyEntries: true }, (openError, zipfile) => {
      if (openError) {
        reject(openError);
        return;
      }

      zipfile.readEntry();
      zipfile.on("entry", (entry) => {
        const name = entry.fileName.replace(/\\/g, "/");
        if (!wanted.has(name)) {
          zipfile.readEntry();
          return;
        }

        zipfile.openReadStream(entry, (streamError, stream) => {
          if (streamError) {
            zipfile.close();
            reject(streamError);
            return;
          }

          const chunks = [];
          stream.on("data", (chunk) => chunks.push(chunk));
          stream.on("end", () => {
            found.set(name, Buffer.concat(chunks).toString("utf8"));
            if (found.size >= wanted.size) {
              zipfile.close();
              resolve(found);
              return;
            }
            zipfile.readEntry();
          });
          stream.on("error", reject);
        });
      });
      zipfile.on("end", () => resolve(found));
      zipfile.on("error", reject);
    });
  });
}

function parseWorkbookSheets(workbookXml, relsXml) {
  const relTargets = new Map();
  const relPattern = /<Relationship\b[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"[^>]*>/g;
  for (const match of relsXml.matchAll(relPattern)) {
    const target = match[2].replace(/^\/+/, "");
    relTargets.set(match[1], target.startsWith("xl/") ? target : `xl/${target}`);
  }

  const sheets = [];
  const sheetPattern = /<sheet\b[^>]*name="([^"]+)"[^>]*(?:r:id|id)="([^"]+)"[^>]*>/g;
  for (const match of workbookXml.matchAll(sheetPattern)) {
    sheets.push({
      name: decodeXml(match[1]),
      path: relTargets.get(match[2]) || "",
    });
  }
  return sheets;
}

function parseSharedStrings(sharedStringsXml) {
  const strings = [];
  const siPattern = /<si\b[^>]*>([\s\S]*?)<\/si>/g;
  for (const match of sharedStringsXml.matchAll(siPattern)) {
    const text = [...match[1].matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g)]
      .map((textMatch) => decodeXml(textMatch[1]))
      .join("");
    strings.push(text);
  }
  return strings;
}

function parseWorksheetRows(sheetXml, sharedStrings, columnLimit) {
  const rows = [];
  const rowPattern = /<row\b[^>]*r="(\d+)"[^>]*>([\s\S]*?)<\/row>/g;
  for (const rowMatch of sheetXml.matchAll(rowPattern)) {
    const rowNumber = Number(rowMatch[1]);
    const row = Array.from({ length: columnLimit }, () => "");
    const cellPattern = /<c\b([^>]*)>([\s\S]*?)<\/c>/g;
    for (const cellMatch of rowMatch[2].matchAll(cellPattern)) {
      const attrs = cellMatch[1];
      const ref = attrs.match(/\br="([A-Z]+)\d+"/)?.[1] || "";
      const columnIndex = columnLettersToIndex(ref);
      if (columnIndex < 0 || columnIndex >= columnLimit) {
        continue;
      }

      const type = attrs.match(/\bt="([^"]+)"/)?.[1] || "";
      const body = cellMatch[2];
      const rawValue = body.match(/<v>([\s\S]*?)<\/v>/)?.[1] ?? "";
      if (type === "s") {
        row[columnIndex] = sharedStrings[Number(rawValue)] ?? "";
      } else if (type === "inlineStr") {
        row[columnIndex] = decodeXml(
          [...body.matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g)]
            .map((textMatch) => textMatch[1])
            .join("")
        );
      } else {
        row[columnIndex] = decodeXml(rawValue);
      }
    }
    rows[rowNumber - 1] = row;
  }
  return Array.from({ length: rows.length }, (_value, index) =>
    rows[index] || Array.from({ length: columnLimit }, () => "")
  );
}

function columnLettersToIndex(letters) {
  let index = 0;
  for (const char of String(letters || "")) {
    index = index * 26 + (char.charCodeAt(0) - 64);
  }
  return index - 1;
}

function decodeXml(value) {
  return String(value || "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

function getBestImportSheetName(filePath, sheetNames, preferredSheetName, sourceFile, columnLimit) {
  const isCombine = /combinetable|linkedcombines?/i.test(sourceFile);
  if (!isCombine || sheetNames.length <= 1) {
    return preferredSheetName;
  }

  const candidates = [
    preferredSheetName,
    ...sheetNames.filter((sheet) => sheet !== preferredSheetName),
  ];

  let bestSheet = preferredSheetName;
  let bestScore = -1;

  for (const sheetName of candidates) {
    try {
      const workbook = XLSX.readFile(filePath, { sheets: sheetName });
      const worksheet = workbook.Sheets[sheetName];
      const range = getLimitedWorksheetRange(worksheet, columnLimit);
      const rows = XLSX.utils.sheet_to_json(worksheet, {
        header: 1,
        defval: "",
        range,
      });
      const headerIndex = findHeaderRowIndex(rows, sourceFile);
      const score = rows
        .slice(headerIndex + 1, Math.min(rows.length, headerIndex + 250))
        .reduce((total, row) => {
          const rawColumns = readFirstColumns(row, columnLimit);
          const hasCode = String(rawColumns[0] ?? "").trim();
          const hasName = String(rawColumns[4] ?? "").trim();
          return total + (hasCode || hasName ? 1 : 0);
        }, 0);

      if (score > bestScore) {
        bestScore = score;
        bestSheet = sheetName;
      }
    } catch {
      continue;
    }
  }

  return bestSheet;
}

function getLimitedWorksheetRange(worksheet, columnLimit) {
  const ref = worksheet?.["!ref"];
  if (!ref) {
    return undefined;
  }

  const range = XLSX.utils.decode_range(ref);
  range.e.c = Math.min(range.e.c, Math.max(columnLimit - 1, 0));
  return XLSX.utils.encode_range(range);
}

function buildSourceColumns(headerRow, sourceFile) {
  const columns = [];
  const isLooting = /itemlooting/i.test(sourceFile);
  const isCombineTable = /combinetable/i.test(sourceFile);
  const isLinkedCombines = /linkedcombines?/i.test(sourceFile);
  const headers = buildHeaderMap(headerRow ?? []);

  if (!isLooting) {
    const standardColumns = [
      ["code", "Code"],
      ["name", "Name"],
      ["model", "Model"],
      ["icon", "Icon"],
      ["kindClt", "KindClt"],
      ["grade", "Grade"],
      ["type", "Type"],
      ["subtype", "SubType"],
      ["levelLim", "LevelLim"],
      ["money", "Money"],
      ["upgrade", "Upgrade"],
      ["tooltip", "ToolTip"],
      ["effect1", "Eff1Code"],
      ["effect2", "Eff2Code"],
      ["effect3", "Eff3Code"],
      ["effect4", "Eff4Code"],
    ];
    const mapped = standardColumns
      .map(([key, headerKey]) => {
        const index = headers.get(normalizeHeader(headerKey));
        const label = index !== undefined ? String(headerRow?.[index] ?? "").trim() : "";
        return {
          key,
          index: index ?? Number.MAX_SAFE_INTEGER,
          label,
        };
      })
      .filter((entry) => entry.label && Number.isFinite(entry.index))
      .sort((a, b) => a.index - b.index);

    const usedIndexes = new Set();
    for (const entry of mapped) {
      usedIndexes.add(entry.index);
      columns.push({
        key: entry.key,
        label: entry.label,
        ordinal: entry.index + 1,
      });
    }

    // Mantem colunas extras do cabecalho real (linha 2), sem duplicar as ja mapeadas.
    const extraColumnCount = getImportColumnLimit(sourceFile);
    for (let index = 0; index < extraColumnCount; index++) {
      const label = String(headerRow?.[index] ?? "").trim();
      if (!label || usedIndexes.has(index)) {
        continue;
      }
      columns.push({
        key: `extra${index + 1}`,
        label,
        ordinal: index + 1,
      });
    }
  }

  if (isLooting) {
    columns.push({
      key: "name",
      label: "Nome",
      ordinal: 0,
    });

    for (let index = 0; index < 15; index++) {
      const label = String(headerRow?.[index] ?? "").trim() || `Col ${index + 1}`;
      columns.push({
        key: `extra${index + 1}`,
        label,
        ordinal: index + 1,
      });
    }
  }

  return columns;
}

function normalizeHeader(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function slugifyProfileName(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

async function loadWindowState() {
  try {
    const boundsRaw = await getAppSetting(WINDOW_BOUNDS_SETTING_KEY);
    const maximizedRaw = await getAppSetting(WINDOW_MAXIMIZED_SETTING_KEY);
    const parsedBounds = boundsRaw ? JSON.parse(boundsRaw) : null;
    const bounds =
      parsedBounds &&
      Number.isFinite(parsedBounds.width) &&
      Number.isFinite(parsedBounds.height)
        ? {
            x: Number.isFinite(parsedBounds.x) ? Math.trunc(parsedBounds.x) : undefined,
            y: Number.isFinite(parsedBounds.y) ? Math.trunc(parsedBounds.y) : undefined,
            width: Math.trunc(parsedBounds.width),
            height: Math.trunc(parsedBounds.height),
          }
        : null;

    return {
      bounds,
      maximized: maximizedRaw === "1",
    };
  } catch {
    return null;
  }
}

async function saveWindowState(windowRef) {
  if (!windowRef || windowRef.isDestroyed()) {
    return;
  }

  try {
    const maximized = windowRef.isMaximized();
    const bounds = maximized ? windowRef.getNormalBounds() : windowRef.getBounds();
    const payload = JSON.stringify({
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
    });
    await setAppSetting(WINDOW_BOUNDS_SETTING_KEY, payload);
    await setAppSetting(
      WINDOW_MAXIMIZED_SETTING_KEY,
      maximized ? "1" : "0"
    );
  } catch {
    // Silencioso: salvar estado da janela nao deve quebrar o app.
  }
}

function getSafeWindowBounds(state) {
  const fallback = { width: 1200, height: 800 };
  const saved = state?.bounds;

  if (!saved) {
    return fallback;
  }

  const width = Math.max(900, Math.min(saved.width, 3000));
  const height = Math.max(640, Math.min(saved.height, 2000));

  if (!Number.isFinite(saved.x) || !Number.isFinite(saved.y)) {
    return { width, height };
  }

  const display = screen.getDisplayNearestPoint({
    x: Math.trunc(saved.x),
    y: Math.trunc(saved.y),
  });
  const area = display.workArea;
  const x = Math.max(area.x, Math.min(Math.trunc(saved.x), area.x + area.width - 120));
  const y = Math.max(area.y, Math.min(Math.trunc(saved.y), area.y + area.height - 120));

  return { x, y, width, height };
}

function readEffects(row, headers) {
  const effects = [];

  for (let slot = 1; slot <= 4; slot++) {
    const effCode = readCell(row, headers, `Eff${slot}Code`);
    const effUnit = readCell(row, headers, `Eff${slot}Unit`);

    if (!effCode || effCode === "0") {
      continue;
    }

    effects.push({
      slot,
      effCode,
      effUnit,
    });
  }

  return effects;
}
