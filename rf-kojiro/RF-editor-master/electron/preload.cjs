const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  test: async () => {
    return await ipcRenderer.invoke("test");
  },

  listProfiles: async () => {
    return await ipcRenderer.invoke("list-profiles");
  },

  createProfile: async (payload) => {
    return await ipcRenderer.invoke("create-profile", payload);
  },

  renameProfile: async (payload) => {
    return await ipcRenderer.invoke("rename-profile", payload);
  },

  duplicateProfile: async (payload) => {
    return await ipcRenderer.invoke("duplicate-profile", payload);
  },

  deleteProfile: async (profileId) => {
    return await ipcRenderer.invoke("delete-profile", profileId);
  },

  switchProfile: async (profileId) => {
    return await ipcRenderer.invoke("switch-profile", profileId);
  },

  restartApp: async () => {
    return await ipcRenderer.invoke("restart-app");
  },

  importItems: async () => {
    return await ipcRenderer.invoke("import-items");
  },
  importCsv: async () => {
    return await ipcRenderer.invoke("import-csv");
  },

  scanExcelDirectory: async () => {
    return await ipcRenderer.invoke("scan-excel-directory");
  },

  importExcelFiles: async (files) => {
    return await ipcRenderer.invoke("import-excel-files", files);
  },

  reimportSourceFile: async (sourceFile) => {
    return await ipcRenderer.invoke("reimport-source-file", sourceFile);
  },

  saveExcelWatchState: async (payload) => {
    return await ipcRenderer.invoke("save-excel-watch-state", payload);
  },

  checkExcelUpdates: async () => {
    return await ipcRenderer.invoke("check-excel-updates");
  },
  listRfIconSheets: async () => {
    return await ipcRenderer.invoke("list-rf-icon-sheets");
  },

  resetExcelUpdatesBaseline: async () => {
    return await ipcRenderer.invoke("reset-excel-updates-baseline");
  },

  saveItemLootingEdits: async (payload) => {
    return await ipcRenderer.invoke("save-itemlooting-edits", payload);
  },

  upsertBoxItemOutBox: async (payload) => {
    return await ipcRenderer.invoke("upsert-boxitemout-box", payload);
  },

  importBossDirectory: async () => {
    return await ipcRenderer.invoke("import-boss-directory");
  },

  onImportProgress: (callback) => {
    const listener = (_event, progress) => callback(progress);
    ipcRenderer.on("import-progress", listener);

    return () => {
      ipcRenderer.removeListener("import-progress", listener);
    };
  },

  countItems: async () => {
    return await ipcRenderer.invoke("count-items");
  },

  listSourceFiles: async () => {
    return await ipcRenderer.invoke("list-source-files");
  },

  listSourceColumns: async (sourceFile) => {
    return await ipcRenderer.invoke("list-source-columns", sourceFile);
  },

  generateGrade1WeaponSocketCombines: async () => {
    return await ipcRenderer.invoke("generate-grade1-weapon-socket-combines");
  },
  saveGeneratedWeaponSocketCombines: async () => {
    return await ipcRenderer.invoke("save-generated-weapon-socket-combines");
  },

  listSourceSheets: async (sourceFile) => {
    return await ipcRenderer.invoke("list-source-sheets", sourceFile);
  },

  importSourceSheet: async (payload) => {
    return await ipcRenderer.invoke("import-source-sheet", payload);
  },

  deleteSourceFile: async (sourceFile) => {
    return await ipcRenderer.invoke("delete-source-file", sourceFile);
  },
  listSourceBackups: async (sourceFile) => {
    return await ipcRenderer.invoke("list-source-backups", sourceFile);
  },
  restoreSourceBackup: async (payload) => {
    return await ipcRenderer.invoke("restore-source-backup", payload);
  },

  listItems: async (options) => {
    return await ipcRenderer.invoke("list-items", options);
  },

  listItemColumnValues: async (options) => {
    return await ipcRenderer.invoke("list-item-column-values", options);
  },

  listEffectDictionaries: async () => {
    return await ipcRenderer.invoke("list-effect-dictionaries");
  },

  setSourceDictionary: async (sourceFile, dictionaryKey) => {
    return await ipcRenderer.invoke("set-source-dictionary", sourceFile, dictionaryKey);
  },

  listEffectDictionary: async (options) => {
    return await ipcRenderer.invoke("list-effect-dictionary", options);
  },

  saveEffectDictionaryEntry: async (entry) => {
    return await ipcRenderer.invoke("save-effect-dictionary-entry", entry);
  },

  deleteEffectDictionaryEntry: async (id) => {
    return await ipcRenderer.invoke("delete-effect-dictionary-entry", id);
  },
});
