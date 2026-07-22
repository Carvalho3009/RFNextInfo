/// <reference types="vite/client" />

type LootSourceFile = {
  sourceFile: string;
  itemCount: number;
  dictionaryKey: string;
};

type LootSourceColumn = {
  key: Exclude<keyof LootItem, "effects">;
  label: string;
  ordinal: number;
};

type ExcelScanFile = {
  filePath: string;
  relativePath: string;
};

type ExcelScanResult = {
  directoryPath: string;
  files: ExcelScanFile[];
};

type ExcelImportSummary = {
  fileName: string;
  inserted: number;
  effectsInserted: number;
  skippedRows: number;
};

type ExcelBatchImportResult = {
  files: ExcelImportSummary[];
  inserted: number;
  effectsInserted: number;
  skippedRows: number;
};

type BossImportResult = {
  directoryPath: string;
  files: number;
  codes: number;
  inserted: number;
  totalBosses: number;
};

type ExcelUpdateCheckResult = {
  watchDirectory: string;
  trackedFiles: number;
  outdatedFiles: Array<{
    sourceFile: string;
    absolutePath: string;
    previousMtimeMs: number;
    currentMtimeMs: number;
  }>;
  missingFiles: Array<{
    sourceFile: string;
    absolutePath: string;
  }>;
};

type ImportProgress = {
  stage: "reading" | "parsing" | "saving" | "done";
  sourceFile: string;
  fileIndex: number;
  fileCount: number;
  inserted: number;
  total: number;
  effectsInserted: number;
};

type LootItem = {
  [key: `extra${number}`]: string;
  id: number;
  sourceFile: string;
  excelRow: number;
  code: string;
  name: string;
  boss: string;
  bossMap: string;
  model: string;
  icon: string;
  kindClt: string;
  grade: string;
  type: string;
  subtype: string;
  levelLim: string;
  money: string;
  upgrade: string;
  tooltip: string;
  extra1: string;
  extra2: string;
  extra3: string;
  extra4: string;
  extra5: string;
  extra6: string;
  extra7: string;
  extra8: string;
  extra9: string;
  extra10: string;
  extra11: string;
  extra12: string;
  extra13: string;
  extra14: string;
  extra15: string;
  effect1: string;
  effect2: string;
  effect3: string;
  effect4: string;
  dictionaryKey: string;
  effects: LootItemEffect[];
};

type LootItemEffect = {
  slot: number;
  effCode: string;
  effUnit: string;
  name: string;
  description: string;
  unitHint: string;
  display: string;
};

type LootItemFilter = {
  field: Exclude<keyof LootItem, "effects">;
  operator: "contains" | "equals" | "startsWith" | "endsWith" | "notContains";
  value: string;
};

type LootItemPage = {
  items: LootItem[];
  total: number;
};

type LootItemColumnFilters = Partial<
  Record<Exclude<keyof LootItem, "effects">, string[]>
>;

type EffectDictionaryEntry = {
  id?: number;
  dictionaryKey: string;
  itemType: string;
  effCode: string;
  name: string;
  description: string;
  unitHint: string;
  updatedAt?: string;
};

type EffectDictionaryInfo = {
  key: string;
  label: string;
};

type AppProfile = {
  id: string;
  name: string;
  isActive: boolean;
};

interface Window {
  electronAPI?: {
    test: () => Promise<string>;
    listProfiles: () => Promise<AppProfile[]>;
    createProfile: (payload: { name: string; cloneCurrent?: boolean }) => Promise<AppProfile>;
    renameProfile: (payload: { profileId: string; name: string }) => Promise<AppProfile>;
    duplicateProfile: (payload: {
      sourceProfileId: string;
      name: string;
    }) => Promise<AppProfile>;
    deleteProfile: (profileId: string) => Promise<boolean>;
    switchProfile: (profileId: string) => Promise<boolean>;
    restartApp: () => Promise<boolean>;

    importItems: () => Promise<{
      fileName: string;
      inserted: number;
      effectsInserted: number;
      skippedRows: number;
    } | null>;
    importCsv: () => Promise<{
      fileName: string;
      inserted: number;
      effectsInserted: number;
      skippedRows: number;
    } | null>;

    scanExcelDirectory: () => Promise<ExcelScanResult | null>;

    importExcelFiles: (
      files: Array<{
        filePath: string;
        sourceFile: string;
      }>
    ) => Promise<ExcelBatchImportResult>;

    reimportSourceFile: (sourceFile: string) => Promise<ExcelImportSummary | null>;

    saveExcelWatchState: (payload: {
      directoryPath: string;
      files: Array<{
        filePath: string;
        sourceFile: string;
      }>;
    }) => Promise<void>;

    checkExcelUpdates: () => Promise<ExcelUpdateCheckResult>;
    resetExcelUpdatesBaseline: () => Promise<void>;
    listRfIconSheets: () => Promise<
      Array<{ fileName: string; width: number; height: number; cols: number; rows: number }>
    >;

    saveItemLootingEdits: (payload: {
      sourceFile: string;
      edits: Array<{
        itemId: number;
        columnKey: string;
        value: string;
      }>;
    }) => Promise<{
      saved: number;
    }>;
    upsertBoxItemOutBox: (payload: {
      sourceFile: string;
      sheetName: string;
      boxCode: string;
      rewards: Array<{
        itemCode: string;
        quantity: number;
        chance: number;
      }>;
    }) => Promise<{
      row: number;
      inserted: boolean;
      rewards: number;
    }>;

    importBossDirectory: () => Promise<BossImportResult | null>;

    onImportProgress: (
      callback: (progress: ImportProgress) => void
    ) => () => void;

    countItems: () => Promise<{
      items: number;
      effects: number;
    }>;

    listSourceFiles: () => Promise<LootSourceFile[]>;

    listSourceColumns: (sourceFile: string) => Promise<LootSourceColumn[]>;
    generateGrade1WeaponSocketCombines: () => Promise<{
      weapons: number;
      groups: number;
      linkedInserted: number;
      combinesInserted: number;
    }>;
    saveGeneratedWeaponSocketCombines: () => Promise<{
      combineRows: number;
      linkedRows: number;
    }>;
    listSourceSheets: (sourceFile: string) => Promise<string[]>;
    importSourceSheet: (payload: {
      sourceFile: string;
      sheetName: string;
    }) => Promise<ExcelImportSummary>;

    deleteSourceFile: (sourceFile: string) => Promise<void>;
    listSourceBackups: (sourceFile: string) => Promise<
      Array<{ name: string; path: string; sourcePath: string }>
    >;
    restoreSourceBackup: (payload: {
      sourceFile: string;
      backupName: string;
    }) => Promise<{ restored: boolean }>;

    listItems: (options?: {
      sourceFile?: string;
      search?: string;
      filters?: LootItemFilter[];
      columnFilters?: LootItemColumnFilters;
      sortField?: Exclude<keyof LootItem, "effects">;
      sortDirection?: "asc" | "desc";
      limit?: number;
      offset?: number;
    }) => Promise<LootItemPage>;

    listItemColumnValues: (options?: {
      sourceFile?: string;
      search?: string;
      filters?: LootItemFilter[];
      columnFilters?: LootItemColumnFilters;
      field: Exclude<keyof LootItem, "effects">;
      valueSearch?: string;
    }) => Promise<string[]>;

    listEffectDictionaries: () => Promise<EffectDictionaryInfo[]>;

    setSourceDictionary: (
      sourceFile: string,
      dictionaryKey: string
    ) => Promise<void>;

    listEffectDictionary: (options?: {
      search?: string;
      dictionaryKey?: string;
    }) => Promise<EffectDictionaryEntry[]>;

    saveEffectDictionaryEntry: (
      entry: EffectDictionaryEntry
    ) => Promise<number>;

    deleteEffectDictionaryEntry: (id: number) => Promise<void>;
  };
}
