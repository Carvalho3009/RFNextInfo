import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import "./topbar-overrides.css";

type ColumnKey = Exclude<keyof LootItem, "effects">;

type ItemColumn = {
  key: ColumnKey;
  label: string;
};

type FilterOperator = LootItemFilter["operator"];

type DraftFilter = LootItemFilter & {
  id: number;
};

type DraftEffectEntry = EffectDictionaryEntry & {
  draftId: string;
};

type ColumnFilters = Partial<Record<ColumnKey, string[]>>;
type ItemEditDraft = Record<number, Partial<Record<ColumnKey, string>>>;
type TemplateAppliedMarks = Record<number, number>;
type CellPosition = { row: number; col: number };
type CellRange = { startRow: number; endRow: number; startCol: number; endCol: number };
type DraftCellChange = {
  itemId: number;
  column: ColumnKey;
  previousValue: string;
  nextValue: string;
};
type RaceKey = "A" | "B" | "C" | "unknown";
type LootTemplateRow = {
  values: Partial<Record<ColumnKey, string>>;
};
type LootTemplate = {
  sourceRace: RaceKey;
  rows: LootTemplateRow[];
};
type BossGroup = {
  key: string;
  monsterCode: string;
  name: string;
  bossMap: string;
  items: LootItem[];
};
type BoxRace = "all" | "acc" | "bell" | "cora";
type BoxRewardDraft = {
  itemCode: string;
  itemName: string;
  itemIcon: string;
  itemSourceFile: string;
  quantity: string;
  chancePercent: string;
  civil: string;
  status: "idle" | "ok" | "invalid" | "unknown";
};

const ITEM_COLUMNS: ItemColumn[] = [
  { key: "excelRow", label: "#" },
  { key: "sourceFile", label: "Arquivo" },
  { key: "code", label: "Code" },
  { key: "name", label: "Name" },
  { key: "boss", label: "Boss" },
  { key: "bossMap", label: "Mapa" },
  { key: "model", label: "Model" },
  { key: "icon", label: "Icon" },
  { key: "kindClt", label: "KindClt" },
  { key: "grade", label: "Grade" },
  { key: "type", label: "Type" },
  { key: "subtype", label: "SubType" },
  { key: "levelLim", label: "LevelLim" },
  { key: "money", label: "Money" },
  ...Array.from({ length: 160 }, (_value, index) => ({
    key: `extra${index + 1}` as ColumnKey,
    label: `Col ${index + 1}`,
  })),
  { key: "effect1", label: "Eff1" },
  { key: "effect2", label: "Eff2" },
  { key: "effect3", label: "Eff3" },
  { key: "effect4", label: "Eff4" },
  { key: "upgrade", label: "Upgrade" },
  { key: "tooltip", label: "ToolTip" },
];

const DEFAULT_COLUMNS: ColumnKey[] = [
  "excelRow",
  "code",
  "name",
  "boss",
  "bossMap",
  "type",
  "subtype",
  "grade",
  "levelLim",
  "money",
  "extra1",
  "extra2",
  "extra3",
  "extra4",
  "extra5",
  "effect1",
  "effect2",
  "effect3",
  "effect4",
];

const COLUMN_STORAGE_PREFIX = "rf-loot-editor.columns.";
const COLUMN_WIDTH_STORAGE_PREFIX = "rf-loot-editor.column-widths.";
const HIDDEN_COLUMN_OPTIONS_PREFIX = "rf-loot-editor.hidden-column-options.";
const FILTER_STATE_STORAGE_PREFIX = "rf-loot-editor.filter-state.";
const COLUMN_PANEL_COLLAPSED_KEY = "rf-loot-editor.column-panel-collapsed";
const FILTER_PANEL_COLLAPSED_KEY = "rf-loot-editor.filter-panel-collapsed";
const ITEM_PAGE_STORAGE_KEY = "rf-loot-editor.item-page";
const ITEM_PAGE_SIZE_STORAGE_KEY = "rf-loot-editor.item-page-size";
const RECENT_SOURCES_STORAGE_KEY = "rf-loot-editor.recent-sources";
const LAST_SELECTED_SOURCE_KEY = "rf-loot-editor.last-selected-source";
const LAST_ACTIVE_VIEW_KEY = "rf-loot-editor.last-active-view";
const PAGE_SIZE_OPTIONS = [200, 500, 1000];
const SHOW_FILTER_PANEL = false;
const MAX_RECENT_SOURCES = 7;
const MIN_COLUMN_WIDTH = 8;
const MAX_COLUMN_WIDTH = 620;
const EXTRA_COLUMN_KEYS = Array.from(
  { length: 160 },
  (_value, index) => `extra${index + 1}` as ColumnKey
);
const DEFAULT_HIDDEN_COLUMN_OPTIONS_FOR_ALL: ColumnKey[] = [
  "sourceFile",
  ...EXTRA_COLUMN_KEYS,
];
const ITEM_LOOTING_ALLOWED_COLUMNS = new Set<ColumnKey>([
  "name",
  "boss",
  "bossMap",
  ...EXTRA_COLUMN_KEYS,
]);
const NON_ITEM_LOOTING_ALLOWED_COLUMNS = new Set<ColumnKey>(
  ITEM_COLUMNS.map((column) => column.key).filter(
    (key) => key !== "boss" && key !== "bossMap"
  )
);
const DEFAULT_HIDDEN_LABELS = new Set(
  [
    "IsExist",
    "Model",
    "Kind",
    "KindClt",
    "FixPart",
    "ClassGradeLim",
    "UpLvLim",
    "Money",
    "ToolTip",
    "IsNormA",
  ].map((label) => label.toLowerCase())
);
const ITEM_LOOTING_EDITABLE_COLUMNS = new Set<ColumnKey>(EXTRA_COLUMN_KEYS);
const RF_CHANCE_MAX = 2147483647;
const BUILD_MARKER = "Build: 2026-05-26-01";

const DEFAULT_COLUMN_WIDTHS: Partial<Record<ColumnKey, number>> = {
  excelRow: 36,
  sourceFile: 170,
  code: 120,
  name: 220,
  boss: 80,
  bossMap: 170,
  type: 80,
  subtype: 90,
  grade: 70,
  levelLim: 90,
  money: 110,
  extra1: 120,
  extra2: 120,
  extra3: 120,
  extra4: 120,
  extra5: 120,
  extra6: 120,
  extra7: 120,
  extra8: 120,
  extra9: 120,
  extra10: 120,
  extra11: 120,
  extra12: 120,
  extra13: 120,
  extra14: 120,
  extra15: 120,
  effect1: 160,
  effect2: 160,
  effect3: 160,
  effect4: 160,
};

const FILTER_OPERATORS: { value: FilterOperator; label: string }[] = [
  { value: "contains", label: "contem" },
  { value: "equals", label: "igual a" },
  { value: "startsWith", label: "comeca com" },
  { value: "endsWith", label: "termina com" },
  { value: "notContains", label: "nao contem" },
];

const SEARCHABLE_COLUMNS = ITEM_COLUMNS.filter(
  (column) =>
    column.key !== "excelRow" &&
    column.key !== "id" &&
    column.key !== "dictionaryKey" &&
    column.key !== "effect1" &&
    column.key !== "effect2" &&
    column.key !== "effect3" &&
    column.key !== "effect4"
);

function App() {
  const [message, setMessage] = useState(
    window.electronAPI ? "" : "Abra pelo Electron para importar arquivos Excel."
  );
  const [profiles, setProfiles] = useState<AppProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState("");
  const [profileNameDraft, setProfileNameDraft] = useState("");
  const [profileAction, setProfileAction] = useState<"new" | "rename" | "duplicate" | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<ImportProgress | null>(null);
  const [scannedDirectory, setScannedDirectory] = useState("");
  const [scannedExcelFiles, setScannedExcelFiles] = useState<ExcelScanFile[]>([]);
  const [selectedExcelFiles, setSelectedExcelFiles] = useState<string[]>([]);
  const [scannedExcelSearch, setScannedExcelSearch] = useState("");
  const [outdatedSourceFiles, setOutdatedSourceFiles] = useState<string[]>([]);
  const [excelUpdateNotice, setExcelUpdateNotice] = useState("");
  const [rfIconSheets, setRfIconSheets] = useState<
    Array<{ fileName: string; width: number; height: number; cols: number; rows: number }>
  >([]);
  const [sourceSheets, setSourceSheets] = useState<string[]>([]);
  const [selectedSheetName, setSelectedSheetName] = useState("");
  const [boxBuilderCode, setBoxBuilderCode] = useState("");
  const [boxBuilderRace, setBoxBuilderRace] = useState<BoxRace>("all");
  const [boxRewards, setBoxRewards] = useState<BoxRewardDraft[]>([]);
  const [boxCodeSuggestions, setBoxCodeSuggestions] = useState<Record<number, LootItem[]>>({});
  const [boxCodeSuggestionCache, setBoxCodeSuggestionCache] = useState<Record<string, LootItem[]>>({});
  const [activeSuggestionRow, setActiveSuggestionRow] = useState<number | null>(null);
  const [sourceCivilKeyCache, setSourceCivilKeyCache] = useState<Record<string, ColumnKey | "">>({});
  const [suggestionCivilByCode, setSuggestionCivilByCode] = useState<Record<string, string>>({});
  const [itemMetaCache, setItemMetaCache] = useState<
    Record<string, { name: string; civil: string; icon: string; sourceFile: string }>
  >({});
  const [showBulkRemoveSources, setShowBulkRemoveSources] = useState(false);
  const [isSourceDropdownOpen, setIsSourceDropdownOpen] = useState(false);
  const [bulkSelectedSources, setBulkSelectedSources] = useState<string[]>([]);
  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [sources, setSources] = useState<LootSourceFile[]>([]);
  const [selectedSource, setSelectedSource] = useState("");
  const [sourceColumnLabels, setSourceColumnLabels] = useState<
    Partial<Record<ColumnKey, string>>
  >({});
  const [sourceColumnOrdinals, setSourceColumnOrdinals] = useState<
    Partial<Record<ColumnKey, number>>
  >({});
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<DraftFilter[]>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFilters>({});
  const [items, setItems] = useState<LootItem[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [currentPage, setCurrentPage] = useState(0);
  const [itemsPerPage, setItemsPerPage] = useState(loadSavedPageSize);
  const [tableScrollTop, setTableScrollTop] = useState(0);
  const [tableViewportHeight, setTableViewportHeight] = useState(560);
  const [quickLookup, setQuickLookup] = useState("");
  const [quickLookupResults, setQuickLookupResults] = useState<LootItem[]>([]);
  const [isQuickLookupLoading, setIsQuickLookupLoading] = useState(false);
  const [topScrollContentWidth, setTopScrollContentWidth] = useState(0);
  const [pageInput, setPageInput] = useState("");
  const [csvSortField, setCsvSortField] = useState<ColumnKey>("excelRow");
  const [csvSortDirection, setCsvSortDirection] = useState<"asc" | "desc">("asc");
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(DEFAULT_COLUMNS);
  const [hiddenColumnOptions, setHiddenColumnOptions] = useState<ColumnKey[]>(() =>
    loadHiddenColumnOptionsForSource("")
  );
  const [showTableIcons, setShowTableIcons] = useState(false);
  const [sourceBackups, setSourceBackups] = useState<Array<{ name: string; path: string; sourcePath: string }>>([]);
  const [iconEditBuffer, setIconEditBuffer] = useState<Record<string, string>>({});
  const [isColumnPanelCollapsed, setIsColumnPanelCollapsed] = useState(
    loadColumnPanelCollapsed
  );
  const [isFilterPanelCollapsed, setIsFilterPanelCollapsed] = useState(
    loadFilterPanelCollapsed
  );
  const [activeView, setActiveView] = useState<"items" | "effects" | "hgk" | "itemCombine">(() => {
    const saved = window.localStorage.getItem(LAST_ACTIVE_VIEW_KEY);
    return saved === "effects" || saved === "hgk" || saved === "itemCombine" ? saved : "items";
  });
  const [activeSidePanel, setActiveSidePanel] = useState<
    "columns" | "boxbuilder" | "effects" | "gearscore" | "gems" | "transmog" | "hgk" | null
  >("columns");
  const [itemCombineViewMode, setItemCombineViewMode] = useState<"recipes" | "groups" | "raw">(
    "recipes"
  );
  const [itemCombineCardsPerPage, setItemCombineCardsPerPage] = useState(4);
  const [dictionaries, setDictionaries] = useState<EffectDictionaryInfo[]>([]);
  const [selectedDictionaryKey, setSelectedDictionaryKey] = useState("resource");
  const [effectSearch, setEffectSearch] = useState("");
  const [effectEntries, setEffectEntries] = useState<DraftEffectEntry[]>([]);
  const [isLoadingEffects, setIsLoadingEffects] = useState(false);
  const [openColumnFilter, setOpenColumnFilter] = useState<ColumnKey | null>(null);
  const [columnValueSearch, setColumnValueSearch] = useState("");
  const [columnFilterValues, setColumnFilterValues] = useState<string[]>([]);
  const [draftColumnValues, setDraftColumnValues] = useState<string[]>([]);
  const [isLoadingColumnValues, setIsLoadingColumnValues] = useState(false);
  const [columnWidths, setColumnWidths] = useState<Partial<Record<ColumnKey, number>>>(
    () => loadColumnWidthsForSource("")
  );
  const [editDrafts, setEditDrafts] = useState<ItemEditDraft>({});
  const [templateAppliedMarks, setTemplateAppliedMarks] = useState<TemplateAppliedMarks>({});
  const [isSavingEdits, setIsSavingEdits] = useState(false);
  const [templateSourceBossKey, setTemplateSourceBossKey] = useState("");
  const [lootTemplate, setLootTemplate] = useState<LootTemplate | null>(null);
  const [activeCell, setActiveCell] = useState<CellPosition | null>(null);
  const [selectedCellRange, setSelectedCellRange] = useState<CellRange | null>(null);
  const [undoStack, setUndoStack] = useState<DraftCellChange[][]>([]);
  const [redoStack, setRedoStack] = useState<DraftCellChange[][]>([]);
  const [applyScope, setApplyScope] = useState<"sameMap" | "selectedMaps" | "allVisible">(
    "sameMap"
  );
  const [selectedMapsForApply, setSelectedMapsForApply] = useState<string[]>([]);
  const [applyRaceMode, setApplyRaceMode] = useState<"auto" | "A" | "B" | "C">("auto");
  const [allMapOptions, setAllMapOptions] = useState<string[]>([]);
  const [recentSources, setRecentSources] = useState<string[]>(loadRecentSources);
  const [hideRepeatedCombineCards, setHideRepeatedCombineCards] = useState(false);
  const [isGeneratingCombineTool, setIsGeneratingCombineTool] = useState(false);
  const columnFilterRef = useRef<HTMLDivElement | null>(null);
  const sourceDropdownRef = useRef<HTMLDivElement | null>(null);
  const tableWrapRef = useRef<HTMLDivElement | null>(null);
  const tableTopScrollRef = useRef<HTMLDivElement | null>(null);

  const isElectron = Boolean(window.electronAPI);

  useEffect(() => {
    window.localStorage.setItem(LAST_ACTIVE_VIEW_KEY, activeView);
  }, [activeView]);

  const selectedSourceLabel = selectedSource
    ? formatSourceLabel(selectedSource)
    : "todos";
  const selectedSourceDictionary =
    sources.find((source) => source.sourceFile === selectedSource)?.dictionaryKey ??
    "resource";
  const isCsvSource = (sourceFile: string) => /\.csv$/i.test(sourceFile);
  const isItemCombineSource = (sourceFile: string) => {
    const baseName = sourceFile.replace(/\\/g, "/").split("/").pop() || "";
    return /^(combinetable2?|linkedcombines?)\.xlsx$/i.test(baseName);
  };
  const sourceBelongsToActiveView = (sourceFile: string) => {
    if (activeView === "hgk") return isCsvSource(sourceFile);
    if (activeView === "itemCombine") return isItemCombineSource(sourceFile);
    return !isCsvSource(sourceFile);
  };
  const scopedSources = useMemo(() => {
    if (activeView === "hgk") {
      return sources.filter((source) => isCsvSource(source.sourceFile));
    }
    if (activeView === "itemCombine") {
      return sources.filter((source) => isItemCombineSource(source.sourceFile));
    }
    return sources.filter((source) => !isCsvSource(source.sourceFile));
  }, [activeView, sources]);
  const sortedScopedSources = useMemo(() => {
    return [...scopedSources].sort((first, second) =>
      formatSourceLabel(first.sourceFile).localeCompare(
        formatSourceLabel(second.sourceFile),
        undefined,
        { numeric: true, sensitivity: "base" }
      )
    );
  }, [scopedSources]);
  const selectedSourceValue = useMemo(
    () =>
      selectedSource &&
      scopedSources.some((source) => source.sourceFile === selectedSource)
        ? selectedSource
        : "",
    [selectedSource, scopedSources]
  );
  const recentSourceTabs = useMemo(() => {
    const existingSources = new Set(scopedSources.map((source) => source.sourceFile));
    return recentSources.filter((sourceFile) => existingSources.has(sourceFile));
  }, [recentSources, scopedSources]);
  const isItemLootingSelected = /itemlooting/i.test(selectedSource);
  const isBoxItemOutSelected = /boxitemout/i.test(selectedSource);
  const isGearScoreCsvSelected = /gear_score_items?\.csv$/i.test(selectedSource);
  const availableColumnKeys = useMemo(() => {
    const sourceKeys = Object.keys(sourceColumnOrdinals) as ColumnKey[];
    if (isItemLootingSelected) {
      if (sourceKeys.length > 0) {
        const merged: ColumnKey[] = [
          "name",
          "boss",
          "bossMap",
          ...sourceKeys.filter((key) => ITEM_LOOTING_ALLOWED_COLUMNS.has(key)),
        ];
        return Array.from(new Set(merged));
      }
      return ITEM_COLUMNS.filter((column) => ITEM_LOOTING_ALLOWED_COLUMNS.has(column.key)).map(
        (column) => column.key
      );
    }

    if (sourceKeys.length > 0) {
      return sourceKeys.filter((key) => NON_ITEM_LOOTING_ALLOWED_COLUMNS.has(key));
    }

    return ITEM_COLUMNS.filter((column) =>
      NON_ITEM_LOOTING_ALLOWED_COLUMNS.has(column.key)
    ).map((column) => column.key);
  }, [isItemLootingSelected, sourceColumnOrdinals]);
  const filteredScannedExcelFiles = useMemo(() => {
    const term = scannedExcelSearch.trim().toLowerCase();
    if (!term) {
      return scannedExcelFiles;
    }
    return scannedExcelFiles.filter((file) =>
      file.relativePath.toLowerCase().includes(term)
    );
  }, [scannedExcelFiles, scannedExcelSearch]);

  const selectedColumns = useMemo(() => {
    const dynamicColumns = ITEM_COLUMNS.filter(
      (column) =>
        column.key !== "excelRow" &&
        !(selectedSource && column.key === "sourceFile") &&
        visibleColumns.includes(column.key) &&
        availableColumnKeys.includes(column.key)
    )
      .map((column) => ({
        ...column,
        label: sourceColumnLabels[column.key] || column.label,
        ordinal: sourceColumnOrdinals[column.key] ?? Number.MAX_SAFE_INTEGER,
      }))
      .sort((a, b) => {
        if (isItemLootingSelected) {
          const priority: Partial<Record<ColumnKey, number>> = {
            bossMap: 0,
            name: 1,
          };
          const pa = priority[a.key] ?? Number.MAX_SAFE_INTEGER;
          const pb = priority[b.key] ?? Number.MAX_SAFE_INTEGER;
          if (pa !== pb) {
            return pa - pb;
          }
        } else {
          const priority: Partial<Record<ColumnKey, number>> = {
            icon: -1,
          };
          const pa = priority[a.key] ?? Number.MAX_SAFE_INTEGER;
          const pb = priority[b.key] ?? Number.MAX_SAFE_INTEGER;
          if (pa !== pb) {
            return pa - pb;
          }
        }
        if (a.ordinal !== b.ordinal) {
          return a.ordinal - b.ordinal;
        }
        return ITEM_COLUMNS.findIndex((column) => column.key === a.key) -
          ITEM_COLUMNS.findIndex((column) => column.key === b.key);
      });
    return [ITEM_COLUMNS[0], ...dynamicColumns];
  }, [availableColumnKeys, isItemLootingSelected, selectedSource, sourceColumnLabels, sourceColumnOrdinals, visibleColumns]);
  const displayItems = useMemo(() => {
    if (/\.csv$/i.test(selectedSource)) {
      return items;
    }
    if (!isBoxItemOutSelected) {
      return items;
    }
    return items.filter((item) => {
      const code = String(item.code ?? "").trim();
      return code !== "" && !/^row-\d+$/i.test(code);
    });
  }, [isBoxItemOutSelected, items, selectedSource]);
  const visibleBossItems = useMemo(
    () =>
      items.filter(
        (item) => /itemlooting/i.test(item.sourceFile) && String(item.boss) === "Boss"
      ),
    [items]
  );
  const visibleMapOptions = useMemo(() => {
    const maps = new Set<string>();

    for (const boss of visibleBossItems) {
      for (const map of splitBossMaps(boss.bossMap)) {
        maps.add(map);
      }
    }

    return [...maps].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [visibleBossItems]);
  const monsterColumnKey = useMemo(
    () => findItemLootingColumnKey(sourceColumnLabels, "monster", "extra1"),
    [sourceColumnLabels]
  );
  const bossGroups = useMemo(() => {
    const groups = new Map<string, BossGroup>();

    for (const item of visibleBossItems) {
      const monsterCode = String(item[monsterColumnKey] ?? "").trim();
      const primaryMap = splitBossMaps(item.bossMap)[0] ?? "";
      const key = `${monsterCode}::${primaryMap}`;
      const current = groups.get(key);

      if (current) {
        current.items.push(item);
        continue;
      }

      groups.set(key, {
        key,
        monsterCode,
        name: item.name,
        bossMap: item.bossMap,
        items: [item],
      });
    }

    return [...groups.values()].sort((a, b) =>
      `${a.name} ${a.bossMap}`.localeCompare(`${b.name} ${b.bossMap}`)
    );
  }, [visibleBossItems, monsterColumnKey]);
  const visibleColumnOptions = useMemo(() => {
    return ITEM_COLUMNS.filter(
      (column) =>
        availableColumnKeys.includes(column.key) &&
        !hiddenColumnOptions.includes(column.key)
    ).sort(
      (a, b) =>
        (sourceColumnOrdinals[a.key] ?? Number.MAX_SAFE_INTEGER) -
        (sourceColumnOrdinals[b.key] ?? Number.MAX_SAFE_INTEGER)
    );
  }, [availableColumnKeys, hiddenColumnOptions, sourceColumnOrdinals]);
  const hiddenColumnOptionItems = useMemo(() => {
    return ITEM_COLUMNS.filter(
      (column) =>
        availableColumnKeys.includes(column.key) &&
        hiddenColumnOptions.includes(column.key)
    ).sort(
      (a, b) =>
        (sourceColumnOrdinals[a.key] ?? Number.MAX_SAFE_INTEGER) -
        (sourceColumnOrdinals[b.key] ?? Number.MAX_SAFE_INTEGER)
    );
  }, [availableColumnKeys, hiddenColumnOptions, sourceColumnOrdinals]);
  const effectiveItemsPerPage = activeView === "itemCombine" ? itemCombineCardsPerPage : itemsPerPage;
  const totalPages = Math.max(Math.ceil(totalItems / effectiveItemsPerPage), 1);
  const effectiveTotalItems = isBoxItemOutSelected ? displayItems.length : totalItems;
  const firstItemIndex = effectiveTotalItems === 0 ? 0 : currentPage * effectiveItemsPerPage + 1;
  const lastItemIndex = Math.min((currentPage + 1) * effectiveItemsPerPage, effectiveTotalItems);
  const visiblePageNumbers = getVisiblePageNumbers(currentPage, totalPages);
  const tableWidth = selectedColumns.reduce(
    (totalWidth, column) => totalWidth + getColumnWidth(column.key),
    0
  );
  const boxItemOutInvalidChanceRows = useMemo(() => {
    if (!isBoxItemOutSelected) {
      return 0;
    }
    let invalid = 0;
    for (const item of items) {
      const values = [item.extra4, item.extra7, item.extra10, item.extra13];
      const total = values.reduce((sum, current) => {
        const value = Number(String(current ?? "").trim().replace(",", "."));
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0);
      if (total > 0 && total !== 10000) {
        invalid += 1;
      }
    }
    return invalid;
  }, [isBoxItemOutSelected, items]);
  const estimatedRowHeight = isItemLootingSelected ? 30 : 34;
  const virtualOverscan = 12;
  const virtualVisibleCount = Math.ceil(tableViewportHeight / estimatedRowHeight) + virtualOverscan * 2;
  const rawVirtualStart = Math.max(
    Math.floor(tableScrollTop / estimatedRowHeight) - virtualOverscan,
    0
  );
  const maxVirtualStart = Math.max(0, items.length - virtualVisibleCount);
  const virtualStartIndex = Math.min(rawVirtualStart, maxVirtualStart);
  const virtualEndIndex = Math.min(items.length - 1, virtualStartIndex + virtualVisibleCount - 1);
  const topSpacerHeight = items.length > 0 ? virtualStartIndex * estimatedRowHeight : 0;
  const bottomSpacerHeight =
    items.length > 0
      ? Math.max(0, (items.length - (virtualEndIndex + 1)) * estimatedRowHeight)
      : 0;
  const hasIconPreviewInTable =
    showTableIcons && selectedColumns.some((column) => column.key === "icon");
  const shouldVirtualize = displayItems.length > (hasIconPreviewInTable ? 250 : 1200);
  const visibleRows = shouldVirtualize
    ? displayItems.slice(
        virtualStartIndex,
        virtualEndIndex >= virtualStartIndex ? virtualEndIndex + 1 : virtualStartIndex
      )
    : displayItems;
  const isLinkedCombineSelected = /linkedcombines?/i.test(selectedSource);
  const isCombineTableSelected = /combinetable/i.test(selectedSource);
  const maxExtraColumnNumber = availableColumnKeys.reduce((max, key) => {
    const match = /^extra(\d+)$/i.exec(key);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 0);
  const combineTableNeedsReimport =
    isCombineTableSelected &&
    availableColumnKeys.some((key) => key === "extra80") &&
    !availableColumnKeys.some((key) => key === "extra81");
  const getCombineColumn = (item: LootItem, columnNumber: number) => {
    if (columnNumber <= 1) {
      return item.code || "";
    }
    return String(item[`extra${columnNumber}`] || "");
  };
  const itemCombineFilteredRows = useMemo(() => {
    let rows = displayItems;
    if (hideRepeatedCombineCards) {
      const seen = new Set<string>();
      rows = rows.filter((item) => {
        const key = (getCombineColumn(item, 5) || item.code || "").trim().toLowerCase();
        if (!key) return true;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    }
    return rows;
  }, [displayItems, hideRepeatedCombineCards]);
  const itemCombinePreviewRows = itemCombineFilteredRows;
  const formatCivilLabel = (civil: string) => {
    const value = String(civil || "").trim();
    if (value === "11111") return "Todas";
    if (value === "11000") return "Bell";
    if (value === "00110") return "Cora";
    if (value === "00001") return "Acc";
    if (value === "11110") return "Bell/Cora";
    return value || "-";
  };
  const getCivilIconInfo = (civil: string) => {
    const value = String(civil || "").trim().slice(0, 5);
    const map: Record<string, { src: string; label: string }> = {
      "11111": { src: "/rf-icons/races/all.png", label: "Todas" },
      "11000": { src: "/rf-icons/races/bell.png", label: "Bell" },
      "00110": { src: "/rf-icons/races/cora.png", label: "Cora" },
      "00001": { src: "/rf-icons/races/acc.png", label: "Acc" },
      "11110": { src: "/rf-icons/races/bell_cora.png", label: "Bell/Cora" },
    };
    return map[value] || null;
  };
  const isCivilColumn = (column: ColumnKey) =>
    getNormalizedColumnLabel(column).includes("civil");
  const formatDalant = (value: string) => {
    const numberValue = Number(String(value || "").replace(/\D/g, ""));
    return Number.isFinite(numberValue) && numberValue > 0
      ? numberValue.toLocaleString("pt-BR")
      : value || "-";
  };
  const formatCombineLoss = (value: string) => {
    const numberValue = Number(String(value || "").trim());
    return Number.isFinite(numberValue) && numberValue !== 0
      ? String(numberValue * -1)
      : value || "-";
  };
  const formatCombineChance = (value: string) => {
    const numberValue = Number(String(value || "").trim());
    if (!Number.isFinite(numberValue)) return value || "-";
    return `${(numberValue / 100).toLocaleString("pt-BR", {
      maximumFractionDigits: 2,
    })}%`;
  };
  const getCombineFailChance = (
    results: Array<{ chance: string }>
  ) => {
    const totalChance = results.reduce((sum, result) => {
      const value = Number(String(result.chance || "").trim());
      return Number.isFinite(value) ? sum + value : sum;
    }, 0);
    return Math.max(0, 10000 - totalChance);
  };
  const isLinkedCombineCode = (value: string) => /^L[LR]/i.test(String(value || "").trim());
  const getCachedItemName = (code: string) => {
    const key = String(code || "").trim().toLowerCase();
    return itemMetaCache[key]?.name || "";
  };
  const formatItemCodeName = (code: string) => {
    const value = String(code || "").trim();
    if (!value || value === "-1") return "-";
    const name = getCachedItemName(value);
    return name ? `${value} - ${name}` : value;
  };
  const itemCombineRecipeCards = useMemo(
    () =>
      itemCombinePreviewRows.map((item) => {
        const resultBlocks = Math.max(0, Math.floor((maxExtraColumnNumber - 23) / 6));
        const results = Array.from({ length: resultBlocks }, (_value, index) => {
          const base = 24 + index * 6;
          return {
            code: getCombineColumn(item, base),
            upt: getCombineColumn(item, base + 1),
            effectType: getCombineColumn(item, base + 2),
            message: getCombineColumn(item, base + 3),
            chance: getCombineColumn(item, base + 4),
            result: getCombineColumn(item, base + 5),
          };
        }).filter((result) => {
          const code = String(result.code || "").trim();
          return code && code !== "-1";
        });
        return {
          id: item.id,
          excelRow: item.excelRow,
          code: item.code || "-",
          dalant: getCombineColumn(item, 2),
          civil: getCombineColumn(item, 3),
          active: getCombineColumn(item, 4),
          description: getCombineColumn(item, 5) || item.code || "-",
          failLostCount: getCombineColumn(item, 6),
          isSelectItem: getCombineColumn(item, 22),
          rewardCount: String(results.length || getCombineColumn(item, 23) || ""),
          results,
          materials: [7, 10, 13, 16, 19]
            .map((base) => ({
              item: getCombineColumn(item, base),
              upt: getCombineColumn(item, base + 1),
              quantity: getCombineColumn(item, base + 2),
            }))
            .filter((material) => material.item && material.item !== "-1"),
        };
      }),
    [itemCombinePreviewRows, itemMetaCache]
  );
  const itemCombineGroupCards = useMemo(
    () =>
      itemCombinePreviewRows.map((item) => ({
        id: item.id,
        code: item.code || "-",
        entries: [
          item.name,
          item.grade,
          item.type,
          item.subtype,
          item.levelLim,
          item.money,
          item.extra1,
          item.extra2,
          item.extra3,
          item.extra4,
          item.extra5,
          item.extra6,
          item.extra7,
          item.extra8,
          item.extra9,
          item.extra10,
          item.extra11,
          item.extra12,
          item.extra13,
          item.extra14,
          item.extra15,
        ].filter((value) => value && value !== "-1"),
      })),
    [itemCombinePreviewRows]
  );
  const searchedCombineOriginalPage = useMemo(() => {
    const firstRow = itemCombinePreviewRows[0]?.excelRow;
    if (!search.trim() || !firstRow) return null;
    return Math.max(0, Math.floor((Number(firstRow) - 3) / effectiveItemsPerPage));
  }, [itemCombinePreviewRows, effectiveItemsPerPage, search]);

  useEffect(() => {
    if (!window.electronAPI) {
      return;
    }

    refreshSources();
    loadProfiles();
    loadEffectDictionaries();
    loadEffectDictionary();
    checkExcelUpdatesOnStart();
    window.electronAPI
      .listRfIconSheets?.()
      .then((rows) => setRfIconSheets(Array.isArray(rows) ? rows : []))
      .catch(() => setRfIconSheets([]));

    return window.electronAPI.onImportProgress((progress) => {
      setImportProgress(progress);
    });
  }, []);

  useEffect(() => {
    const hasSavedColumns = hasSavedColumnsForSource(selectedSource);
    const savedColumns = loadColumnsForSource(selectedSource);
    const normalizedColumns = savedColumns.filter((column) =>
      availableColumnKeys.includes(column)
    );
    if (/combinetable/i.test(selectedSource) && availableColumnKeys.length > 0) {
      setVisibleColumns(availableColumnKeys.slice(0, 32));
    } else if (/boxitem/i.test(selectedSource) && availableColumnKeys.length > 0) {
      const first21 = Object.entries(sourceColumnOrdinals)
        .filter(([key]) => availableColumnKeys.includes(key as ColumnKey))
        .sort((a, b) => Number(a[1] || 0) - Number(b[1] || 0))
        .map(([key]) => key as ColumnKey)
        .slice(0, 21);
      setVisibleColumns(first21);
      saveColumnsForSource(selectedSource, first21);
    } else if (normalizedColumns.length > 0 && hasSavedColumns) {
      setVisibleColumns(normalizedColumns);
    } else {
      const fromSourceOrder = Object.entries(sourceColumnOrdinals)
        .filter(([key]) => availableColumnKeys.includes(key as ColumnKey))
        .sort((a, b) => Number(a[1] || 0) - Number(b[1] || 0))
        .map(([key]) => key as ColumnKey)
        .filter((column) => {
          const label = String(
            sourceColumnLabels[column] ||
              ITEM_COLUMNS.find((entry) => entry.key === column)?.label ||
              ""
          )
            .trim()
            .toLowerCase();
          return !DEFAULT_HIDDEN_LABELS.has(label);
        });

      if (/boxitem/i.test(selectedSource) && fromSourceOrder.length > 0) {
        setVisibleColumns(fromSourceOrder.slice(0, 21));
      } else if (fromSourceOrder.length > 0) {
        setVisibleColumns(fromSourceOrder);
      } else {
        const fallback = isItemLootingSelected
          ? ["name", "boss", "bossMap", "extra1", "extra2", "extra3", "extra4", "extra5"]
          : ["code", "icon", "name", "grade", "levelLim", "type", "subtype"];
        const fallbackKeys = fallback.filter((column) =>
          availableColumnKeys.includes(column as ColumnKey)
        ) as ColumnKey[];
        setVisibleColumns(fallbackKeys);
      }
    }
    setColumnWidths(loadColumnWidthsForSource(selectedSource));
    const loadedHidden = loadHiddenColumnOptionsForSource(selectedSource).filter(
      (column) => !(!isItemLootingSelected && column === "icon")
    );
    setHiddenColumnOptions(loadedHidden);
    saveHiddenColumnOptionsForSource(selectedSource, loadedHidden);
    setEditDrafts({});
    setTemplateAppliedMarks({});
    setUndoStack([]);
    setRedoStack([]);
    setActiveCell(null);
    setSelectedCellRange(null);
    loadSourceColumns(selectedSource);
  }, [
    availableColumnKeys,
    isItemLootingSelected,
    selectedSource,
    sourceColumnLabels,
    sourceColumnOrdinals,
  ]);

  useEffect(() => {
    if (!/boxitem/i.test(selectedSource)) {
      return;
    }
    setHiddenColumnOptions([]);
    saveHiddenColumnOptionsForSource(selectedSource, []);
  }, [selectedSource]);

  useEffect(() => {
    if (!window.electronAPI || !selectedSource) {
      setSourceSheets([]);
      setSelectedSheetName("");
      return;
    }

    let cancelled = false;
    window.electronAPI
      .listSourceSheets(selectedSource)
      .then((sheets) => {
        if (cancelled) {
          return;
        }
        const sorted = [...sheets].sort((a, b) => a.localeCompare(b));
        setSourceSheets(sorted);
        const current = extractSheetNameFromSource(selectedSource);
        if (current && sorted.includes(current)) {
          setSelectedSheetName(current);
          return;
        }
        if (sorted.includes("BoxItemOut")) {
          setSelectedSheetName("BoxItemOut");
          return;
        }
        setSelectedSheetName(sorted[0] ?? "");
      })
      .catch(() => {
        if (!cancelled) {
          setSourceSheets([]);
          setSelectedSheetName("");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSource]);

  useEffect(() => {
    if (!window.electronAPI || !isBoxItemOutSelected) {
      return;
    }
    let cancelled = false;
    const pendingCodes = boxRewards
      .map((reward) => reward.itemCode.trim().toLowerCase())
      .filter((code) => code && !itemMetaCache[code]);
    if (pendingCodes.length === 0) {
      return;
    }

    (async () => {
      const updates: Record<string, { name: string; civil: string; icon: string; sourceFile: string }> = {};
      for (const code of [...new Set(pendingCodes)]) {
      const meta = await resolveItemMetaByCode(code);
      updates[code] = meta;
      }
      if (cancelled) {
        return;
      }
      setItemMetaCache((current) => ({ ...current, ...updates }));
      setBoxRewards((current) =>
        current.map((reward) => {
          const key = reward.itemCode.trim().toLowerCase();
          const meta = updates[key];
          if (!meta) {
            return reward;
          }
          return {
            ...reward,
            itemName: reward.itemName || meta.name,
            civil: reward.civil || meta.civil,
          };
        })
      );
    })();

    return () => {
      cancelled = true;
    };
  }, [boxRewards, isBoxItemOutSelected, itemMetaCache]);

  useEffect(() => {
    if (!isBoxItemOutSelected) {
      return;
    }
    setBoxBuilderCode("");
    setBoxBuilderRace("all");
    setBoxRewards([
      {
        itemCode: "",
        itemName: "",
        itemIcon: "",
        itemSourceFile: "",
        quantity: "1",
        chancePercent: "",
        civil: "",
        status: "idle",
      },
    ]);
  }, [isBoxItemOutSelected, selectedSource]);

  useEffect(() => {
    setTemplateSourceBossKey((currentKey) => currentKey || bossGroups[0]?.key || "");
    setSelectedMapsForApply(visibleMapOptions);
  }, [bossGroups, visibleMapOptions]);

  useEffect(() => {
    if (!window.electronAPI || !isItemLootingSelected) {
      setAllMapOptions([]);
      return;
    }

    let cancelled = false;

    window.electronAPI
      .listItemColumnValues({
        sourceFile: selectedSource,
        field: "bossMap",
      })
      .then((values) => {
        if (cancelled) {
          return;
        }

        const maps = new Set<string>();

        for (const value of values) {
          for (const map of splitBossMaps(value)) {
            maps.add(map);
          }
        }

        const nextMaps = [...maps].sort((a, b) =>
          a.localeCompare(b, undefined, { sensitivity: "base" })
        );
        setAllMapOptions(nextMaps);
      })
      .catch(() => {
        if (!cancelled) {
          setAllMapOptions([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isItemLootingSelected, selectedSource]);

  useEffect(() => {
    if (
      (!/itemlooting/i.test(selectedSource) && !/boxitem/i.test(selectedSource)) ||
      hasSavedColumnWidthsForSource(selectedSource) ||
      items.length === 0
    ) {
      return;
    }

    setColumnWidths(getAutoColumnWidthsForItems(items, sourceColumnLabels));
  }, [items, selectedSource, sourceColumnLabels]);

  useEffect(() => {
    if (activeView !== "itemCombine" || !window.electronAPI) {
      return;
    }
    const codes = new Set<string>();
    for (const card of itemCombineRecipeCards) {
      for (const material of card.materials) {
        const code = String(material.item || "").trim();
        if (code && code !== "-1" && !isLinkedCombineCode(code)) {
          codes.add(code.toLowerCase());
        }
      }
      for (const result of card.results) {
        const code = String(result.code || "").trim();
        if (code && code !== "-1" && !isLinkedCombineCode(code)) {
          codes.add(code.toLowerCase());
        }
      }
    }
    for (const group of itemCombineGroupCards) {
      for (const entry of group.entries) {
        const code = String(entry || "").trim();
        if (code && code !== "-1" && !isLinkedCombineCode(code)) {
          codes.add(code.toLowerCase());
        }
      }
    }
    const pending = [...codes].filter((code) => !itemMetaCache[code]);
    if (pending.length === 0) {
      return;
    }
    let cancelled = false;
    (async () => {
      const updates: Record<string, { name: string; civil: string; icon: string; sourceFile: string }> = {};
      for (const code of pending.slice(0, 80)) {
        updates[code] = await resolveItemMetaByCode(code);
      }
      if (!cancelled) {
        setItemMetaCache((current) => ({ ...current, ...updates }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeView, itemCombineGroupCards, itemCombineRecipeCards, itemMetaCache]);

  useEffect(() => {
    if (!selectedSource) {
      return;
    }

    setRecentSources((currentSources) => {
      const nextSources = [
        selectedSource,
        ...currentSources.filter((sourceFile) => sourceFile !== selectedSource),
      ].slice(0, MAX_RECENT_SOURCES);
      saveRecentSources(nextSources);
      return nextSources;
    });
  }, [selectedSource]);

  useEffect(() => {
    const pageSizeForStorage = activeView === "itemCombine" ? itemCombineCardsPerPage : itemsPerPage;
    const savedPageKey =
      getItemPageStorageKey(selectedSource, search, filters, columnFilters) + `.${pageSizeForStorage}`;
    const hasSavedPage = window.localStorage.getItem(savedPageKey) !== null;
    if (activeView === "itemCombine" && selectedSource && !hasSavedPage && totalItems > 0) {
      setCurrentPage(Math.max(Math.ceil(totalItems / itemCombineCardsPerPage) - 1, 0));
      return;
    }
    setCurrentPage(loadSavedPage(selectedSource, search, filters, columnFilters, pageSizeForStorage));
  }, [activeView, selectedSource, search, filters, columnFilters, itemsPerPage, itemCombineCardsPerPage, totalItems]);

  useEffect(() => {
    if (!window.electronAPI) {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadItems();
    }, 200);

    return () => window.clearTimeout(timeout);
  }, [selectedSource, search, filters, columnFilters, currentPage, itemsPerPage, itemCombineCardsPerPage]);

  useEffect(() => {
    void loadSourceBackups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSource]);

  useEffect(() => {
    if (!window.electronAPI) {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadEffectDictionary();
    }, 200);

    return () => window.clearTimeout(timeout);
  }, [effectSearch, selectedDictionaryKey]);

  useEffect(() => {
    if (!window.electronAPI || !openColumnFilter) {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadColumnValues(openColumnFilter);
    }, 150);

    return () => window.clearTimeout(timeout);
  }, [openColumnFilter, columnValueSearch, selectedSource, search, filters, columnFilters]);

  useEffect(() => {
    if (!openColumnFilter) {
      return;
    }
    const term = columnValueSearch.trim().toLowerCase();
    if (!term) {
      return;
    }
    setDraftColumnValues(
      columnFilterValues.filter((value) =>
        String(value ?? "").toLowerCase().includes(term)
      )
    );
  }, [openColumnFilter, columnValueSearch, columnFilterValues]);

  useEffect(() => {
    if (!window.electronAPI) {
      return;
    }

    const query = quickLookup.trim();
    if (query.length < 2) {
      setQuickLookupResults([]);
      setIsQuickLookupLoading(false);
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      setIsQuickLookupLoading(true);
      try {
        const result = await window.electronAPI!.listItems({
          sourceFile: "",
          search: query,
          filters: [],
          columnFilters: {},
          limit: 15,
          offset: 0,
        });
        if (!cancelled) {
          setQuickLookupResults(result.items);
        }
      } catch {
        if (!cancelled) {
          setQuickLookupResults([]);
        }
      } finally {
        if (!cancelled) {
          setIsQuickLookupLoading(false);
        }
      }
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [quickLookup]);

  useEffect(() => {
    function syncViewportHeight() {
      const viewport = tableWrapRef.current?.clientHeight ?? 560;
      setTableViewportHeight(viewport);
    }

    syncViewportHeight();
    window.addEventListener("resize", syncViewportHeight);
    return () => window.removeEventListener("resize", syncViewportHeight);
  }, [selectedSource, activeView]);

  useEffect(() => {
    if (!isSourceDropdownOpen) {
      return;
    }
    function handleSourceDropdownOutside(event: MouseEvent) {
      if (
        sourceDropdownRef.current &&
        event.target instanceof Node &&
        !sourceDropdownRef.current.contains(event.target)
      ) {
        setIsSourceDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleSourceDropdownOutside);
    return () => document.removeEventListener("mousedown", handleSourceDropdownOutside);
  }, [isSourceDropdownOpen]);

  useEffect(() => {
    if (!openColumnFilter) {
      return;
    }

    function handleDocumentMouseDown(event: MouseEvent) {
      if (
        columnFilterRef.current &&
        event.target instanceof Node &&
        columnFilterRef.current.contains(event.target)
      ) {
        return;
      }

      setOpenColumnFilter(null);
    }

    document.addEventListener("mousedown", handleDocumentMouseDown);

    return () => {
      document.removeEventListener("mousedown", handleDocumentMouseDown);
    };
  }, [openColumnFilter]);

  useEffect(() => {
    function closeSuggestionDropdown() {
      setActiveSuggestionRow(null);
    }
    document.addEventListener("click", closeSuggestionDropdown);
    return () => document.removeEventListener("click", closeSuggestionDropdown);
  }, []);

  useEffect(() => {
    function handleGlobalF5(event: KeyboardEvent) {
      if (event.key === "F5") {
        event.preventDefault();
        void restartApp();
      }
    }
    window.addEventListener("keydown", handleGlobalF5);
    return () => window.removeEventListener("keydown", handleGlobalF5);
  }, []);

  async function importarItems() {
    if (!window.electronAPI) {
      setMessage("Importacao de Excel funciona apenas na janela do Electron.");
      return;
    }

    setIsImporting(true);
    setImportProgress({
      stage: "reading",
      sourceFile: "",
      fileIndex: 1,
      fileCount: 1,
      inserted: 0,
      total: 0,
      effectsInserted: 0,
    });
    setMessage("Importando Excel...");

    try {
      const result = await window.electronAPI.importItems();

      if (!result) {
        setMessage("Importacao cancelada.");
        return;
      }

      changeSelectedSource(result.fileName);
      setMessage(
        `Importados ${result.inserted} itens e ${result.effectsInserted} efeitos de ${result.fileName}. Linhas puladas: ${result.skippedRows}`
      );
      window.setTimeout(() => setMessage(""), 2500);
      setIsImporting(false);
      window.setTimeout(() => setImportProgress(null), 1200);
      await refreshSources();
      await checkExcelUpdatesOnStart();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao importar: ${error.message}`
          : "Erro ao importar Excel."
      );
    } finally {
      setIsImporting(false);
      window.setTimeout(() => setImportProgress(null), 1200);
    }
  }

  async function scanExcelDirectory() {
    if (!window.electronAPI) {
      setMessage("Importacao de pasta funciona apenas na janela do Electron.");
      return;
    }

    try {
      const result = await window.electronAPI.scanExcelDirectory();

      if (!result) {
        setMessage("Selecao de pasta cancelada.");
        return;
      }

      setScannedDirectory(result.directoryPath);
      setScannedExcelFiles(result.files);
      setSelectedExcelFiles(result.files.map((file) => file.filePath));
      setScannedExcelSearch("");
      setMessage(`Encontrados ${result.files.length} arquivos Excel.`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao ler pasta: ${error.message}`
          : "Erro ao ler pasta."
      );
    }
  }

  async function importBossDirectory() {
    if (!window.electronAPI) {
      setMessage("Importacao de bosses funciona apenas na janela do Electron.");
      return;
    }

    try {
      const result = await window.electronAPI.importBossDirectory();

      if (!result) {
        setMessage("Importacao de bosses cancelada.");
        return;
      }

      setMessage(
        `Bosses importados: ${result.inserted} codigos unicos em ${result.files} arquivos.`
      );
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao importar bosses: ${error.message}`
          : "Erro ao importar bosses."
      );
    }
  }

  async function importSelectedExcelFiles() {
    if (!window.electronAPI) {
      return;
    }

    const filesToImport = scannedExcelFiles
      .filter((file) => selectedExcelFiles.includes(file.filePath))
      .map((file) => ({
        filePath: file.filePath,
        sourceFile: file.relativePath,
      }));

    if (filesToImport.length === 0) {
      setMessage("Nenhum Excel selecionado para importar.");
      return;
    }

    setIsImporting(true);
    setImportProgress({
      stage: "reading",
      sourceFile: "",
      fileIndex: 1,
      fileCount: filesToImport.length,
      inserted: 0,
      total: 0,
      effectsInserted: 0,
    });
    setMessage(`Importando ${filesToImport.length} arquivos Excel...`);

    try {
      const result = await window.electronAPI.importExcelFiles(filesToImport);
      setMessage(
        `Importados ${result.inserted} itens e ${result.effectsInserted} efeitos de ${result.files.length} arquivos. Linhas puladas: ${result.skippedRows}`
      );
      window.setTimeout(() => setMessage(""), 2500);
      await window.electronAPI.saveExcelWatchState({
        directoryPath: scannedDirectory,
        files: filesToImport,
      });
      setScannedExcelFiles([]);
      setSelectedExcelFiles([]);
      setScannedExcelSearch("");
      await refreshSources();
      await loadItems();
      await checkExcelUpdatesOnStart();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao importar arquivos: ${error.message}`
          : "Erro ao importar arquivos."
      );
    } finally {
      setIsImporting(false);
      window.setTimeout(() => setImportProgress(null), 1200);
    }
  }

  async function importSelectedSheet() {
    if (!window.electronAPI || !selectedSource || !selectedSheetName) {
      return;
    }

    setIsImporting(true);
    setImportProgress({
      stage: "reading",
      sourceFile: selectedSource,
      fileIndex: 1,
      fileCount: 1,
      inserted: 0,
      total: 0,
      effectsInserted: 0,
    });

    try {
      const result = await window.electronAPI.importSourceSheet({
        sourceFile: selectedSource,
        sheetName: selectedSheetName,
      });
      changeSelectedSource(result.fileName);
      setMessage(
        `Aba ${selectedSheetName} importada: ${result.inserted} itens, ${result.effectsInserted} efeitos.`
      );
      await refreshSources();
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao importar aba: ${error.message}`
          : "Erro ao importar aba."
      );
    } finally {
      setIsImporting(false);
      window.setTimeout(() => setImportProgress(null), 1200);
    }
  }

  async function reimportCurrentSource() {
    if (!window.electronAPI?.reimportSourceFile || !selectedSource) {
      return;
    }

    setIsImporting(true);
    setImportProgress({
      stage: "reading",
      sourceFile: selectedSource,
      fileIndex: 1,
      fileCount: 1,
      inserted: 0,
      total: 0,
      effectsInserted: 0,
    });
    setMessage(`Reimportando ${formatSourceLabel(selectedSource)}...`);

    try {
      const result = await window.electronAPI.reimportSourceFile(selectedSource);
      if (!result) {
        setMessage("Reimportacao cancelada.");
        return;
      }
      setMessage(`Reimportado ${formatSourceLabel(result.fileName)}: ${result.inserted} itens.`);
      window.setTimeout(() => setMessage(""), 2500);
      await refreshSources();
      await loadItems();
      await checkExcelUpdatesOnStart();
    } catch (error) {
      setMessage(error instanceof Error ? `Erro ao reimportar: ${error.message}` : "Erro ao reimportar arquivo.");
    } finally {
      setIsImporting(false);
      window.setTimeout(() => setImportProgress(null), 1200);
    }
  }

  async function generateGrade1WeaponSocketCombines() {
    if (!window.electronAPI?.generateGrade1WeaponSocketCombines || isGeneratingCombineTool) {
      return;
    }

    setIsGeneratingCombineTool(true);
    try {
      const result = await window.electronAPI.generateGrade1WeaponSocketCombines();
      setMessage(
        `Grade 1 gerada: ${result.weapons} armas, ${result.groups} pares de grupos e ${result.combinesInserted} combines.`
      );
      await refreshSources();
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao gerar combines: ${error.message}`
          : "Erro ao gerar combines."
      );
    } finally {
      setIsGeneratingCombineTool(false);
    }
  }

  async function saveGeneratedWeaponSocketCombines() {
    if (!window.electronAPI?.saveGeneratedWeaponSocketCombines || isGeneratingCombineTool) {
      return;
    }

    setIsGeneratingCombineTool(true);
    try {
      const result = await window.electronAPI.saveGeneratedWeaponSocketCombines();
      setMessage(
        `Salvo no Excel: ${result.combineRows} linhas no CombineTable2 e ${result.linkedRows} linhas no LinkedCombines.`
      );
      loadSourceBackups();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao salvar no Excel: ${error.message}`
          : "Erro ao salvar no Excel."
      );
    } finally {
      setIsGeneratingCombineTool(false);
    }
  }

  function addBoxRewardLine() {
    setBoxRewards((current) => [
      ...current,
      {
        itemCode: "",
        itemName: "",
        itemIcon: "",
        itemSourceFile: "",
        quantity: "1",
        chancePercent: "",
        civil: "",
        status: "idle",
      },
    ]);
  }

  async function importarCsv() {
    if (!window.electronAPI?.importCsv) {
      setMessage("Importacao de CSV funciona apenas na janela do Electron.");
      return;
    }
    setIsImporting(true);
    setImportProgress({
      stage: "reading",
      sourceFile: "",
      fileIndex: 1,
      fileCount: 1,
      inserted: 0,
      total: 0,
      effectsInserted: 0,
    });
    setMessage("Importando CSV...");
    try {
      const result = await window.electronAPI.importCsv();
      if (!result) {
        setMessage("Importacao cancelada.");
        return;
      }
      changeSelectedSource(result.fileName);
      setMessage(
        `Importados ${result.inserted} itens de ${result.fileName}. Linhas puladas: ${result.skippedRows}`
      );
      window.setTimeout(() => setMessage(""), 2500);
      await refreshSources();
      await checkExcelUpdatesOnStart();
    } catch (error) {
      setMessage(error instanceof Error ? `Erro ao importar CSV: ${error.message}` : "Erro ao importar CSV.");
    } finally {
      setIsImporting(false);
      window.setTimeout(() => setImportProgress(null), 1200);
    }
  }

  function removeBoxRewardLine(index: number) {
    setBoxRewards((current) => current.filter((_value, currentIndex) => currentIndex !== index));
  }

  function updateBoxRewardLine(
    index: number,
    field: keyof Pick<BoxRewardDraft, "itemCode" | "quantity" | "chancePercent">,
    value: string
  ) {
    setBoxRewards((current) => {
      const next: BoxRewardDraft[] = current.map((reward, currentIndex) =>
        currentIndex === index ? { ...reward, [field]: value, status: "idle" as const } : reward
      );
      if (field !== "chancePercent") {
        return next;
      }

      const activeIndexes = next
        .map((reward, idx) => ({ idx, reward }))
        .filter(({ reward }) => reward.itemCode.trim() !== "")
        .map(({ idx }) => idx);
      if (activeIndexes.length <= 1 || !activeIndexes.includes(index)) {
        return next;
      }

      const desired = Math.max(0, Math.min(100, Number(value.replace(",", ".")) || 0));
      const others = activeIndexes.filter((idx) => idx !== index);
      const remaining = Math.max(0, 100 - desired);
      const previousOthers = others.map((idx) => {
        const raw = Number(String(next[idx].chancePercent ?? "").replace(",", "."));
        return Number.isFinite(raw) && raw > 0 ? raw : 0;
      });
      const previousTotal = previousOthers.reduce((sum, current) => sum + current, 0);
      let used = 0;
      for (let pos = 0; pos < others.length; pos += 1) {
        const idx = others[pos];
        let v = 0;
        if (pos === others.length - 1) {
          v = Number((remaining - used).toFixed(4));
        } else if (previousTotal > 0) {
          v = Number(((previousOthers[pos] / previousTotal) * remaining).toFixed(4));
          used += v;
        } else {
          const fallback = remaining / others.length;
          v = Number(fallback.toFixed(4));
          used += v;
        }
        next[idx] = { ...next[idx], chancePercent: String(Math.max(0, v)) };
      }
      next[index] = { ...next[index], chancePercent: String(desired) };
      return next;
    });
  }

  function getRaceCivil(race: BoxRace) {
    switch (race) {
      case "bell":
        return "11000";
      case "cora":
        return "00110";
      case "acc":
        return "00001";
      default:
        return "11111";
    }
  }

  function isCivilCompatible(civil: string, race: BoxRace) {
    const normalized = String(civil ?? "").trim();
    if (!normalized || race === "all") {
      return true;
    }
    return normalized === "11111" || normalized === getRaceCivil(race);
  }

  function normalizeBoxChanceTo10000(rewards: BoxRewardDraft[]) {
    const rows = rewards
      .map((reward) => ({
        ...reward,
        itemCode: reward.itemCode.trim(),
        quantity: reward.quantity.trim(),
        chancePercent: reward.chancePercent.trim(),
      }))
      .filter((reward) => reward.itemCode !== "");

    if (rows.length === 0) {
      return [];
    }

    const points = rows.map((reward) => {
      const percent = Number(reward.chancePercent.replace(",", "."));
      const numericPercent = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
      return Math.round((numericPercent / 100) * 10000);
    });
    const baseSum = points.reduce((sum, value) => sum + value, 0);
    points[points.length - 1] += 10000 - baseSum;

    return rows.map((reward, index) => ({
      itemCode: reward.itemCode,
      quantity: Math.max(0, Math.trunc(Number(reward.quantity.replace(",", ".")) || 0)),
      chance: Math.max(0, points[index]),
    }));
  }

  function convertCodeForRace(code: string, race: BoxRace) {
    const value = String(code ?? "");
    if (!value || race === "all" || value.length < 3) {
      return value;
    }

    const chars = value.split("");
    const token = race === "acc" ? "a" : race === "bell" ? "b" : "c";
    chars[2] = chars[2] === chars[2].toUpperCase() ? token.toUpperCase() : token;
    return chars.join("");
  }

  async function resolveItemMetaByCode(itemCode: string) {
    if (!window.electronAPI) {
      return { name: "", civil: "", icon: "", sourceFile: "" };
    }

    const code = itemCode.trim();
    if (!code) {
      return { name: "", civil: "", icon: "", sourceFile: "" };
    }

    const page = await window.electronAPI.listItems({
      sourceFile: "",
      search: "",
      filters: [{ field: "code", operator: "equals", value: code }],
      columnFilters: {},
      limit: 1000,
      offset: 0,
    });
    const matches = page.items.filter((item) => String(item.code).trim().toLowerCase() === code.toLowerCase());
    for (const item of matches) {
      const columns = await window.electronAPI.listSourceColumns(item.sourceFile);
      const civilColumn = columns.find((column) =>
        String(column.label ?? "").trim().toLowerCase() === "civil"
      );
      if (civilColumn) {
        const key = civilColumn.key;
        const value = String(item[key] ?? "").trim();
        if (value) {
          return {
            name: String(item.name ?? ""),
            civil: value,
            icon: String(item.icon ?? ""),
            sourceFile: String(item.sourceFile ?? ""),
          };
        }
      }
      const fallbackCivil = extractCivilPatternFromItem(item);
      if (fallbackCivil) {
        return {
          name: String(item.name ?? ""),
          civil: fallbackCivil,
          icon: String(item.icon ?? ""),
          sourceFile: String(item.sourceFile ?? ""),
        };
      }
    }

    const fallback = matches[0];
    return {
      name: fallback ? String(fallback.name ?? "") : "",
      civil: "",
      icon: fallback ? String(fallback.icon ?? "") : "",
      sourceFile: fallback ? String(fallback.sourceFile ?? "") : "",
    };
  }

  async function validateBoxRewardsCivil() {
    const nextRewards = [...boxRewards];
    for (let index = 0; index < nextRewards.length; index += 1) {
      const reward = nextRewards[index];
      if (!reward.itemCode.trim()) {
        continue;
      }
      const key = reward.itemCode.trim().toLowerCase();
      const cached = itemMetaCache[key];
      const meta = cached ?? (await resolveItemMetaByCode(reward.itemCode));
      if (!cached) {
        setItemMetaCache((current) => ({
          ...current,
          [key]: meta,
        }));
      }
      const civil = meta.civil;
      const compatible = isCivilCompatible(civil, boxBuilderRace);
      nextRewards[index] = {
        ...reward,
        itemName: meta.name,
        civil,
        status: civil ? (compatible ? "ok" : "invalid") : "unknown",
      };
    }
    setBoxRewards(nextRewards);
    const invalid = nextRewards.some((reward) => reward.status === "invalid");
    if (invalid) {
      setMessage("Ha recompensas com Civil incompativel para a raca selecionada.");
      return false;
    }
    return true;
  }

  async function createOrUpdateBoxFromBuilder() {
    if (!window.electronAPI || !selectedSource || !isBoxItemOutSelected) {
      return;
    }

    const boxCode = boxBuilderCode.trim();
    if (!boxCode) {
      setMessage("Informe o codigo da box.");
      return;
    }

    const isValidCivil = await validateBoxRewardsCivil();
    if (!isValidCivil) {
      return;
    }

    const normalizedRewards = normalizeBoxChanceTo10000(boxRewards);
    if (normalizedRewards.length === 0) {
      setMessage("Adicione ao menos uma recompensa.");
      return;
    }

    try {
      setIsSavingEdits(true);
      const result = await window.electronAPI.upsertBoxItemOutBox({
        sourceFile: selectedSource,
        sheetName: selectedSheetName || "BoxItemOut",
        boxCode,
        rewards: normalizedRewards,
      });
      setMessage(
        `Box ${boxCode} salva na linha ${result.row} com ${result.rewards} recompensas (chance total 10000).`
      );
      await checkExcelUpdatesOnStart();
      await refreshSources();
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao salvar box: ${error.message}`
          : "Erro ao salvar box."
      );
    } finally {
      setIsSavingEdits(false);
    }
  }

  async function loadExistingBoxToBuilder() {
    if (!window.electronAPI || !selectedSource || !isBoxItemOutSelected) {
      return;
    }

    const boxCode = boxBuilderCode.trim();
    if (!boxCode) {
      setMessage("Informe o codigo da box para carregar.");
      return;
    }

    try {
      const page = await window.electronAPI.listItems({
        sourceFile: selectedSource,
        filters: [{ field: "code", operator: "equals", value: boxCode }],
        limit: 1,
        offset: 0,
      });
      const item = page.items[0];
      if (!item) {
        setMessage(`Box ${boxCode} nao encontrada nesta aba.`);
        return;
      }

      const loaded: BoxRewardDraft[] = [];
      for (let slot = 0; slot < 5; slot += 1) {
        const base = 2 + slot * 3;
        const itemCode = String(item[`extra${base}` as ColumnKey] ?? "").trim();
        const qty = String(item[`extra${base + 1}` as ColumnKey] ?? "").trim();
        const chance = String(item[`extra${base + 2}` as ColumnKey] ?? "").trim();
        if (!itemCode || itemCode === "-1") {
          continue;
        }
        const chanceNum = Number(chance.replace(",", "."));
        loaded.push({
          itemCode,
          itemName: "",
          itemIcon: "",
          itemSourceFile: "",
          quantity: qty === "-1" ? "0" : qty,
          chancePercent:
            Number.isFinite(chanceNum) && chanceNum >= 0
              ? String(Math.round((chanceNum / 10000) * 10000) / 100)
              : "",
          civil: "",
          status: "idle",
        });
      }

      setBoxRewards(
        loaded.length > 0
          ? loaded
          : [
              {
                itemCode: "",
                itemName: "",
                itemIcon: "",
                itemSourceFile: "",
                quantity: "1",
                chancePercent: "",
                civil: "",
                status: "idle",
              },
            ]
      );
      setMessage(`Box ${boxCode} carregada para edicao.`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao carregar box: ${error.message}`
          : "Erro ao carregar box."
      );
    }
  }

  async function replicateBoxForRaces(targetRaces: BoxRace[]) {
    if (!window.electronAPI || !selectedSource || !isBoxItemOutSelected) {
      return;
    }

    const sourceCode = boxBuilderCode.trim();
    if (!sourceCode) {
      setMessage("Informe o codigo base da box.");
      return;
    }

    const normalizedRewards = normalizeBoxChanceTo10000(boxRewards);
    if (normalizedRewards.length === 0) {
      setMessage("Adicione recompensas antes de replicar.");
      return;
    }

    try {
      setIsSavingEdits(true);
      let applied = 0;
      for (const race of targetRaces) {
        const nextCode = convertCodeForRace(sourceCode, race);
        const nextRewards = normalizedRewards.map((reward) => ({
          ...reward,
          itemCode: convertCodeForRace(reward.itemCode, race),
        }));
        await window.electronAPI.upsertBoxItemOutBox({
          sourceFile: selectedSource,
          sheetName: selectedSheetName || "BoxItemOut",
          boxCode: nextCode,
          rewards: nextRewards,
        });
        applied += 1;
      }
      setMessage(`Replicacao concluida em ${applied} box(es).`);
      await refreshSources();
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao replicar box: ${error.message}`
          : "Erro ao replicar box."
      );
    } finally {
      setIsSavingEdits(false);
    }
  }

  function toggleScannedExcelFile(filePath: string) {
    setSelectedExcelFiles((currentFiles) =>
      currentFiles.includes(filePath)
        ? currentFiles.filter((currentFile) => currentFile !== filePath)
        : [...currentFiles, filePath]
    );
  }

  function toggleAllScannedExcelFiles() {
    const visibleFiles = filteredScannedExcelFiles;
    setSelectedExcelFiles((currentFiles) =>
      visibleFiles.length > 0 &&
      visibleFiles.every((file) => currentFiles.includes(file.filePath))
        ? currentFiles.filter(
            (filePath) => !visibleFiles.some((file) => file.filePath === filePath)
          )
        : [
            ...new Set([
              ...currentFiles,
              ...visibleFiles.map((file) => file.filePath),
            ]),
          ]
    );
  }

  async function loadProfiles() {
    if (!window.electronAPI?.listProfiles) {
      setMessage("API de perfis indisponivel. Reinicie o app pelo Electron.");
      return;
    }
    try {
      const nextProfiles = await window.electronAPI.listProfiles();
      setProfiles(nextProfiles);
      setActiveProfileId(nextProfiles.find((profile) => profile.isActive)?.id ?? "");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao carregar perfis: ${error.message}`
          : "Erro ao carregar perfis."
      );
    }
  }

  async function createProfile() {
    if (!window.electronAPI?.createProfile) {
      setMessage("Funcao de criar perfil indisponivel. Reinicie o app.");
      return;
    }

    const name = profileNameDraft.trim();
    if (!name) {
      setMessage("Digite um nome para criar perfil.");
      return;
    }

    try {
      await window.electronAPI.createProfile({
        name,
        cloneCurrent: true,
      });
      await loadProfiles();
      setProfileNameDraft("");
      setMessage(`Perfil "${name}" criado.`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao criar perfil: ${error.message}`
          : "Erro ao criar perfil."
      );
    }
  }

  async function switchProfile(profileId: string) {
    if (!window.electronAPI?.switchProfile || !profileId || profileId === activeProfileId) {
      return;
    }
    try {
      setMessage("Trocando perfil...");
      await window.electronAPI.switchProfile(profileId);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao trocar perfil: ${error.message}`
          : "Erro ao trocar perfil."
      );
    }
  }

  async function renameProfile() {
    if (!window.electronAPI?.renameProfile || !activeProfileId) {
      setMessage("Funcao de renomear perfil indisponivel. Reinicie o app.");
      return;
    }

    const name = profileNameDraft.trim();
    if (!name) {
      setMessage("Digite um nome para renomear perfil.");
      return;
    }

    try {
      await window.electronAPI.renameProfile({
        profileId: activeProfileId,
        name,
      });
      await loadProfiles();
      setProfileNameDraft("");
      setMessage(`Perfil renomeado para "${name}".`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao renomear perfil: ${error.message}`
          : "Erro ao renomear perfil."
      );
    }
  }

  async function duplicateProfile() {
    if (!window.electronAPI?.duplicateProfile || !activeProfileId) {
      setMessage("Funcao de duplicar perfil indisponivel. Reinicie o app.");
      return;
    }

    const name = profileNameDraft.trim();
    if (!name) {
      setMessage("Digite um nome para duplicar perfil.");
      return;
    }

    try {
      await window.electronAPI.duplicateProfile({
        sourceProfileId: activeProfileId,
        name,
      });
      await loadProfiles();
      setProfileNameDraft("");
      setMessage(`Perfil "${name}" duplicado.`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao duplicar perfil: ${error.message}`
          : "Erro ao duplicar perfil."
      );
    }
  }

  async function deleteProfile() {
    if (!window.electronAPI?.deleteProfile || !activeProfileId) {
      setMessage("Funcao de excluir perfil indisponivel. Reinicie o app.");
      return;
    }

    const current = profiles.find((profile) => profile.id === activeProfileId);
    const confirmed = window.confirm(
      `Excluir o perfil "${current?.name ?? activeProfileId}"?`
    );
    if (!confirmed) {
      return;
    }

    try {
      setMessage("Excluindo perfil...");
      await window.electronAPI.deleteProfile(activeProfileId);
      await loadProfiles();
      setProfileAction(null);
      setProfileNameDraft("");
      setMessage(`Perfil "${current?.name ?? activeProfileId}" excluido.`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao excluir perfil: ${error.message}`
          : "Erro ao excluir perfil."
      );
    }
  }

  async function restartApp() {
    if (!window.electronAPI) {
      setMessage("Reinicio disponivel apenas no Electron.");
      return;
    }

    try {
      setMessage("Reiniciando app...");
      if (window.electronAPI.restartApp) {
        try {
          await window.electronAPI.restartApp();
          return;
        } catch (error) {
          const text = error instanceof Error ? error.message : String(error);
          if (!/No handler registered for 'restart-app'/.test(text)) {
            throw error;
          }
        }
      }

      // Fallback para builds com preload antigo sem restartApp.
      if (window.electronAPI.switchProfile && activeProfileId) {
        await window.electronAPI.switchProfile(activeProfileId);
        return;
      }

      setMessage("Funcao de reinicio indisponivel. Reinicie pelo terminal.");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao reiniciar: ${error.message}`
          : "Erro ao reiniciar app."
      );
    }
  }

  async function confirmProfileAction() {
    if (profileAction === "new") {
      await createProfile();
    } else if (profileAction === "rename") {
      await renameProfile();
    } else if (profileAction === "duplicate") {
      await duplicateProfile();
    }
    setProfileAction(null);
  }

  function startProfileAction(action: "new" | "rename" | "duplicate") {
    const current = profiles.find((profile) => profile.id === activeProfileId);
    if (action === "rename") {
      setProfileNameDraft(current?.name ?? "");
    } else if (action === "duplicate") {
      setProfileNameDraft(current ? `${current.name} (copia)` : "");
    } else {
      setProfileNameDraft("");
    }
    setProfileAction(action);
  }

  function cancelProfileAction() {
    setProfileAction(null);
    setProfileNameDraft("");
  }

  async function refreshSources() {
    if (!window.electronAPI) {
      return;
    }

    const nextSources = await window.electronAPI.listSourceFiles();
    setSources(nextSources);

    const lastSource = loadLastSelectedSource();
    const nextScopedSources = nextSources.filter((source) =>
      sourceBelongsToActiveView(source.sourceFile)
    );

    if (!selectedSource && nextScopedSources.length > 0) {
      const preferred =
        (lastSource &&
          nextScopedSources.find((source) => source.sourceFile === lastSource)?.sourceFile) ||
        nextScopedSources[0].sourceFile;
      changeSelectedSource(preferred);
      return;
    }

    if (
      selectedSource &&
      !nextSources.some((source) => source.sourceFile === selectedSource)
    ) {
      const fallback =
        (lastSource &&
          nextScopedSources.find((source) => source.sourceFile === lastSource)?.sourceFile) ||
        nextScopedSources[0]?.sourceFile ||
        "";
      setSelectedSource(fallback);
    }
  }

  async function loadSourceColumns(sourceFile: string) {
    if (!window.electronAPI || !sourceFile) {
      setSourceColumnLabels({});
      setSourceColumnOrdinals({});
      return;
    }

    try {
      const columns = await window.electronAPI.listSourceColumns(sourceFile);
      const supported = columns.filter((column) =>
        ITEM_COLUMNS.some((itemColumn) => itemColumn.key === column.key)
      );
      setSourceColumnLabels(
        Object.fromEntries(
          supported.map((column) => [column.key, column.label])
        )
      );
      setSourceColumnOrdinals(
        Object.fromEntries(supported.map((column) => [column.key, Number(column.ordinal) || 0]))
      );
    } catch {
      setSourceColumnLabels({});
      setSourceColumnOrdinals({});
    }
  }

  async function deleteSelectedSource() {
    if (!window.electronAPI || !selectedSource) {
      return;
    }

    const sourceLabel = formatSourceLabel(selectedSource);
    const confirmed = window.confirm(
      `Remover "${sourceLabel}" do banco? Os itens importados desse arquivo deixam de aparecer na lista.`
    );

    if (!confirmed) {
      return;
    }

    try {
      await window.electronAPI.deleteSourceFile(selectedSource);
      setMessage(`${sourceLabel} removido do banco.`);
      setIsSourceDropdownOpen(false);
      saveLastSelectedSource("");
      const nextSources = sources.filter((source) => source.sourceFile !== selectedSource);
      const nextScopedSources = nextSources.filter((source) =>
        sourceBelongsToActiveView(source.sourceFile)
      );
      const nextSelected = nextScopedSources[0]?.sourceFile || "";
      setSources(nextSources);
      setRecentSources((current) => {
        const next = current.filter((sourceFile) => sourceFile !== selectedSource);
        saveRecentSources(next);
        return next;
      });
      if (nextSelected) {
        changeSelectedSource(nextSelected);
      } else {
        setSelectedSource("");
      }
      if (nextSelected) {
        saveLastSelectedSource(nextSelected);
      }
      setColumnFilters({});
      setOpenColumnFilter(null);
      setCurrentPage(0);
      await refreshSources();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao remover arquivo: ${error.message}`
          : "Erro ao remover arquivo."
      );
    }
  }

  function toggleBulkSource(sourceFile: string) {
    setBulkSelectedSources((current) =>
      current.includes(sourceFile)
        ? current.filter((value) => value !== sourceFile)
        : [...current, sourceFile]
    );
  }

  async function deleteMultipleSources(sourceFiles: string[]) {
    if (!window.electronAPI || sourceFiles.length === 0) {
      return;
    }

    const confirmed = window.confirm(`Remover ${sourceFiles.length} arquivos do banco?`);
    if (!confirmed) {
      return;
    }

    try {
      const remainingSources = sources.filter(
        (source) => !sourceFiles.includes(source.sourceFile)
      );
      for (const sourceFile of sourceFiles) {
        await window.electronAPI.deleteSourceFile(sourceFile);
      }
      setMessage(`${sourceFiles.length} arquivos removidos do banco.`);
      setIsSourceDropdownOpen(false);
      setBulkSelectedSources([]);
      saveLastSelectedSource("");
      setSources(remainingSources);
      setRecentSources((current) => {
        const removed = new Set(sourceFiles);
        const next = current.filter((sourceFile) => !removed.has(sourceFile));
        saveRecentSources(next);
        return next;
      });
      const nextSelected =
        remainingSources.find((source) => sourceBelongsToActiveView(source.sourceFile))
          ?.sourceFile || "";
      if (nextSelected) {
        changeSelectedSource(nextSelected);
        saveLastSelectedSource(nextSelected);
      } else {
        setSelectedSource("");
      }
      await refreshSources();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao remover arquivos: ${error.message}`
          : "Erro ao remover arquivos."
      );
    }
  }

  async function loadEffectDictionaries() {
    if (!window.electronAPI) {
      return;
    }

    const nextDictionaries = await window.electronAPI.listEffectDictionaries();
    setDictionaries(nextDictionaries);
  }

  async function changeSourceDictionary(dictionaryKey: string) {
    if (!window.electronAPI || !selectedSource) {
      return;
    }

    try {
      await window.electronAPI.setSourceDictionary(selectedSource, dictionaryKey);
      setMessage(`${selectedSource} agora usa ${getDictionaryLabel(dictionaryKey)}.`);
      await refreshSources();
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao alterar dicionario: ${error.message}`
          : "Erro ao alterar dicionario."
      );
    }
  }

  async function loadItems() {
    if (!window.electronAPI) {
      return;
    }

    setIsLoadingItems(true);

    try {
      const filterPayload = filters.map(({ field, operator, value }) => ({
        field,
        operator,
        value,
      }));

      const nextItems = await window.electronAPI.listItems({
        sourceFile: selectedSource,
        search,
        filters: filterPayload,
        columnFilters,
        sortField: isGearScoreCsvSelected ? csvSortField : undefined,
        sortDirection: isGearScoreCsvSelected ? csvSortDirection : undefined,
        limit: effectiveItemsPerPage,
        offset: currentPage * effectiveItemsPerPage,
      });
      const normalized = /boxitem/i.test(selectedSource)
        ? nextItems.items.filter((item) => {
            const code = String(item.code ?? "").trim();
            return code !== "" && !/^row-\d+$/i.test(code);
          })
        : nextItems.items;
      const nextTotal = /boxitem/i.test(selectedSource)
        ? Math.max(nextItems.total - (nextItems.items.length - normalized.length), 0)
        : nextItems.total;
      setItems(normalized);
      setTotalItems(nextTotal);
      const maxPage = Math.max(Math.ceil(nextTotal / effectiveItemsPerPage) - 1, 0);

      if (currentPage > maxPage) {
        goToPage(maxPage);
      }
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao listar itens: ${error.message}`
          : "Erro ao listar itens."
      );
    } finally {
      setIsLoadingItems(false);
    }
  }

  function toggleColumn(column: ColumnKey) {
    const nextColumns = visibleColumns.includes(column)
      ? visibleColumns.filter((key) => key !== column)
      : [...visibleColumns, column];

    const safeColumns = nextColumns.length > 0 ? nextColumns : visibleColumns;
    setVisibleColumns(safeColumns);
    saveColumnsForSource(selectedSource, safeColumns);
  }

  function hideColumnOption(column: ColumnKey) {
    setHiddenColumnOptions((currentOptions) => {
      if (currentOptions.includes(column)) {
        return currentOptions;
      }

      const nextOptions = [...currentOptions, column];
      saveHiddenColumnOptionsForSource(selectedSource, nextOptions);
      return nextOptions;
    });

    if (visibleColumns.includes(column)) {
      const nextVisibleColumns = visibleColumns.filter((key) => key !== column);
      const safeColumns =
        nextVisibleColumns.length > 0 ? nextVisibleColumns : visibleColumns;
      setVisibleColumns(safeColumns);
      saveColumnsForSource(selectedSource, safeColumns);
    }
  }

  function restoreColumnOption(column: ColumnKey) {
    setHiddenColumnOptions((currentOptions) => {
      const nextOptions = currentOptions.filter((key) => key !== column);
      saveHiddenColumnOptionsForSource(selectedSource, nextOptions);
      return nextOptions;
    });
  }

  function changeSelectedSource(sourceFile: string) {
    saveFilterStateForSource(selectedSource, search, filters, columnFilters);
    const savedFilterState = loadFilterStateForSource(sourceFile);

    setSelectedSource(sourceFile);
    saveLastSelectedSource(sourceFile);
    setSearch(savedFilterState.search);
    setFilters(savedFilterState.filters);
    setColumnFilters(savedFilterState.columnFilters);
    setOpenColumnFilter(null);
    setColumnValueSearch("");
    setColumnFilterValues([]);
    setDraftColumnValues([]);
    setCurrentPage(0);
  }

  function closeRecentSource(sourceFile: string) {
    setRecentSources((currentSources) => {
      const nextSources = currentSources.filter(
        (currentSource) => currentSource !== sourceFile
      );
      saveRecentSources(nextSources);
      return nextSources;
    });
  }

  function toggleColumnPanel() {
    setIsColumnPanelCollapsed((currentValue) => {
      const nextValue = !currentValue;
      saveColumnPanelCollapsed(nextValue);
      return nextValue;
    });
  }

  function toggleFilterPanel() {
    setIsFilterPanelCollapsed((currentValue) => {
      const nextValue = !currentValue;
      saveFilterPanelCollapsed(nextValue);
      return nextValue;
    });
  }

  function addFilter() {
    setFilters((currentFilters) => [
      ...currentFilters,
      {
        id: Date.now(),
        field: "name",
        operator: "contains",
        value: "",
      },
    ]);
  }

  function updateFilter(
    id: number,
    changes: Partial<Omit<DraftFilter, "id">>
  ) {
    setFilters((currentFilters) =>
      currentFilters.map((filter) =>
        filter.id === id ? { ...filter, ...changes } : filter
      )
    );
  }

  function removeFilter(id: number) {
    setFilters((currentFilters) =>
      currentFilters.filter((filter) => filter.id !== id)
    );
  }

  function clearFilters() {
    setSearch("");
    setFilters([]);
    setColumnFilters({});
    setCurrentPage(0);
  }

  async function loadColumnValues(column: ColumnKey) {
    if (!window.electronAPI) {
      return;
    }

    setIsLoadingColumnValues(true);
    const lookupColumnFilters = getColumnFiltersForLookup(columnFilters, column);

    try {
      const values = await window.electronAPI.listItemColumnValues({
        sourceFile: selectedSource,
        search,
        filters: filters.map(({ field, operator, value }) => ({
          field,
          operator,
          value,
        })),
        columnFilters: lookupColumnFilters,
        field: column,
        valueSearch: columnValueSearch,
      });
      const fallbackValues =
        values.length === 0 &&
        (search || filters.length > 0 || Object.keys(lookupColumnFilters).length > 0)
          ? await window.electronAPI.listItemColumnValues({
              sourceFile: selectedSource,
              field: column,
              valueSearch: columnValueSearch,
            })
          : values;
      const activeValues = columnFilters[column];

      setColumnFilterValues(fallbackValues);
      setDraftColumnValues(
        activeValues && activeValues.length > 0 ? activeValues : fallbackValues
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao carregar filtro: ${error.message}`
          : "Erro ao carregar filtro."
      );
    } finally {
      setIsLoadingColumnValues(false);
    }
  }

  function openFilterForColumn(column: ColumnKey) {
    setOpenColumnFilter((currentColumn) => {
      const nextColumn = currentColumn === column ? null : column;

      if (nextColumn) {
        setColumnValueSearch("");
        setColumnFilterValues([]);
        setDraftColumnValues(columnFilters[column] ?? []);
      }

      return nextColumn;
    });
  }

  function toggleDraftColumnValue(value: string) {
    setDraftColumnValues((currentValues) =>
      currentValues.includes(value)
        ? currentValues.filter((currentValue) => currentValue !== value)
        : [...currentValues, value]
    );
  }

  function applyColumnFilter(column: ColumnKey) {
    setColumnFilters((currentFilters) => {
      const nextFilters = { ...currentFilters };
      const isAllSelectedVisible =
        draftColumnValues.length === columnFilterValues.length &&
        columnFilterValues.every((value) => draftColumnValues.includes(value));
      const hasSearchTerm = columnValueSearch.trim().length > 0;

      if (draftColumnValues.length === 0 || (isAllSelectedVisible && !hasSearchTerm)) {
        delete nextFilters[column];
      } else {
        nextFilters[column] = draftColumnValues;
      }

      return nextFilters;
    });
    setCurrentPage(0);
    setOpenColumnFilter(null);
  }

  function clearColumnFilter(column: ColumnKey) {
    setColumnFilters((currentFilters) => {
      const nextFilters = { ...currentFilters };
      delete nextFilters[column];
      return nextFilters;
    });
    setDraftColumnValues(columnFilterValues);
    setCurrentPage(0);
    setOpenColumnFilter(null);
  }

  function isColumnFilterable(column: ColumnKey) {
    return column !== "excelRow";
  }

  function toggleGearCsvSort(column: ColumnKey) {
    if (!isGearScoreCsvSelected) {
      return;
    }
    setCurrentPage(0);
    if (csvSortField !== column) {
      setCsvSortField(column);
      setCsvSortDirection("asc");
      return;
    }
    setCsvSortDirection((current) => (current === "asc" ? "desc" : "asc"));
  }

  useEffect(() => {
    if (!isGearScoreCsvSelected) {
      return;
    }
    void loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [csvSortField, csvSortDirection, isGearScoreCsvSelected]);

  async function hydrateBoxRewardMeta(index: number, codeValue: string) {
    const key = codeValue.trim().toLowerCase();
    if (!key) {
      setBoxRewards((current) =>
        current.map((reward, currentIndex) =>
          currentIndex === index
            ? { ...reward, itemName: "", itemIcon: "", itemSourceFile: "", civil: "", status: "idle" }
            : reward
        )
      );
      return;
    }
    const suggestion = (boxCodeSuggestions[index] || []).find(
      (item) => String(item.code || "").trim().toLowerCase() === key
    );
    const civilFromSuggestion = suggestion ? await getCivilFromItem(suggestion) : "";
    const cached = itemMetaCache[key];
    const meta =
      civilFromSuggestion && suggestion
        ? {
            name: String(suggestion.name || ""),
            civil: civilFromSuggestion,
            icon: String(suggestion.icon || ""),
            sourceFile: String(suggestion.sourceFile || ""),
          }
        : cached ?? (await resolveItemMetaByCode(codeValue));
    if (!cached) {
      setItemMetaCache((current) => ({ ...current, [key]: meta }));
    }
    const compatible = isCivilCompatible(meta.civil, boxBuilderRace);
    setBoxRewards((current) =>
      current.map((reward, currentIndex) =>
        currentIndex === index
          ? {
              ...reward,
              itemName: meta.name || reward.itemName,
              itemIcon: meta.icon || reward.itemIcon,
              itemSourceFile: meta.sourceFile || reward.itemSourceFile,
              civil: meta.civil || reward.civil,
              status: meta.civil ? (compatible ? "ok" : "invalid") : "unknown",
            }
          : reward
      )
    );
  }

  async function loadBoxCodeSuggestions(index: number, query: string) {
    if (!window.electronAPI) {
      return;
    }
    const term = query.trim();
    if (term.length < 3) {
      setBoxCodeSuggestions((current) => ({ ...current, [index]: [] }));
      return;
    }
    const normalizedTerm = term.toLowerCase();
    const baseKey = normalizedTerm.slice(0, 3);

    if (boxCodeSuggestionCache[baseKey]) {
      let filtered = boxCodeSuggestionCache[baseKey]
        .filter((item) => String(item.code || "").trim().toLowerCase().startsWith(normalizedTerm))
        .slice(0, 12);
      if (filtered.length === 0 && normalizedTerm.length > 3) {
        const result = await window.electronAPI.listItems({
          sourceFile: "",
          search: "",
          filters: [{ field: "code", operator: "startsWith", value: normalizedTerm }],
          columnFilters: {},
          limit: 300,
          offset: 0,
        });
        filtered = result.items
          .filter((item) => !/boxitem/i.test(String(item.sourceFile || "")))
          .filter(
            (item, position, list) =>
              list.findIndex(
                (candidate) =>
                  String(candidate.code || "").trim().toLowerCase() ===
                  String(item.code || "").trim().toLowerCase()
              ) === position
          )
          .slice(0, 12);
      }
      setBoxCodeSuggestions((current) => ({ ...current, [index]: filtered }));
      void enrichSuggestionCivil(filtered);
      return;
    }
    try {
      const result = await window.electronAPI.listItems({
        sourceFile: "",
        search: "",
        filters: [{ field: "code", operator: "startsWith", value: baseKey }],
        columnFilters: {},
        limit: 1000,
        offset: 0,
      });
      const baseFiltered = result.items
        .filter((item) => {
          const code = String(item.code || "").trim().toLowerCase();
          if (!code) {
            return false;
          }
          if (!code.startsWith(baseKey)) {
            return false;
          }
          if (/boxitem/i.test(String(item.sourceFile || ""))) {
            return false;
          }
          return true;
        })
        .filter(
          (item, position, list) =>
            list.findIndex(
              (candidate) =>
                String(candidate.code || "").trim().toLowerCase() ===
                String(item.code || "").trim().toLowerCase()
            ) === position
        );
      setBoxCodeSuggestionCache((current) => ({ ...current, [baseKey]: baseFiltered }));
      const filtered = baseFiltered
        .filter((item) => String(item.code || "").trim().toLowerCase().startsWith(normalizedTerm))
        .slice(0, 12);
      setBoxCodeSuggestions((current) => ({ ...current, [index]: filtered }));
      void enrichSuggestionCivil(filtered);
    } catch {
      setBoxCodeSuggestions((current) => ({ ...current, [index]: [] }));
    }
  }

  async function enrichSuggestionCivil(itemsForCivil: LootItem[]) {
    const quickCivilUpdates: Record<string, string> = {};
    for (const item of itemsForCivil) {
      const codeKey = String(item.code || "").trim().toLowerCase();
      if (!codeKey || suggestionCivilByCode[codeKey]) {
        continue;
      }
      const civilFromItem = await getCivilFromItem(item);
      if (civilFromItem) {
        quickCivilUpdates[codeKey] = civilFromItem;
      }
    }
    if (Object.keys(quickCivilUpdates).length > 0) {
      setSuggestionCivilByCode((current) => ({ ...current, ...quickCivilUpdates }));
    }

    const pendingCodes = itemsForCivil
      .map((item) => String(item.code || "").trim().toLowerCase())
      .filter((code) => code && !itemMetaCache[code] && !quickCivilUpdates[code]);
    if (pendingCodes.length === 0) {
      return;
    }
    const updates: Record<string, { name: string; civil: string; icon: string; sourceFile: string }> = {};
    for (const code of pendingCodes.slice(0, 12)) {
      const meta = await resolveItemMetaByCode(code);
      updates[code] = meta;
    }
    setItemMetaCache((current) => ({ ...current, ...updates }));
    const metaCivilUpdates = Object.fromEntries(
      Object.entries(updates)
        .filter(([, meta]) => String(meta.civil || "").trim() !== "")
        .map(([code, meta]) => [code, String(meta.civil || "").trim().slice(0, 5)])
    );
    if (Object.keys(metaCivilUpdates).length > 0) {
      setSuggestionCivilByCode((current) => ({ ...current, ...metaCivilUpdates }));
    }
  }

  async function getCivilFromItem(item: LootItem) {
    const sourceFile = String(item.sourceFile || "");
    if (!sourceFile || !window.electronAPI) {
      return "";
    }
    let civilKey = sourceCivilKeyCache[sourceFile];
    if (civilKey === undefined) {
      const columns = await window.electronAPI.listSourceColumns(sourceFile);
      const civilColumn = columns.find((column) =>
        String(column.label || "").trim().toLowerCase() === "civil"
      );
      civilKey = (civilColumn?.key as ColumnKey | undefined) ?? "";
      setSourceCivilKeyCache((current) => ({ ...current, [sourceFile]: civilKey || "" }));
    }
    if (!civilKey) {
      return extractCivilPatternFromItem(item);
    }
    const direct = String(item[civilKey] ?? "").trim().slice(0, 5);
    return direct || extractCivilPatternFromItem(item);
  }

  function extractCivilPatternFromItem(item: LootItem) {
    const keys: ColumnKey[] = [
      "extra1","extra2","extra3","extra4","extra5",
      "extra6","extra7","extra8","extra9","extra10",
      "extra11","extra12","extra13","extra14","extra15",
    ];
    for (const key of keys) {
      const value = String(item[key] ?? "").trim();
      if (/^[01]{5,}$/.test(value)) {
        return value.slice(0, 5);
      }
    }
    return "";
  }

  async function loadEffectDictionary() {
    if (!window.electronAPI) {
      return;
    }

    setIsLoadingEffects(true);

    try {
      const entries = await window.electronAPI.listEffectDictionary({
        search: effectSearch,
        dictionaryKey: selectedDictionaryKey,
      });

      setEffectEntries(entries.map(toDraftEffectEntry));
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao carregar dicionario: ${error.message}`
          : "Erro ao carregar dicionario."
      );
    } finally {
      setIsLoadingEffects(false);
    }
  }

  function addEffectEntry() {
    setEffectEntries((currentEntries) => [
      {
        draftId: `new-${Date.now()}`,
        dictionaryKey: selectedDictionaryKey,
        itemType: "",
        effCode: "",
        name: "",
        description: "",
        unitHint: "",
      },
      ...currentEntries,
    ]);
  }

  function updateEffectEntry(
    draftId: string,
    changes: Partial<EffectDictionaryEntry>
  ) {
    setEffectEntries((currentEntries) =>
      currentEntries.map((entry) =>
        entry.draftId === draftId ? { ...entry, ...changes } : entry
      )
    );
  }

  async function saveEffectEntry(entry: DraftEffectEntry) {
    if (!window.electronAPI) {
      return;
    }

    try {
      await window.electronAPI.saveEffectDictionaryEntry({
        id: entry.id,
        dictionaryKey: entry.dictionaryKey,
        itemType: entry.itemType,
        effCode: entry.effCode,
        name: entry.name,
        description: entry.description,
        unitHint: entry.unitHint,
      });
      setMessage(`Efeito ${entry.effCode} salvo no dicionario.`);
      await loadEffectDictionary();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao salvar efeito: ${error.message}`
          : "Erro ao salvar efeito."
      );
    }
  }

  async function deleteEffectEntry(entry: DraftEffectEntry) {
    if (!window.electronAPI) {
      return;
    }

    if (!entry.id) {
      setEffectEntries((currentEntries) =>
        currentEntries.filter((currentEntry) => currentEntry.draftId !== entry.draftId)
      );
      return;
    }

    try {
      await window.electronAPI.deleteEffectDictionaryEntry(entry.id);
      setMessage(`Efeito ${entry.effCode} removido do dicionario.`);
      await loadEffectDictionary();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao remover efeito: ${error.message}`
          : "Erro ao remover efeito."
      );
    }
  }

  function getDictionaryLabel(dictionaryKey: string) {
    return (
      dictionaries.find((dictionary) => dictionary.key === dictionaryKey)?.label ??
      dictionaryKey
    );
  }

  function getColumnWidth(column: ColumnKey) {
    return columnWidths[column] ?? DEFAULT_COLUMN_WIDTHS[column] ?? 120;
  }

  function getCellValue(item: LootItem, column: ColumnKey) {
    const draftValue = editDrafts[item.id]?.[column];

    if (draftValue !== undefined) {
      return draftValue;
    }

    return String(item[column] ?? "");
  }

  function getCellDisplayValue(item: LootItem, column: ColumnKey) {
    const rawValue = getCellValue(item, column);
    const isSocketGemRecords = /socket_gem_records\.csv$/i.test(item.sourceFile);

    if (column === "bossMap") {
      return formatBossMapLabel(rawValue);
    }

    if (getNormalizedColumnLabel(column).includes("civil")) {
      const text = String(rawValue ?? "");
      if (text.length > 5) {
        return text.slice(0, 5);
      }
      return text;
    }

    if (isSocketGemRecords && column === "extra15") {
      const effectCode = String(rawValue || "").trim();
      if (!effectCode) {
        return "";
      }
      const found = effectEntries.find(
        (entry) =>
          String(entry.dictionaryKey || "resource") === "resource" &&
          String(entry.effCode || "").trim() === effectCode
      );
      const name = String(found?.name || found?.description || "").trim();
      const valueNum = Number(String(getCellValue(item, "extra3") || "").trim().replace(",", "."));
      const baseLabel = name || `Eff ${effectCode}`;
      const lower = baseLabel.toLowerCase();
      const isDecimalLike =
        lower.includes("speed") ||
        lower.includes("avoid") ||
        lower.includes("dodge") ||
        lower.includes("accuracy") ||
        lower.includes("precision");
      const isPercentLike =
        lower.includes("rate") ||
        lower.includes("chance") ||
        lower.includes("critical") ||
        lower.includes("attack") ||
        lower.includes("defense") ||
        lower.includes("hp") ||
        lower.includes("resistance") ||
        lower.includes("duration") ||
        lower.includes("range");
      const valueText = Number.isFinite(valueNum)
        ? isDecimalLike
          ? `${(Math.abs(valueNum) >= 1000 ? valueNum / 1000 : valueNum / 10).toFixed(1)}`
          : isPercentLike
          ? `${(Math.abs(valueNum) >= 1000 ? valueNum / 1000 : valueNum / 10).toFixed(1)}%`
          : String(Math.trunc(valueNum))
        : "";
      return `${baseLabel}${valueText ? ` ${valueText}` : ""}`;
    }

    if (isSocketGemRecords && ["extra6", "extra7", "extra8", "extra9"].includes(column)) {
      const parsed = Number(String(rawValue || "").trim().replace(",", "."));
      if (Number.isFinite(parsed)) {
        return `${(parsed / 100).toFixed(1)}%`;
      }
    }

    if (isChanceColumn(column)) {
      return formatChanceForInput(rawValue);
    }

    return rawValue;
  }

  function isEditableCell(item: LootItem, column: ColumnKey) {
    if (isIconColumn(column) && !/itemlooting/i.test(item.sourceFile)) {
      return true;
    }
    const isEditableSource =
      /itemlooting/i.test(item.sourceFile) || /boxitemout/i.test(item.sourceFile);
    return isEditableSource && ITEM_LOOTING_EDITABLE_COLUMNS.has(column);
  }

  function updateItemCellDraft(itemId: number, column: ColumnKey, value: string) {
    const previousValue = getCellValueById(itemId, column);
    applyDraftChanges(
      [
        {
          itemId,
          column,
          previousValue,
          nextValue: value,
        },
      ],
      true
    );

    const ownerGroup = bossGroups.find((group) =>
      group.items.some((item) => item.id === itemId)
    );

    if (ownerGroup) {
      setTemplateSourceBossKey(ownerGroup.key);
    }
  }

  function updateItemCellDraftsBulk(
    updates: Array<{ itemId: number; column: ColumnKey; value: string }>
  ) {
    if (updates.length === 0) {
      return;
    }

    applyDraftChanges(
      updates.map((update) => ({
        itemId: update.itemId,
        column: update.column,
        previousValue: getCellValueById(update.itemId, update.column),
        nextValue: update.value,
      })),
      true
    );

    const ownerGroup = bossGroups.find((group) =>
      group.items.some((item) => item.id === updates[0].itemId)
    );
    if (ownerGroup) {
      setTemplateSourceBossKey(ownerGroup.key);
    }
  }

  function getCellValueById(itemId: number, column: ColumnKey) {
    const item = items.find((currentItem) => currentItem.id === itemId);
    if (!item) {
      return "";
    }
    return getCellValue(item, column);
  }

  function applyDraftChanges(changes: DraftCellChange[], pushToUndo: boolean) {
    if (changes.length === 0) {
      return;
    }

    const normalizedChanges = changes.map((change) => ({
      ...change,
      nextValue: isChanceColumn(change.column)
        ? parsePercentToRfChance(change.nextValue)
        : change.nextValue,
    }));

    setEditDrafts((currentDrafts) => {
      const nextDrafts = { ...currentDrafts };
      for (const change of normalizedChanges) {
        nextDrafts[change.itemId] = {
          ...(nextDrafts[change.itemId] ?? {}),
          [change.column]: String(change.nextValue ?? ""),
        };
      }
      return nextDrafts;
    });

    if (pushToUndo) {
      setUndoStack((currentStack) => [...currentStack.slice(-99), normalizedChanges]);
      setRedoStack([]);
    }
  }

  function applyHistoryEntry(changes: DraftCellChange[], usePrevious: boolean) {
    setEditDrafts((currentDrafts) => {
      const nextDrafts = { ...currentDrafts };
      for (const change of changes) {
        nextDrafts[change.itemId] = {
          ...(nextDrafts[change.itemId] ?? {}),
          [change.column]: usePrevious ? change.previousValue : change.nextValue,
        };
      }
      return nextDrafts;
    });
  }

  function undoLastEdit() {
    setUndoStack((currentUndo) => {
      if (currentUndo.length === 0) {
        return currentUndo;
      }
      const entry = currentUndo[currentUndo.length - 1];
      applyHistoryEntry(entry, true);
      setRedoStack((currentRedo) => [...currentRedo, entry]);
      return currentUndo.slice(0, -1);
    });
  }

  function redoLastEdit() {
    setRedoStack((currentRedo) => {
      if (currentRedo.length === 0) {
        return currentRedo;
      }
      const entry = currentRedo[currentRedo.length - 1];
      applyHistoryEntry(entry, false);
      setUndoStack((currentUndo) => [...currentUndo, entry]);
      return currentRedo.slice(0, -1);
    });
  }

  function buildCellRange(anchor: CellPosition, target: CellPosition): CellRange {
    return {
      startRow: Math.min(anchor.row, target.row),
      endRow: Math.max(anchor.row, target.row),
      startCol: Math.min(anchor.col, target.col),
      endCol: Math.max(anchor.col, target.col),
    };
  }

  function isCellInRange(row: number, col: number) {
    if (!selectedCellRange) {
      return false;
    }
    return (
      row >= selectedCellRange.startRow &&
      row <= selectedCellRange.endRow &&
      col >= selectedCellRange.startCol &&
      col <= selectedCellRange.endCol
    );
  }

  function handleCellSelection(row: number, col: number, useRange: boolean) {
    const nextCell = { row, col };
    if (useRange && activeCell) {
      setSelectedCellRange(buildCellRange(activeCell, nextCell));
      return;
    }
    setActiveCell(nextCell);
    setSelectedCellRange(buildCellRange(nextCell, nextCell));
  }

  function applyQuickColumnFilter(
    column: ColumnKey,
    rawValue: string,
    append: boolean
  ) {
    if (!isColumnFilterable(column)) {
      return;
    }

    const value = String(rawValue ?? "");
    setColumnFilters((currentFilters) => {
      const currentValues = currentFilters[column] ?? [];
      const alreadySelected = currentValues.includes(value);

      let nextValues: string[];
      if (append) {
        nextValues = alreadySelected
          ? currentValues.filter((currentValue) => currentValue !== value)
          : [...currentValues, value];
      } else {
        nextValues = alreadySelected && currentValues.length === 1 ? [] : [value];
      }

      const nextFilters = { ...currentFilters };
      if (nextValues.length > 0) {
        nextFilters[column] = nextValues;
      } else {
        delete nextFilters[column];
      }
      return nextFilters;
    });

    setCurrentPage(0);
    setOpenColumnFilter(null);
  }

  function parseTsv(input: string) {
    return input
      .replace(/\r/g, "")
      .split("\n")
      .filter((line, index, lines) => line.length > 0 || index < lines.length - 1)
      .map((line) => line.split("\t"));
  }

  async function copySelectedCellsToClipboard() {
    if (!selectedCellRange || !navigator.clipboard) {
      return;
    }
    const lines: string[] = [];
    for (let row = selectedCellRange.startRow; row <= selectedCellRange.endRow; row += 1) {
      const item = items[row];
      if (!item) {
        continue;
      }
      const cells: string[] = [];
      for (let col = selectedCellRange.startCol; col <= selectedCellRange.endCol; col += 1) {
        const column = selectedColumns[col];
        if (!column) {
          cells.push("");
          continue;
        }
        cells.push(String(getCellDisplayValue(item, column.key) ?? ""));
      }
      lines.push(cells.join("\t"));
    }
    if (lines.length > 0) {
      await navigator.clipboard.writeText(lines.join("\n"));
    }
  }

  function pasteTsvIntoGrid(startRow: number, startCol: number, tsv: string) {
    const matrix = parseTsv(tsv);
    const updates: Array<{ itemId: number; column: ColumnKey; value: string }> = [];
    for (let rowOffset = 0; rowOffset < matrix.length; rowOffset += 1) {
      const item = items[startRow + rowOffset];
      if (!item) {
        continue;
      }
      for (let colOffset = 0; colOffset < matrix[rowOffset].length; colOffset += 1) {
        const column = selectedColumns[startCol + colOffset];
        if (!column || !isEditableCell(item, column.key)) {
          continue;
        }
        updates.push({
          itemId: item.id,
          column: column.key,
          value: matrix[rowOffset][colOffset] ?? "",
        });
      }
    }
    updateItemCellDraftsBulk(updates);
  }

  function isChanceColumn(column: ColumnKey) {
    const label = String(sourceColumnLabels[column] || column).toLowerCase();
    const normalized = label.replace(/[^a-z]/g, "");
    return normalized === "chance" || normalized === "chanse";
  }

  async function saveItemLootingEdits() {
    if (!window.electronAPI || !selectedSource || Object.keys(editDrafts).length === 0) {
      return;
    }

    const edits = Object.entries(editDrafts).flatMap(([itemId, columns]) =>
      Object.entries(columns)
        .filter(([column]) => ITEM_LOOTING_EDITABLE_COLUMNS.has(column as ColumnKey))
        .map(([column, value]) => ({
          itemId: Number(itemId),
          columnKey: column,
          value: String(value ?? ""),
        }))
    );

    if (edits.length === 0) {
      setMessage("Nenhuma alteracao valida para salvar.");
      return;
    }

    setIsSavingEdits(true);

    try {
      const result = await window.electronAPI.saveItemLootingEdits({
        sourceFile: selectedSource,
        edits,
      });
      setMessage(`${result.saved} celulas salvas no Excel de origem.`);
      await checkExcelUpdatesOnStart();
      setEditDrafts({});
      setTemplateAppliedMarks({});
      setUndoStack([]);
      setRedoStack([]);
      await refreshSources();
      await loadItems();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `Erro ao salvar alteracoes: ${error.message}`
          : "Erro ao salvar alteracoes."
      );
    } finally {
      setIsSavingEdits(false);
    }
  }

  function saveLootTemplateFromSelectedBoss() {
    const sourceGroup = bossGroups.find((group) => group.key === templateSourceBossKey);

    if (!sourceGroup) {
      setMessage("Selecione um boss para criar template.");
      return;
    }

    const templateRows: LootTemplateRow[] = [...sourceGroup.items]
      .sort((first, second) => (first.excelRow || first.id) - (second.excelRow || second.id))
      .map((item) => ({
      values: Object.fromEntries(
        [...ITEM_LOOTING_EDITABLE_COLUMNS].map((column) => [column, getCellValue(item, column)])
      ) as Partial<Record<ColumnKey, string>>,
      }));

    setLootTemplate({
      sourceRace: detectRaceFromBossMap(sourceGroup.bossMap),
      rows: templateRows,
    });
    setMessage(`Template salvo de ${sourceGroup.name} com ${templateRows.length} linhas.`);
  }

  function toggleApplyMap(map: string) {
    setSelectedMapsForApply((currentMaps) =>
      currentMaps.includes(map)
        ? currentMaps.filter((currentMap) => currentMap !== map)
        : [...currentMaps, map]
    );
  }

  function changeApplyRaceMode(nextMode: "auto" | "A" | "B" | "C") {
    setApplyRaceMode(nextMode);

    if (nextMode === "auto") {
      return;
    }

    const sourceMaps = allMapOptions.length > 0 ? allMapOptions : visibleMapOptions;
    setSelectedMapsForApply(
      sourceMaps.filter((map) => detectRaceFromBossMap(map) === nextMode)
    );
  }

  function applyLootTemplateToScope() {
    if (!lootTemplate) {
      setMessage("Crie um template de loot antes de aplicar.");
      return;
    }

    const sourceGroup = bossGroups.find((group) => group.key === templateSourceBossKey);
    const sourceMaps = sourceGroup ? splitBossMaps(sourceGroup.bossMap) : [];
    const targetGroups = bossGroups.filter((group) => {
      if (applyScope === "allVisible") {
        return true;
      }

      const maps = splitBossMaps(group.bossMap);
      if (applyScope === "sameMap") {
        return maps.some((map) => sourceMaps.includes(map));
      }

      return maps.some((map) => selectedMapsForApply.includes(map));
    });

    if (targetGroups.length === 0) {
      setMessage("Nenhum boss encontrado para o escopo escolhido.");
      return;
    }

    let updatedRows = 0;
    let clearedRows = 0;
    let truncatedRows = 0;
    const nextMarks: TemplateAppliedMarks = {};

    setEditDrafts((currentDrafts) => {
      const nextDrafts = { ...currentDrafts };

      for (const group of targetGroups) {
        const colorIndex = Math.abs(hashString(group.key)) % 8;
        const targetRace =
          applyRaceMode === "auto"
            ? detectRaceFromBossMap(group.bossMap)
            : (applyRaceMode as RaceKey);

        const orderedItems = [...group.items].sort(
          (first, second) => (first.excelRow || first.id) - (second.excelRow || second.id)
        );

        if (orderedItems.length < lootTemplate.rows.length) {
          truncatedRows += lootTemplate.rows.length - orderedItems.length;
        }

        for (let rowIndex = 0; rowIndex < orderedItems.length; rowIndex += 1) {
          const item = orderedItems[rowIndex];
          const templateValues = lootTemplate.rows[rowIndex]?.values ?? {};

          const convertedValues = Object.fromEntries(
            [...ITEM_LOOTING_EDITABLE_COLUMNS].map((column) => {
              const rawValue = templateValues[column] ?? "";
              const converted = convertLootValueForRace(
                String(rawValue),
                lootTemplate.sourceRace,
                targetRace
              );
              return [column, converted];
            })
          ) as Partial<Record<ColumnKey, string>>;
          convertedValues[monsterColumnKey] = String(item[monsterColumnKey] ?? group.monsterCode ?? "");

          if (!lootTemplate.rows[rowIndex]) {
            clearedRows += 1;
          } else {
            updatedRows += 1;
          }

          nextDrafts[item.id] = {
            ...(nextDrafts[item.id] ?? {}),
            ...convertedValues,
          };
          nextMarks[item.id] = colorIndex;
        }
      }

      return nextDrafts;
    });
    setTemplateAppliedMarks(nextMarks);

    setMessage(
      `Template aplicado: ${updatedRows} linhas copiadas, ${clearedRows} linhas zeradas.` +
        (truncatedRows > 0
          ? ` ${truncatedRows} linhas nao couberam (destino com menos linhas que o template).`
          : "")
    );
  }

  function changeColumnWidth(column: ColumnKey, width: number) {
    const nextWidth = Math.min(Math.max(width, MIN_COLUMN_WIDTH), MAX_COLUMN_WIDTH);

    setColumnWidths((currentWidths) => {
      const nextWidths = {
        ...currentWidths,
        [column]: nextWidth,
      };
      saveColumnWidthsForSource(selectedSource, nextWidths);
      return nextWidths;
    });
  }

  function autoFitAllVisibleColumns() {
    for (const column of selectedColumns) {
      if (column.key === "excelRow") {
        continue;
      }
      autoFitColumnWidth(column.key);
    }
  }

  function autoFitColumnWidth(column: ColumnKey) {
    if (column === "excelRow") {
      return;
    }
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.font = '13px "Segoe UI", Arial, sans-serif';

    const measure = (text: string) => Math.ceil(ctx.measureText(text).width);
    const label = String(sourceColumnLabels[column] || column);
    const sampleRows = visibleRows.length > 0 ? visibleRows : displayItems;
    const widths = sampleRows.map((item) => {
      const value = String(getCellDisplayValue(item, column) ?? "");
      return measure(value);
    });
    const maxTextWidth = widths.reduce((currentMax, width) => Math.max(currentMax, width), 0);

    // Padding sÃ³ do corpo da cÃ©lula; cabeÃ§alho nÃ£o deve forÃ§ar largura mÃ­nima.
    const contentPadding = 12;
    let target = Math.min(
      Math.max(Math.max(maxTextWidth, measure(label)) + contentPadding, MIN_COLUMN_WIDTH),
      MAX_COLUMN_WIDTH
    );
    if (/^\d+$/.test(String(column))) {
      const sorted = [...widths].sort((a, b) => a - b);
      const percentile95 = sorted.length > 0 ? sorted[Math.max(0, Math.floor(sorted.length * 0.95) - 1)] : 0;
      target = Math.min(target, Math.max(percentile95 + 10, 34));
    }
    changeColumnWidth(column, target);
  }

  function getNormalizedColumnLabel(column: ColumnKey) {
    return String(sourceColumnLabels[column] || ITEM_COLUMNS.find((c) => c.key === column)?.label || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "");
  }

  function isIconColumn(column: ColumnKey) {
    if (column === "icon") return true;
    const normalized = getNormalizedColumnLabel(column);
    return normalized === "icon" || normalized === "iconid" || normalized.startsWith("icon");
  }

  function startColumnResize(
    column: ColumnKey,
    event: ReactMouseEvent<HTMLDivElement>
  ) {
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = getColumnWidth(column);

    function handleMouseMove(moveEvent: MouseEvent) {
      changeColumnWidth(column, startWidth + moveEvent.clientX - startX);
    }

    function handleMouseUp() {
      document.body.classList.remove("is-resizing-column");
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    }

    document.body.classList.add("is-resizing-column");
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  }

  async function checkExcelUpdatesOnStart() {
    if (!window.electronAPI) {
      return;
    }

    try {
      const check = await window.electronAPI.checkExcelUpdates();
      const outdatedUniqueByPath = new Map<string, (typeof check.outdatedFiles)[number]>();
      for (const file of check.outdatedFiles) {
        const key = String(file.absolutePath || file.sourceFile || "").toLowerCase();
        if (!outdatedUniqueByPath.has(key)) {
          outdatedUniqueByPath.set(key, file);
        }
      }

      const missingUniqueByPath = new Map<string, (typeof check.missingFiles)[number]>();
      for (const file of check.missingFiles) {
        const key = String(file.absolutePath || file.sourceFile || "").toLowerCase();
        if (!missingUniqueByPath.has(key)) {
          missingUniqueByPath.set(key, file);
        }
      }

      const uniqueOutdatedFiles = [...outdatedUniqueByPath.values()];
      const uniqueMissingFiles = [...missingUniqueByPath.values()];
      const changed = uniqueOutdatedFiles.length;
      const missing = uniqueMissingFiles.length;

      const outdatedSourcesUnique = Array.from(
        new Set(uniqueOutdatedFiles.map((file) => String(file.sourceFile || "")))
      ).filter(Boolean);
      setOutdatedSourceFiles(outdatedSourcesUnique);

      if (changed > 0 || missing > 0) {
        const changedNames = Array.from(
          new Set(uniqueOutdatedFiles.map((file) => formatSourceLabel(file.sourceFile)))
        );
        const missingNames = Array.from(
          new Set(uniqueMissingFiles.map((file) => formatSourceLabel(file.sourceFile)))
        );
        const details = [
          changedNames.length ? `Alterados: ${changedNames.join(", ")}` : "",
          missingNames.length ? `Ausentes: ${missingNames.join(", ")}` : "",
        ]
          .filter(Boolean)
          .join(" | ");
        setExcelUpdateNotice(
          `Excels alterados: ${changed} | ausentes: ${missing}. ${details || ""}`
        );
      } else {
        setExcelUpdateNotice("");
      }
    } catch {
      // Silencioso para nao poluir a abertura do app.
    }
  }

  function goToPage(page: number) {
    const safePage = Math.min(Math.max(page, 0), totalPages - 1);
    setCurrentPage(safePage);
    setPageInput("");
    saveCurrentPage(selectedSource, search, filters, columnFilters, effectiveItemsPerPage, safePage);
  }

  function goToPageInput() {
    const page = Number(pageInput);

    if (!Number.isInteger(page)) {
      return;
    }

    goToPage(page - 1);
  }

  function syncTableScroll(source: "top" | "table") {
    const topScroller = tableTopScrollRef.current;
    const tableScroller = tableWrapRef.current;

    if (!topScroller || !tableScroller) {
      return;
    }

    if (source === "top") {
      tableScroller.scrollLeft = topScroller.scrollLeft;
    } else {
      topScroller.scrollLeft = tableScroller.scrollLeft;
    }
  }

  async function loadSourceBackups() {
    if (!window.electronAPI?.listSourceBackups || !selectedSource) {
      setSourceBackups([]);
      return;
    }
    try {
      const list = await window.electronAPI.listSourceBackups(selectedSource);
      setSourceBackups(list);
    } catch {
      setSourceBackups([]);
    }
  }

  async function restoreSourceBackup(backupName: string) {
    if (!window.electronAPI?.restoreSourceBackup || !selectedSource) {
      return;
    }
    const ok = window.confirm(`Restaurar backup ${backupName}?`);
    if (!ok) return;
    try {
      await window.electronAPI.restoreSourceBackup({ sourceFile: selectedSource, backupName });
      await loadItems();
      await loadSourceBackups();
      setMessage(`Backup restaurado: ${backupName}`);
    } catch (error) {
      setMessage(error instanceof Error ? `Erro ao restaurar backup: ${error.message}` : "Erro ao restaurar backup.");
    }
  }

  async function resetExcelUpdatesBaseline() {
    if (!window.electronAPI?.resetExcelUpdatesBaseline) {
      return;
    }
    await window.electronAPI.resetExcelUpdatesBaseline();
    await checkExcelUpdatesOnStart();
    setMessage("Notificacoes de alteracao foram reiniciadas.");
    window.setTimeout(() => setMessage(""), 2000);
  }

  useEffect(() => {
    syncTableScroll("table");
  }, [tableWidth, selectedSource, itemsPerPage, currentPage]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const measured = tableWrapRef.current?.scrollWidth ?? 0;
      setTopScrollContentWidth(Math.max(measured, tableWidth));
      syncTableScroll("table");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [tableWidth, selectedColumns, visibleRows.length, items.length, selectedSource]);

  useEffect(() => {
    if (isBoxItemOutSelected) {
      setActiveSidePanel("boxbuilder");
    }
  }, [isBoxItemOutSelected]);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="header-left">
          <div className="title-row">
            <span className="app-mark">×</span>
            <h1>RF Editor Tool</h1>
            <span className="build-chip">{BUILD_MARKER}</span>
            <button
              type="button"
              className={`build-alert ${excelUpdateNotice ? "active" : ""}`}
              title={
                excelUpdateNotice
                  ? `${excelUpdateNotice} (clique para resetar aviso)`
                  : "Sem notificacoes"
              }
              onClick={resetExcelUpdatesBaseline}
            >
              !
            </button>
          </div>
          <section className="toolbar-group profile-toolbar-group">
            <h3>Perfil</h3>
            <div className="toolbar-row">
              <select
                className="profile-select-wide"
                value={activeProfileId}
                onChange={(event) => switchProfile(event.target.value)}
                disabled={!isElectron || isImporting || profiles.length === 0}
                title="Perfil ativo"
              >
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
              <button
                className="profile-mini-btn"
                onClick={() => startProfileAction("new")}
                disabled={!isElectron || isImporting}
              >
                Novo
              </button>
              <button
                className="profile-mini-btn"
                onClick={() => startProfileAction("rename")}
                disabled={!isElectron || isImporting || !activeProfileId}
              >
                Renomear
              </button>
              <button
                className="profile-mini-btn"
                onClick={() => startProfileAction("duplicate")}
                disabled={!isElectron || isImporting || !activeProfileId}
              >
                Duplicar
              </button>
              <button
                className="profile-mini-btn"
                onClick={deleteProfile}
                disabled={!isElectron || isImporting || !activeProfileId || profiles.length <= 1}
              >
                Excluir
              </button>
              <button
                className="profile-mini-btn"
                onClick={restartApp}
                disabled={!isElectron || isImporting}
              >
                Reiniciar
              </button>
            </div>
            {profileAction ? (
              <div className="toolbar-row">
                <input
                  value={profileNameDraft}
                  onChange={(event) => setProfileNameDraft(event.target.value)}
                  placeholder="Nome do perfil"
                  disabled={!isElectron || isImporting}
                />
                <button onClick={confirmProfileAction} disabled={!isElectron || isImporting}>
                  OK
                </button>
                <button onClick={cancelProfileAction} disabled={!isElectron || isImporting}>
                  Cancelar
                </button>
              </div>
            ) : null}
          </section>
        </div>

        <div className="toolbar toolbar-layout">
          <section className="toolbar-group import-toolbar-group">
            <h3>Importar</h3>
            <div className="toolbar-row">
              <button className="import-btn" onClick={importarItems} disabled={!isElectron || isImporting}>
                <span className="toolbar-button-icon">▣</span>
                <span>{isImporting ? "Importando..." : "Excel"}</span>
              </button>
              <button className="import-btn" onClick={scanExcelDirectory} disabled={!isElectron || isImporting}>
                <span className="toolbar-button-icon">▰</span>
                <span>Pasta</span>
              </button>
              <button className="import-btn" onClick={importBossDirectory} disabled={!isElectron || isImporting}>
                <span className="toolbar-button-icon">▣</span>
                <span>Bosses</span>
              </button>
              <button className="import-btn" onClick={importarCsv} disabled={!isElectron || isImporting}>
                <span className="toolbar-button-icon">▤</span>
                <span>CSV</span>
              </button>
            </div>
          </section>
        </div>

        <label className="top-global-search">
          <span>Buscar em todos os arquivos</span>
          <input
            value={quickLookup}
            onChange={(event) => setQuickLookup(event.target.value)}
            placeholder="Buscar em todos os arquivos..."
            disabled={!isElectron}
          />
        </label>
      </header>

      {message ? <div className="status">{message}</div> : null}
      {importProgress ? (
        <ImportProgressBar progress={importProgress} />
      ) : null}

      <nav className="view-tabs" aria-label="Areas do editor">
        <button
          type="button"
          className={activeView === "items" ? "active" : ""}
          onClick={() => setActiveView("items")}
        >
          Itens
        </button>
        <button
          type="button"
          className={activeView === "effects" ? "active" : ""}
          onClick={() => setActiveView("effects")}
        >
          Dicionario de efeitos
        </button>
        <button
          type="button"
          className={activeView === "hgk" ? "active" : ""}
          onClick={() => setActiveView("hgk")}
        >
          HGK
        </button>
        <button
          type="button"
          className={activeView === "itemCombine" ? "active" : ""}
          onClick={() => setActiveView("itemCombine")}
        >
          ItemCombine
        </button>
      </nav>

      {activeView === "items" || activeView === "hgk" || activeView === "itemCombine" ? (
        <>
          <div className="left-dock">
            <button
              type="button"
              className={activeSidePanel === "columns" ? "active" : ""}
              onClick={() =>
                setActiveSidePanel((current) => (current === "columns" ? null : "columns"))
              }
              title="Colunas"
            >
              📏
            </button>
            <button
              type="button"
              className={activeSidePanel === "boxbuilder" ? "active" : ""}
              onClick={() =>
                setActiveSidePanel((current) => (current === "boxbuilder" ? null : "boxbuilder"))
              }
              title="Box Builder"
            >
              📦
            </button>
            <button
              type="button"
              className={activeSidePanel === "effects" ? "active" : ""}
              onClick={() => {
                setActiveSidePanel((current) => (current === "effects" ? null : "effects"));
                setActiveView("effects");
              }}
              title="Dicionario"
            >
              📘
            </button>
            <button
              type="button"
              className={activeSidePanel === "gearscore" ? "active" : ""}
              onClick={() =>
                setActiveSidePanel((current) => (current === "gearscore" ? null : "gearscore"))
              }
              title="Gearscore"
            >
              ⚔
            </button>
            <button
              type="button"
              className={activeSidePanel === "gems" ? "active" : ""}
              onClick={() =>
                setActiveSidePanel((current) => (current === "gems" ? null : "gems"))
              }
              title="Gemas"
            >
              💎
            </button>
            <button
              type="button"
              className={activeSidePanel === "transmog" ? "active" : ""}
              onClick={() =>
                setActiveSidePanel((current) => (current === "transmog" ? null : "transmog"))
              }
              title="Transmog"
            >
              👕
            </button>
          </div>
          <section className="controls data-source-card">
            <label className="data-field source-file-field">
              <span>Arquivo</span>
              <div className="source-control source-control-primary">
                <div className="source-dropdown" ref={sourceDropdownRef}>
                  <button
                    type="button"
                    className={`source-dropdown-trigger ${
                      (selectedSourceValue && outdatedSourceFiles.includes(selectedSourceValue)) ||
                      (!selectedSourceValue && outdatedSourceFiles.length > 0)
                        ? "outdated"
                        : ""
                    }`}
                    onClick={() => setIsSourceDropdownOpen((current) => !current)}
                    disabled={!isElectron}
                  >
                    <span>
                      {selectedSourceValue
                        ? `${formatSourceLabel(selectedSourceValue)} (${scopedSources.find((source) => source.sourceFile === selectedSourceValue)?.itemCount ?? 0})`
                        : "Todos os arquivos"}
                    </span>
                    <span className="source-dropdown-caret">&#9662;</span>
                  </button>
                  {isSourceDropdownOpen ? (
                    <div className="source-dropdown-menu">
                      <button
                        type="button"
                        className={`source-dropdown-item ${selectedSourceValue === "" ? "active" : ""}`}
                        onClick={() => {
                          changeSelectedSource("");
                          setIsSourceDropdownOpen(false);
                        }}
                      >
                        Todos os arquivos
                      </button>
                      {sortedScopedSources.map((source) => (
                        <button
                          key={source.sourceFile}
                          type="button"
                          className={`source-dropdown-item ${selectedSourceValue === source.sourceFile ? "active" : ""} ${
                            outdatedSourceFiles.includes(source.sourceFile) ? "outdated" : ""
                          }`}
                          onClick={() => {
                            changeSelectedSource(source.sourceFile);
                            setIsSourceDropdownOpen(false);
                          }}
                        >
                          {formatSourceLabel(source.sourceFile)} ({source.itemCount})
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="source-remove-button"
                  onClick={deleteSelectedSource}
                  disabled={!isElectron || !selectedSource || isImporting}
                  title="Remover o arquivo selecionado do banco"
                >
                  Remover
                </button>
                <button
                  type="button"
                  className="source-remove-button"
                  onClick={reimportCurrentSource}
                  disabled={!isElectron || !selectedSource || isImporting}
                  title="Reimportar este arquivo do caminho original"
                >
                  Reimportar
                </button>
              </div>
            </label>
            {selectedSource && activeView === "items" ? (
              <label className="data-field sheet-field">
                <span>Aba da planilha</span>
                <div className="sheet-control">
                  <select
                    value={selectedSheetName}
                    onChange={(event) => setSelectedSheetName(event.target.value)}
                    disabled={!isElectron || isImporting || sourceSheets.length === 0}
                  >
                    {sourceSheets.map((sheet) => (
                      <option key={sheet} value={sheet}>
                        {sheet}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="source-remove-button"
                    onClick={importSelectedSheet}
                    disabled={
                      !isElectron ||
                      isImporting ||
                      !selectedSheetName ||
                      extractSheetNameFromSource(selectedSource) === selectedSheetName
                    }
                    title="Carregar outra aba do mesmo Excel"
                  >
                    Carregar aba
                  </button>
                </div>
              </label>
            ) : null}
            <label className="data-field backup-field">
              <span>Backup</span>
              <select
                className="backup-select-compact"
                value=""
                onChange={(event) => {
                  const value = event.target.value;
                  if (value) {
                    void restoreSourceBackup(value);
                  }
                }}
                disabled={!selectedSource || sourceBackups.length === 0}
                title="Restaurar backup"
              >
                <option value="">Restaurar backup</option>
                {sourceBackups.slice(0, 20).map((backup) => (
                  <option key={backup.name} value={backup.name}>
                    {backup.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="data-field data-filter-field">
              <span>Filtro de dados</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Code, Name, Type ou SubType"
                disabled={!isElectron}
              />
            </label>
            <div className="quick-actions-row" aria-label="Acoes rapidas">
              <button
                type="button"
                onClick={clearFilters}
                disabled={
                  !isElectron ||
                  (!search && filters.length === 0 && Object.keys(columnFilters).length === 0)
                }
              >
                Limpar filtros
              </button>
              {selectedSource && activeView === "items" ? (
                <button
                  type="button"
                  className="source-remove-button"
                  onClick={() => setShowBulkRemoveSources((current) => !current)}
                  disabled={!isElectron || scopedSources.length === 0 || isImporting}
                  title="Remover varios arquivos"
                >
                  Varios
                </button>
              ) : null}
            </div>
          </section>

          {showBulkRemoveSources ? (
            <section className="excel-scan-panel">
              <div className="excel-scan-header">
                <div>
                  <h2>Remover arquivos</h2>
                  <p>Selecione os arquivos para excluir do banco.</p>
                </div>
                <div className="excel-scan-actions">
                  <button
                    type="button"
                    onClick={() =>
                      setBulkSelectedSources(scopedSources.map((source) => source.sourceFile))
                    }
                  >
                    Marcar todos
                  </button>
                  <button type="button" onClick={() => setBulkSelectedSources([])}>
                    Limpar
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMultipleSources(bulkSelectedSources)}
                    disabled={bulkSelectedSources.length === 0}
                  >
                    Remover selecionados
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      deleteMultipleSources(scopedSources.map((source) => source.sourceFile))
                    }
                    disabled={scopedSources.length === 0}
                  >
                    Remover todos
                  </button>
                </div>
              </div>
              <div className="excel-file-list">
                {sortedScopedSources.map((source) => (
                  <label key={source.sourceFile} className="excel-file-option">
                    <input
                      type="checkbox"
                      checked={bulkSelectedSources.includes(source.sourceFile)}
                      onChange={() => toggleBulkSource(source.sourceFile)}
                    />
                    <span>
                      {formatSourceLabel(source.sourceFile)} ({source.itemCount})
                    </span>
                  </label>
                ))}
              </div>
            </section>
          ) : null}

          {scannedExcelFiles.length > 0 ? (
            <section className="excel-scan-panel">
              <div className="excel-scan-header">
                <div>
                  <h2>Excels encontrados</h2>
                  <p>{scannedDirectory}</p>
                </div>

                <div className="excel-scan-actions">
                  <button type="button" onClick={toggleAllScannedExcelFiles}>
                    {selectedExcelFiles.length === scannedExcelFiles.length
                      ? "Desmarcar todos"
                      : "Marcar todos"}
                  </button>
                  <button
                    type="button"
                    onClick={importSelectedExcelFiles}
                    disabled={isImporting || selectedExcelFiles.length === 0}
                  >
                    Importar selecionados
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setScannedExcelFiles([]);
                      setSelectedExcelFiles([]);
                      setScannedExcelSearch("");
                    }}
                  >
                    Fechar
                  </button>
                </div>
              </div>

              <input
                value={scannedExcelSearch}
                onChange={(event) => setScannedExcelSearch(event.target.value)}
                placeholder="Buscar arquivo na pasta"
              />

              <div className="excel-file-list">
                {filteredScannedExcelFiles.map((file) => (
                  <label key={file.filePath} className="excel-file-option">
                    <input
                      type="checkbox"
                      checked={selectedExcelFiles.includes(file.filePath)}
                      onChange={() => toggleScannedExcelFile(file.filePath)}
                    />
                    <span>{file.relativePath}</span>
                  </label>
                ))}
                {filteredScannedExcelFiles.length === 0 ? (
                  <div className="empty-state">Nenhum arquivo encontrado.</div>
                ) : null}
              </div>
            </section>
          ) : null}

          <div className={`top-panels ${SHOW_FILTER_PANEL ? "" : "single-panel"}`}>
          {activeView !== "itemCombine" && SHOW_FILTER_PANEL ? (
          <section
            className={`filter-panel ${isFilterPanelCollapsed ? "collapsed" : ""}`}
            aria-label="Filtros avancados"
          >
            <div className="filter-panel-header">
              <div>
                <h2>Filtros</h2>
                <p>Todos os criterios ativos sao combinados na mesma busca.</p>
              </div>

              <button
                type="button"
                className="filter-panel-toggle"
                onClick={toggleFilterPanel}
                title={isFilterPanelCollapsed ? "Mostrar filtros" : "Minimizar filtros"}
                aria-label={
                  isFilterPanelCollapsed ? "Mostrar filtros" : "Minimizar filtros"
                }
              >
                {isFilterPanelCollapsed ? "+" : "-"}
              </button>

              <div className="filter-actions">
                <button type="button" onClick={addFilter} disabled={!isElectron}>
                  Adicionar criterio
                </button>
                <button
                  type="button"
                  onClick={clearFilters}
                  disabled={
                    !isElectron ||
                    (!search &&
                      filters.length === 0 &&
                      Object.keys(columnFilters).length === 0)
                  }
                >
                  Limpar
                </button>
              </div>
            </div>

            {!isFilterPanelCollapsed && filters.length > 0 ? (
              <div className="filter-list">
                {filters.map((filter) => (
                  <div className="filter-row" key={filter.id}>
                    <select
                      value={filter.field}
                      onChange={(event) =>
                        updateFilter(filter.id, {
                          field: event.target.value as ColumnKey,
                        })
                      }
                    >
                      {SEARCHABLE_COLUMNS.map((column) => (
                        <option key={column.key} value={column.key}>
                          {sourceColumnLabels[column.key] || column.label}
                        </option>
                      ))}
                    </select>

                    <select
                      value={filter.operator}
                      onChange={(event) =>
                        updateFilter(filter.id, {
                          operator: event.target.value as FilterOperator,
                        })
                      }
                    >
                      {FILTER_OPERATORS.map((operator) => (
                        <option key={operator.value} value={operator.value}>
                          {operator.label}
                        </option>
                      ))}
                    </select>

                    <input
                      value={filter.value}
                      onChange={(event) =>
                        updateFilter(filter.id, { value: event.target.value })
                      }
                      placeholder="Valor"
                    />

                    <button type="button" onClick={() => removeFilter(filter.id)}>
                      Remover
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

            {!isFilterPanelCollapsed && filters.length === 0 ? (
              <div className="filter-empty">
                Exemplo: Name contem Hora staff + Grade igual a 0.
              </div>
            ) : null}
          </section>
          ) : null}

          {activeView !== "itemCombine" && activeSidePanel === "columns" ? (
          <section
            className={`column-panel ${isColumnPanelCollapsed ? "collapsed" : ""}`}
            aria-label="Colunas visiveis"
          >
            <div className="column-panel-header">
              <div className="filters-heading-row">
                <h2 className="filters-title">Filtros de {selectedSourceLabel}</h2>
                <select
                  value={selectedSourceDictionary}
                  onChange={(event) => changeSourceDictionary(event.target.value)}
                  disabled={!isElectron || !selectedSource}
                  title="Trocar dicionario"
                >
                  {dictionaries.map((dictionary) => (
                    <option key={dictionary.key} value={dictionary.key}>
                      {dictionary.label}
                    </option>
                  ))}
                </select>
                <select
                  className="hidden-column-select"
                  value=""
                  onChange={(event) => {
                    const value = event.target.value as ColumnKey;
                    if (value) {
                      restoreColumnOption(value);
                    }
                  }}
                  disabled={hiddenColumnOptionItems.length === 0}
                  title="Restaurar filtro oculto"
                >
                  <option value="">
                    Colunas ocultas ({hiddenColumnOptionItems.length})
                  </option>
                  {hiddenColumnOptionItems.map((column) => (
                    <option key={column.key} value={column.key}>
                      {sourceColumnLabels[column.key] || column.label}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="column-panel-toggle"
                onClick={toggleColumnPanel}
                title={isColumnPanelCollapsed ? "Mostrar colunas" : "Minimizar colunas"}
                aria-label={
                  isColumnPanelCollapsed ? "Mostrar colunas" : "Minimizar colunas"
                }
              >
                {isColumnPanelCollapsed ? "+" : "-"}
              </button>
            </div>

            {!isColumnPanelCollapsed ? (
              <div className="column-panel-body">
                <div className="column-list">
                  {visibleColumnOptions.map((column) => (
                    <label key={column.key} className="column-option">
                      <input
                        type="checkbox"
                        checked={visibleColumns.includes(column.key)}
                        onChange={() => toggleColumn(column.key)}
                      />
                      <span>{sourceColumnLabels[column.key] || column.label}</span>
                      <button
                        type="button"
                        className="column-option-hide"
                        onClick={(event) => {
                          event.preventDefault();
                          hideColumnOption(column.key);
                        }}
                        title="Esconder este controle"
                        aria-label={`Esconder ${sourceColumnLabels[column.key] || column.label}`}
                      >
                        x
                      </button>
                    </label>
                  ))}
                </div>

              </div>
            ) : null}
          </section>
          ) : null}
          </div>

          {activeView === "itemCombine" ? (
            <section className="item-combine-panel">
              <div className="item-combine-header">
                <div>
                  <h2>{selectedSource ? formatSourceLabel(selectedSource) : "ItemCombine"}</h2>
                  <p>
                    Trabalhe com receitas, grupos vinculados e a tabela original importada.
                  </p>
                </div>
                <div className="item-combine-tabs">
                  <button
                    type="button"
                    className={itemCombineViewMode === "recipes" ? "active" : ""}
                    onClick={() => setItemCombineViewMode("recipes")}
                  >
                    Receitas
                  </button>
                  <button
                    type="button"
                    className={itemCombineViewMode === "groups" ? "active" : ""}
                    onClick={() => setItemCombineViewMode("groups")}
                  >
                    Grupos
                  </button>
                  <button
                    type="button"
                    className={itemCombineViewMode === "raw" ? "active" : ""}
                    onClick={() => setItemCombineViewMode("raw")}
                  >
                    Excel original
                  </button>
                </div>
              </div>
              <div className="item-combine-tools">
                <input
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setCurrentPage(0);
                  }}
                  placeholder="Buscar combinacao, item, grupo..."
                  disabled={!selectedSource}
                />
                <button
                  type="button"
                  onClick={() => setHideRepeatedCombineCards((current) => !current)}
                  className={hideRepeatedCombineCards ? "active" : ""}
                  disabled={!selectedSource}
                >
                  {hideRepeatedCombineCards ? "Repetidas ocultas" : "Ocultar repetidas"}
                </button>
                <button
                  type="button"
                  onClick={generateGrade1WeaponSocketCombines}
                  disabled={isGeneratingCombineTool}
                  title="Cria grupos LL/LR e combines de slot para armas grade 1 no CombineTable2."
                >
                  {isGeneratingCombineTool ? "Gerando..." : "Gerar Grade 1"}
                </button>
                <button
                  type="button"
                  onClick={saveGeneratedWeaponSocketCombines}
                  disabled={isGeneratingCombineTool}
                  title="Salva no Excel as combinações de extensores geradas."
                >
                  Salvar extensores no Excel
                </button>
                <select
                  value={itemCombineCardsPerPage}
                  onChange={(event) => {
                    setItemCombineCardsPerPage(Number(event.target.value));
                    setCurrentPage(0);
                  }}
                  title="Combinações por página"
                >
                  <option value={4}>4 por página</option>
                  <option value={8}>8 por página</option>
                  <option value={12}>12 por página</option>
                  <option value={20}>20 por página</option>
                </select>
                <div className="item-combine-page-tools">
                  <button type="button" onClick={() => goToPage(0)} disabled={currentPage === 0}>
                    &lt;&lt;
                  </button>
                  <button type="button" onClick={() => goToPage(currentPage - 1)} disabled={currentPage === 0}>
                    &lt;
                  </button>
                  <span>{currentPage + 1} / {totalPages}</span>
                  <button
                    type="button"
                    onClick={() => goToPage(currentPage + 1)}
                    disabled={currentPage >= totalPages - 1}
                  >
                    &gt;
                  </button>
                  <button
                    type="button"
                    onClick={() => goToPage(totalPages - 1)}
                    disabled={currentPage >= totalPages - 1}
                  >
                    &gt;&gt;
                  </button>
                  <input
                    value={pageInput}
                    onChange={(event) => setPageInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        goToPageInput();
                      }
                    }}
                    inputMode="numeric"
                    placeholder="Pagina"
                  />
                  <button type="button" onClick={goToPageInput} disabled={!pageInput}>
                    Ir
                  </button>
                  {searchedCombineOriginalPage !== null ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSearch("");
                        goToPage(searchedCombineOriginalPage);
                      }}
                    >
                      Ver pagina original
                    </button>
                  ) : null}
                </div>
              </div>

              {!selectedSource ? (
                <div className="item-combine-empty">
                  Selecione CombineTable, CombineTable2 ou LinkedCombines no campo Arquivo.
                </div>
              ) : combineTableNeedsReimport ? (
                <div className="item-combine-empty">
                  Este CombineTable ainda foi importado com poucas colunas. Reimporte o Excel para carregar todos os resultados.
                </div>
              ) : itemCombineViewMode === "raw" ? (
                <div className="item-combine-empty">
                  A tabela original fica logo abaixo para conferência célula por célula.
                </div>
              ) : isLinkedCombineSelected || itemCombineViewMode === "groups" ? (
                <div className="item-combine-grid">
                  {itemCombineGroupCards.map((group) => (
                    <article key={group.id} className="item-combine-card">
                      <div className="item-combine-card-title">
                        <strong>{group.code}</strong>
                        <span>{group.entries.length} itens</span>
                      </div>
                      <div className="linked-combine-items">
                        {group.entries.slice(0, 18).map((entry, index) => (
                          <span key={`${group.id}-${entry}-${index}`} title={formatItemCodeName(entry || "")}>
                            {formatItemCodeName(entry || "")}
                          </span>
                        ))}
                      </div>
                    </article>
                  ))}
                  {itemCombineGroupCards.length === 0 ? (
                    <div className="item-combine-empty">Nenhum grupo carregado nesta página.</div>
                  ) : null}
                </div>
              ) : (
                <div className="item-combine-grid">
                  {itemCombineRecipeCards.map((recipe) => (
                    <article key={recipe.id} className="item-combine-card recipe-card">
                      <div className="item-combine-card-title">
                        <strong>{recipe.description} ({recipe.excelRow})</strong>
                      </div>
                      <div className="recipe-meta">
                        <span>Custo: <strong>{formatDalant(recipe.dalant)}</strong></span>
                        <span>Raça: <strong>{formatCivilLabel(recipe.civil)}</strong></span>
                        <span>Loss: <strong>{formatCombineLoss(recipe.failLostCount)}</strong></span>
                        <span>Resultados: <strong>{recipe.rewardCount || "-"}</strong></span>
                        <span>Escolha: <strong>{recipe.isSelectItem === "1" ? "Sim" : "Não"}</strong></span>
                      </div>
                      <div className="recipe-materials">
                        {recipe.materials.length > 0 ? (
                          recipe.materials.map((material, index) => (
                            <div key={`${recipe.id}-mat-${index}`}>
                              <span className="combine-card-quantity">x{material.quantity || "-"}</span>
                              <strong title={formatItemCodeName(material.item || "")}>
                                {material.item || "-"} - {material.upt || "-"}
                              </strong>
                              {!isLinkedCombineCode(material.item || "") && getCachedItemName(material.item || "") ? (
                                <span>{getCachedItemName(material.item || "")}</span>
                              ) : null}
                              {isLinkedCombineCode(material.item || "") ? (
                                <span className="linked-group-hint">ver em Grupos</span>
                              ) : null}
                            </div>
                          ))
                        ) : (
                          <span className="item-combine-muted">Sem materiais visíveis nas colunas carregadas.</span>
                        )}
                      </div>
                      <div className="recipe-section-label">Resultado:</div>
                      <div className="recipe-results">
                        {recipe.results.map((result) => (
                          <span
                            key={`${recipe.id}-${result.code}`}
                            className="recipe-result-card"
                            title={formatItemCodeName(result.code)}
                          >
                            <span className="combine-card-quantity">x{result.result || "-"}</span>
                            <strong>{result.code || "-"} - {result.upt || "-"}</strong>
                            {getCachedItemName(result.code || "") ? (
                              <small>{getCachedItemName(result.code || "")}</small>
                            ) : null}
                            <em className="combine-card-chance">{formatCombineChance(result.chance)}</em>
                          </span>
                        ))}
                        {getCombineFailChance(recipe.results) > 0 ? (
                          <span className="recipe-fail-result">
                            <strong>Falha</strong>
                            <em>{formatCombineChance(String(getCombineFailChance(recipe.results)))}</em>
                          </span>
                        ) : null}
                      </div>
                    </article>
                  ))}
                  {itemCombineRecipeCards.length === 0 ? (
                    <div className="item-combine-empty">Nenhuma receita carregada nesta página.</div>
                  ) : null}
                </div>
              )}
            </section>
          ) : null}

          {isBoxItemOutSelected && activeSidePanel === "boxbuilder" ? (
            <section className="column-panel box-builder-panel">
              <div className="column-panel-header">
                <h2>Box Builder</h2>
                <p>Crie/edite box por recompensa e chance em %.</p>
              </div>
              <div className="box-builder-toolbar">
                <input
                  value={boxBuilderCode}
                  onChange={(event) => setBoxBuilderCode(event.target.value)}
                  placeholder="Codigo da box"
                />
                <select
                  value={boxBuilderRace}
                  onChange={(event) => setBoxBuilderRace(event.target.value as BoxRace)}
                >
                  <option value="all">Todas</option>
                  <option value="acc">Accretia</option>
                  <option value="bell">Bellato</option>
                  <option value="cora">Cora</option>
                </select>
                <button type="button" onClick={addBoxRewardLine}>
                  + Recompensa
                </button>
                <button type="button" onClick={loadExistingBoxToBuilder}>
                  Carregar box
                </button>
                <button type="button" onClick={validateBoxRewardsCivil}>
                  Validar Civil
                </button>
                <button
                  type="button"
                  onClick={createOrUpdateBoxFromBuilder}
                  disabled={isSavingEdits}
                >
                  {isSavingEdits ? "Salvando..." : "Salvar box"}
                </button>
              </div>
              <div className="box-builder-list">
                <div className="box-builder-list-header">
                  <span>Item</span>
                  <span>Nome</span>
                  <span>Icone</span>
                  <span>Civil</span>
                  <span>Qtd</span>
                  <span>Chance %</span>
                  <span />
                  <span>AÃ§Ãµes</span>
                </div>
                {boxRewards.map((reward, index) => (
                  <div key={`reward-${index}`} className="box-builder-row">
                    <div className="box-code-cell" onClick={(event) => event.stopPropagation()}>
                      <input
                        value={reward.itemCode}
                        onChange={(event) => {
                          updateBoxRewardLine(index, "itemCode", event.target.value);
                          void loadBoxCodeSuggestions(index, event.target.value);
                          void hydrateBoxRewardMeta(index, event.target.value);
                          setActiveSuggestionRow(index);
                        }}
                        onFocus={() => {
                          void loadBoxCodeSuggestions(index, reward.itemCode);
                          setActiveSuggestionRow(index);
                        }}
                        placeholder="Recompensa"
                      />
                      {activeSuggestionRow === index && (boxCodeSuggestions[index] || []).length > 0 ? (
                        <div className="box-code-dropdown">
                          {(boxCodeSuggestions[index] || []).map((item) => {
                            const code = String(item.code || "");
                            return (
                              <button
                                key={`box-suggestion-${index}-${item.id}`}
                                type="button"
                                onClick={() => {
                                  updateBoxRewardLine(index, "itemCode", code);
                                  setBoxRewards((current) =>
                                    current.map((reward, currentIndex) =>
                                      currentIndex === index
                                        ? {
                                            ...reward,
                                            itemName: String(item.name || ""),
                                            itemIcon: String(item.icon || ""),
                                            itemSourceFile: String(item.sourceFile || ""),
                                          }
                                        : reward
                                    )
                                  );
                                  void hydrateBoxRewardMeta(index, code);
                                  setActiveSuggestionRow(null);
                                }}
                              >
                                {code} - {String(item.name || "")}
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                    <input value={reward.itemName} readOnly placeholder="Nome do item" />
                    <div className="box-icon-preview-cell">
                      <span
                        className="box-icon-preview"
                        style={getBoxIconPreviewStyle(reward, rfIconSheets)}
                      />
                    </div>
                    <span className={`box-civil-status status-${reward.status}`}>
                      {reward.status === "ok"
                        ? `${reward.civil}`
                        : reward.status === "invalid"
                        ? `${reward.civil}`
                        : reward.status === "unknown"
                        ? "-"
                        : ""}
                    </span>
                    <input
                      value={reward.quantity}
                      onChange={(event) =>
                        updateBoxRewardLine(index, "quantity", event.target.value)
                      }
                      placeholder="Qtd"
                    />
                    <input
                      value={reward.chancePercent}
                      onChange={(event) =>
                        updateBoxRewardLine(index, "chancePercent", event.target.value)
                      }
                      placeholder="Chance %"
                    />
                    <span />
                    <button
                      type="button"
                      className="box-builder-remove"
                      onClick={() => removeBoxRewardLine(index)}
                    >
                      Remover
                    </button>
                  </div>
                ))}
              </div>
              <div className="box-builder-replica">
                <button type="button" onClick={() => void replicateBoxForRaces(["acc"])}>
                  Replicar Acc
                </button>
                <button type="button" onClick={() => void replicateBoxForRaces(["bell"])}>
                  Replicar Bell
                </button>
                <button type="button" onClick={() => void replicateBoxForRaces(["cora"])}>
                  Replicar Cora
                </button>
                <button
                  type="button"
                  onClick={() => void replicateBoxForRaces(["acc", "bell", "cora"])}
                >
                  Replicar Todas
                </button>
              </div>
            </section>
          ) : null}

          {activeSidePanel === "gearscore" ? (
            <section className="column-panel">
              <div className="column-panel-header">
                <h2>Gearscore</h2>
                <p>Em breve.</p>
              </div>
            </section>
          ) : null}

          {activeSidePanel === "gems" ? (
            <section className="column-panel">
              <div className="column-panel-header">
                <h2>Gemas</h2>
                <p>Em breve.</p>
              </div>
            </section>
          ) : null}

          {activeSidePanel === "transmog" ? (
            <section className="column-panel">
              <div className="column-panel-header">
                <h2>Transmog</h2>
                <p>Em breve.</p>
              </div>
            </section>
          ) : null}

          {activeView !== "itemCombine" || itemCombineViewMode === "raw" ? (
          <section className="table-section">
            <div className="table-summary">
              <strong>
                {firstItemIndex}-{lastItemIndex}
              </strong>{" "}
              de {totalItems} itens
              {recentSourceTabs.length > 0 ? (
                <nav className="recent-source-tabs inline" aria-label="Guias recentes">
                  <span>Guias recentes</span>
                  {recentSourceTabs.map((sourceFile) => (
                    <button
                      key={sourceFile}
                      type="button"
                      className={sourceFile === selectedSource ? "active" : ""}
                      onClick={() => changeSelectedSource(sourceFile)}
                      disabled={isLoadingItems}
                      title={sourceFile}
                    >
                      <span>{formatSourceLabel(sourceFile)}</span>
                      <span
                        role="button"
                        tabIndex={0}
                        className="recent-source-close"
                        aria-label={`Fechar guia ${formatSourceLabel(sourceFile)}`}
                        title="Fechar guia"
                        onClick={(event) => {
                          event.stopPropagation();
                          closeRecentSource(sourceFile);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            event.stopPropagation();
                            closeRecentSource(sourceFile);
                          }
                        }}
                      >
                        x
                      </span>
                    </button>
                  ))}
                </nav>
              ) : null}
              {isBoxItemOutSelected ? (
                <span>
                  {boxItemOutInvalidChanceRows > 0
                    ? ` | ${boxItemOutInvalidChanceRows} boxes com chance != 10000`
                    : " | chances OK (10000)"}
                </span>
              ) : null}
              {isLoadingItems ? <span>Carregando...</span> : null}
            </div>

            {isItemLootingSelected ? (
              <div className="itemlooting-edit-actions">
                <select
                  value={templateSourceBossKey}
                  onChange={(event) => setTemplateSourceBossKey(event.target.value)}
                >
                  {bossGroups.map((group) => (
                    <option key={group.key} value={group.key}>
                      {group.name} [{formatBossMapLabel(group.bossMap)}]
                    </option>
                  ))}
                </select>
                <button type="button" onClick={saveLootTemplateFromSelectedBoss}>
                  Salvar template
                </button>
                <select
                  value={applyScope}
                  onChange={(event) =>
                    setApplyScope(event.target.value as "sameMap" | "selectedMaps" | "allVisible")
                  }
                >
                  <option value="sameMap">Mesmo mapa</option>
                  <option value="selectedMaps">Mapas selecionados</option>
                  <option value="allVisible">Todos visiveis</option>
                </select>
                <select
                  value={applyRaceMode}
                  onChange={(event) =>
                    changeApplyRaceMode(event.target.value as "auto" | "A" | "B" | "C")
                  }
                >
                  <option value="auto">RaÃ§a auto</option>
                  <option value="A">RaÃ§a A</option>
                  <option value="B">RaÃ§a B</option>
                  <option value="C">RaÃ§a C</option>
                </select>
                <button
                  type="button"
                  onClick={applyLootTemplateToScope}
                  disabled={!lootTemplate}
                >
                  Aplicar template
                </button>
                <button type="button" onClick={undoLastEdit} disabled={undoStack.length === 0}>
                  Desfazer
                </button>
                <button type="button" onClick={redoLastEdit} disabled={redoStack.length === 0}>
                  Refazer
                </button>
                <button
                  type="button"
                  onClick={saveItemLootingEdits}
                  disabled={isSavingEdits || Object.keys(editDrafts).length === 0}
                >
                  {isSavingEdits ? "Salvando..." : "Salvar alteracoes no Excel"}
                </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEditDrafts({});
                      setTemplateAppliedMarks({});
                      setUndoStack([]);
                      setRedoStack([]);
                    }}
                    disabled={isSavingEdits || Object.keys(editDrafts).length === 0}
                  >
                  Descartar
                </button>
              </div>
            ) : null}

            {!isItemLootingSelected && isBoxItemOutSelected ? (
              <div className="itemlooting-edit-actions">
                <button type="button" onClick={undoLastEdit} disabled={undoStack.length === 0}>
                  Desfazer
                </button>
                <button type="button" onClick={redoLastEdit} disabled={redoStack.length === 0}>
                  Refazer
                </button>
                <button
                  type="button"
                  onClick={saveItemLootingEdits}
                  disabled={isSavingEdits || Object.keys(editDrafts).length === 0}
                >
                  {isSavingEdits ? "Salvando..." : "Salvar alteracoes no Excel"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditDrafts({});
                    setTemplateAppliedMarks({});
                    setUndoStack([]);
                    setRedoStack([]);
                  }}
                  disabled={isSavingEdits || Object.keys(editDrafts).length === 0}
                >
                  Descartar
                </button>
              </div>
            ) : null}

            {isItemLootingSelected &&
            applyScope === "selectedMaps" &&
            (allMapOptions.length > 0 || visibleMapOptions.length > 0) ? (
              <div className="itemlooting-map-scope">
                <button
                  type="button"
                  onClick={() =>
                    setSelectedMapsForApply(
                      allMapOptions.length > 0 ? allMapOptions : visibleMapOptions
                    )
                  }
                >
                  Marcar todos
                </button>
                <button type="button" onClick={() => setSelectedMapsForApply([])}>
                  Limpar mapas
                </button>
                {(allMapOptions.length > 0 ? allMapOptions : visibleMapOptions).map((map) => (
                  <label key={map}>
                    <input
                      type="checkbox"
                      checked={selectedMapsForApply.includes(map)}
                      onChange={() => toggleApplyMap(map)}
                    />
                    <span>{map}</span>
                  </label>
                ))}
              </div>
            ) : null}

            <div className="pagination-bar">
              <button
                type="button"
                onClick={() => goToPage(0)}
                disabled={currentPage === 0 || isLoadingItems}
              >
                &lt;&lt;
              </button>
              <button
                type="button"
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage === 0 || isLoadingItems}
              >
                &lt;
              </button>
              <div className="page-number-list" aria-label="Paginas">
                {visiblePageNumbers.map((pageNumber, index) =>
                  pageNumber === "gap" ? (
                    <span key={`gap-${index}`}>...</span>
                  ) : (
                    <button
                      key={pageNumber}
                      type="button"
                      className={pageNumber === currentPage ? "active" : ""}
                      onClick={() => goToPage(pageNumber)}
                      disabled={isLoadingItems}
                    >
                      {pageNumber + 1}
                    </button>
                  )
                )}
              </div>
              <button
                type="button"
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage >= totalPages - 1 || isLoadingItems}
              >
                &gt;
              </button>
              <button
                type="button"
                onClick={() => goToPage(totalPages - 1)}
                disabled={currentPage >= totalPages - 1 || isLoadingItems}
              >
                &gt;&gt;
              </button>
              <span>
                Pagina {currentPage + 1} de {totalPages}
              </span>
              <label className="page-size-select">
                <span>Linhas</span>
                <select
                  value={itemsPerPage}
                  onChange={(event) => {
                    const nextSize = Number(event.target.value);
                    setItemsPerPage(nextSize);
                    savePageSize(nextSize);
                    setCurrentPage(0);
                  }}
                  disabled={isLoadingItems}
                >
                  {PAGE_SIZE_OPTIONS.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
              </label>
              <div className="page-jump">
                <input
                  value={pageInput}
                  onChange={(event) => setPageInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      goToPageInput();
                    }
                  }}
                  inputMode="numeric"
                  placeholder="Pagina"
                  disabled={isLoadingItems}
                />
                <button
                  type="button"
                  onClick={goToPageInput}
                  disabled={!pageInput || isLoadingItems}
                >
                  Ir
                </button>
              </div>
              <div className="pagination-search">
                <button
                  type="button"
                  onClick={() => setShowTableIcons((current) => !current)}
                  title={showTableIcons ? "Ocultar icones da tabela" : "Mostrar icones da tabela"}
                >
                  {showTableIcons ? "Ocultar Ã­cones" : "Mostrar Ã­cones"}
                </button>
                <input
                  value={quickLookup}
                  onChange={(event) => setQuickLookup(event.target.value)}
                  placeholder="Busca rapida global"
                  disabled={!isElectron}
                />
                <button
                  type="button"
                  className="mini-action-button"
                  onClick={clearFilters}
                  disabled={
                    !isElectron ||
                    (!search && filters.length === 0 && Object.keys(columnFilters).length === 0)
                  }
                >
                  Limpar
                </button>
                <button
                  type="button"
                  className="mini-action-button"
                  onClick={loadItems}
                  disabled={!isElectron || isLoadingItems}
                  title="Atualizar"
                >
                  ↻
                </button>
                {quickLookup.trim().length >= 2 ? (
                  <div className="quick-lookup-popover">
                    {isQuickLookupLoading ? <div>Buscando...</div> : null}
                    {!isQuickLookupLoading && quickLookupResults.length === 0 ? (
                      <div>Nenhum item.</div>
                    ) : null}
                    {!isQuickLookupLoading
                      ? quickLookupResults.map((item) => (
                          <button
                            key={`quick-${item.id}`}
                            type="button"
                            onClick={() => {
                              setQuickLookup(`${item.code} - ${item.name}`);
                            }}
                            title={item.sourceFile}
                          >
                            <span>{item.code}</span>
                            <span>{item.name || "-"}</span>
                            <span>{formatSourceLabel(item.sourceFile)}</span>
                          </button>
                        ))
                      : null}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="table-info-strip">
              <span>Arquivo: <strong>{selectedSourceLabel}</strong></span>
              <span>Registros: <strong>{totalItems}</strong></span>
              <span>Perfil: <strong>{profiles.find((profile) => profile.id === activeProfileId)?.name ?? "-"}</strong></span>
              <span>Aba: <strong>{selectedSheetName || extractSheetNameFromSource(selectedSource) || "-"}</strong></span>
              <span>Dicionario: <strong>{dictionaries.find((dictionary) => dictionary.key === selectedSourceDictionary)?.label ?? "-"}</strong></span>
              <div className="table-info-actions">
                <button type="button" onClick={autoFitAllVisibleColumns} disabled={!isElectron}>
                  Auto-fit
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const defaults = /itemlooting/i.test(selectedSource)
                      ? getAutoColumnWidthsForItems(items, sourceColumnLabels)
                      : DEFAULT_COLUMN_WIDTHS;
                    setColumnWidths(defaults);
                    saveColumnWidthsForSource(selectedSource, defaults);
                  }}
                  disabled={!isElectron}
                >
                  Resetar larguras
                </button>
              </div>
            </div>

            <div
              className="table-top-scroll"
              ref={tableTopScrollRef}
              onScroll={() => syncTableScroll("top")}
              aria-label="Scroll horizontal da tabela"
            >
              <div style={{ width: `${Math.max(topScrollContentWidth, tableWidth)}px` }} />
            </div>

            <div
              className={`table-wrap ${isItemLootingSelected ? "itemlooting-compact" : ""}`}
              ref={tableWrapRef}
              onScroll={() => {
                syncTableScroll("table");
                setTableScrollTop(tableWrapRef.current?.scrollTop ?? 0);
              }}
              tabIndex={0}
              onKeyDown={(event) => {
                const isModifier = event.ctrlKey || event.metaKey;
                const key = event.key.toLowerCase();
                if (isModifier && key === "c") {
                  event.preventDefault();
                  void copySelectedCellsToClipboard();
                }
                if (isModifier && key === "z" && !event.shiftKey) {
                  event.preventDefault();
                  undoLastEdit();
                }
                if (isModifier && (key === "y" || (key === "z" && event.shiftKey))) {
                  event.preventDefault();
                  redoLastEdit();
                }
              }}
            >
              <table>
                <thead>
                  <tr>
                    {selectedColumns.map((column) => (
                      <th
                        key={column.key}
                        style={
                          {
                            "--column-width": `${getColumnWidth(column.key)}px`,
                          } as CSSProperties
                        }
                      >
                        <div className={`column-header-control ${column.key === "excelRow" ? "row-index-header" : ""}`}>
                          <span>{column.label}</span>
                          {isGearScoreCsvSelected ? (
                            <button
                              type="button"
                              className={`column-filter-button ${
                                csvSortField === column.key ? "active" : ""
                              }`}
                              onClick={() => toggleGearCsvSort(column.key)}
                              title={`Ordenar ${column.label}`}
                              aria-label={`Ordenar ${column.label}`}
                            >
                              {csvSortField === column.key
                                ? csvSortDirection === "asc"
                                  ? "â†‘"
                                  : "â†“"
                                : "â†•"}
                            </button>
                          ) : null}
                          {isIconColumn(column.key) ? (
                            <button
                              type="button"
                              className={`column-filter-button ${showTableIcons ? "active" : ""}`}
                              onClick={() => setShowTableIcons((current) => !current)}
                              title={showTableIcons ? "Ocultar icones" : "Mostrar icones"}
                              aria-label={showTableIcons ? "Ocultar icones" : "Mostrar icones"}
                            >
                              *
                            </button>
                          ) : null}
                          {isColumnFilterable(column.key) ? (
                            <button
                              type="button"
                              className={`column-filter-button ${
                                columnFilters[column.key]?.length ? "active" : ""
                              }`}
                              onClick={() => openFilterForColumn(column.key)}
                              title={`Filtrar ${column.label}`}
                              aria-label={`Filtrar ${column.label}`}
                           >&#128269;</button>
                          ) : null}
                            <div
                              className="column-resize-handle"
                              onMouseDown={(event) =>
                                startColumnResize(column.key, event)
                              }
                              onDoubleClick={() => autoFitColumnWidth(column.key)}
                              role="separator"
                              aria-orientation="vertical"
                              aria-label={`Redimensionar coluna ${column.label}`}
                              title={`Arraste para ajustar ${column.label}`}
                            />
                          {openColumnFilter === column.key ? (
                            <div
                              className="column-filter-popover"
                              ref={columnFilterRef}
                            >
                              <button
                                type="button"
                                className="column-filter-clear"
                                onClick={() => clearColumnFilter(column.key)}
                                disabled={!columnFilters[column.key]?.length}
                              >
                                Limpar filtro de {column.label}
                              </button>
                              {/socket_gem_records\.csv$/i.test(selectedSource) &&
                              column.key === "extra15" ? (
                                <select
                                  value={selectedSourceDictionary}
                                  onChange={(event) => {
                                    void changeSourceDictionary(event.target.value);
                                  }}
                                >
                                  {dictionaries.map((dictionary) => (
                                    <option key={dictionary.key} value={dictionary.key}>
                                      Dicionario: {dictionary.label}
                                    </option>
                                  ))}
                                </select>
                              ) : null}

                              <input
                                value={columnValueSearch}
                                onChange={(event) => {
                                  const term = event.target.value;
                                  setColumnValueSearch(term);
                                  const normalized = term.trim().toLowerCase();
                                  if (!normalized) {
                                    setDraftColumnValues(columnFilterValues);
                                  } else {
                                    setDraftColumnValues(
                                      columnFilterValues.filter((value) =>
                                        String(value ?? "").toLowerCase().includes(normalized)
                                      )
                                    );
                                  }
                                }}
                                placeholder={`Buscar ${column.label}`}
                                autoFocus
                              />

                              <div className="column-filter-values">
                                <label className="column-filter-select-all">
                                  <input
                                    type="checkbox"
                                    checked={
                                      columnFilterValues.length > 0 &&
                                      draftColumnValues.length ===
                                        columnFilterValues.length
                                    }
                                    onChange={(event) =>
                                      setDraftColumnValues(
                                        event.target.checked ? columnFilterValues : []
                                      )
                                    }
                                    disabled={isLoadingColumnValues}
                                  />
                                  (Selecionar Tudo)
                                </label>

                                {isLoadingColumnValues ? (
                                  <div className="column-filter-status">
                                    Carregando...
                                  </div>
                                ) : null}

                                {!isLoadingColumnValues &&
                                columnFilterValues.length === 0 ? (
                                  <div className="column-filter-status">
                                    Nenhum valor.
                                  </div>
                                ) : null}

                                {columnFilterValues.map((value) => (
                                  <label key={value} className="column-filter-value">
                                    <input
                                      type="checkbox"
                                      checked={draftColumnValues.includes(value)}
                                      onChange={() => toggleDraftColumnValue(value)}
                                    />
                                    <span>
                                      {formatColumnFilterValue(openColumnFilter, value)}
                                    </span>
                                  </label>
                                ))}
                              </div>

                              <div className="column-filter-footer">
                                <button
                                  type="button"
                                  onClick={() => applyColumnFilter(column.key)}
                                >
                                  OK
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setOpenColumnFilter(null)}
                                >
                                  Cancelar
                                </button>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shouldVirtualize && topSpacerHeight > 0 ? (
                    <tr className="virtual-spacer-row" aria-hidden="true">
                      <td colSpan={selectedColumns.length} style={{ height: `${topSpacerHeight}px` }} />
                    </tr>
                  ) : null}
                  {visibleRows.map((item, visibleIndex) => {
                    const rowIndex = shouldVirtualize ? virtualStartIndex + visibleIndex : visibleIndex;
                    return (
                    <tr key={item.id} className={getItemRowClass(item)}>
                      {selectedColumns.map((column, columnIndex) => (
                        <td
                          key={column.key}
                          className={`resizable-cell ${getItemCellClass(item, column.key)} ${
                            editDrafts[item.id]?.[column.key] !== undefined
                              ? "edited-cell"
                              : ""
                          } ${
                            templateAppliedMarks[item.id] !== undefined
                              ? `template-applied-${templateAppliedMarks[item.id]}`
                              : ""
                          } ${isCellInRange(rowIndex, columnIndex) ? "selected-cell" : ""}`}
                          onMouseDown={(event) => {
                            if (event.altKey) {
                              event.preventDefault();
                              applyQuickColumnFilter(
                                column.key,
                                getCellValue(item, column.key),
                                event.shiftKey
                              );
                              return;
                            }
                            handleCellSelection(rowIndex, columnIndex, event.shiftKey);
                          }}
                          style={
                            {
                              "--column-width": `${getColumnWidth(column.key)}px`,
                              ...(column.key === "excelRow"
                                ? { width: "52px", minWidth: "52px", maxWidth: "52px" }
                                : {}),
                            } as CSSProperties
                          }
                          title={String(getCellDisplayValue(item, column.key) || "")}
                        >
                          {isCivilColumn(column.key) ? (
                            (() => {
                              const civilValue = String(getCellDisplayValue(item, column.key) || "");
                              const icon = getCivilIconInfo(civilValue);
                              return icon ? (
                                <span
                                  className="race-icon-cell"
                                  title={`${icon.label} (${civilValue})`}
                                  aria-label={`${icon.label} (${civilValue})`}
                                >
                                  <img src={icon.src} alt={icon.label} />
                                </span>
                              ) : (
                                civilValue || "-"
                              );
                            })()
                          ) : isIconColumn(column.key) ? (
                            <div className="table-icon-preview-cell">
                              {(() => {
                                const iconDraftKey = `${item.id}:${column.key}`;
                                const iconLiveValue =
                                  iconEditBuffer[iconDraftKey] ?? String(getCellValue(item, column.key) ?? "");
                                return (
                                  <>
                              {showTableIcons ? (
                                <span
                                  className="box-icon-preview"
                                  style={getItemIconPreviewStyle(
                                    item,
                                    iconLiveValue,
                                    rfIconSheets
                                  )}
                                />
                              ) : null}
                              {isEditableCell(item, column.key) ? (
                                <input
                                  className="table-cell-input table-icon-id-input"
                                  value={iconLiveValue}
                                  onChange={(event) => {
                                    const nextValue = event.target.value;
                                    setIconEditBuffer((current) => ({
                                      ...current,
                                      [iconDraftKey]: nextValue,
                                    }));
                                  }}
                                  onBlur={(event) =>
                                    {
                                      const nextValue = event.target.value;
                                      updateItemCellDraft(item.id, column.key, nextValue);
                                      setIconEditBuffer((current) => ({
                                        ...current,
                                        [iconDraftKey]: nextValue,
                                      }));
                                    }
                                  }
                                  onFocus={(event) => {
                                    setIconEditBuffer((current) => ({
                                      ...current,
                                      [iconDraftKey]: String(getCellValue(item, column.key) ?? ""),
                                    }));
                                    event.currentTarget.select();
                                  }}
                                  onMouseDown={(event) => event.stopPropagation()}
                                  onClick={(event) => event.stopPropagation()}
                                  onKeyDown={(event) => {
                                    event.stopPropagation();
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      updateItemCellDraft(
                                        item.id,
                                        column.key,
                                        event.currentTarget.value
                                      );
                                      event.currentTarget.blur();
                                    }
                                  }}
                                />
                              ) : (
                                <span className="table-icon-id-text">
                                  {getCellDisplayValue(item, column.key) || "-"}
                                </span>
                              )}
                                  </>
                                );
                              })()}
                            </div>
                          ) : isEditableCell(item, column.key) ? (
                            <input
                              className="table-cell-input"
                              value={getCellDisplayValue(item, column.key)}
                              onChange={(event) =>
                                updateItemCellDraft(item.id, column.key, event.target.value)
                              }
                              onPaste={(event) => {
                                const text = event.clipboardData.getData("text/plain");
                                if (text.includes("\t") || text.includes("\n")) {
                                  event.preventDefault();
                                  pasteTsvIntoGrid(rowIndex, columnIndex, text);
                                }
                              }}
                              onFocus={(event) => event.currentTarget.select()}
                              onClick={(event) => {
                                if (event.altKey) {
                                  event.preventDefault();
                                  applyQuickColumnFilter(
                                    column.key,
                                    getCellValue(item, column.key),
                                    event.shiftKey
                                  );
                                  return;
                                }
                                handleCellSelection(rowIndex, columnIndex, event.shiftKey);
                                event.currentTarget.select();
                              }}
                              disabled={isSavingEdits}
                            />
                          ) : (
                            getCellDisplayValue(item, column.key) || "-"
                          )}
                        </td>
                      ))}
                    </tr>
                    );
                  })}
                  {shouldVirtualize && bottomSpacerHeight > 0 ? (
                    <tr className="virtual-spacer-row" aria-hidden="true">
                      <td colSpan={selectedColumns.length} style={{ height: `${bottomSpacerHeight}px` }} />
                    </tr>
                  ) : null}
                </tbody>
              </table>

              {items.length === 0 ? (
                <div className="empty-state">
                  Nenhum item encontrado. Importe um Excel ou ajuste a busca.
                </div>
              ) : null}
            </div>
          </section>
          ) : null}
        </>
      ) : activeView === "effects" ? (
        <section className="dictionary-section">
          <div className="dictionary-header">
            <div>
              <h2>Dicionario de efeitos</h2>
              <p>Use contexto vazio para regra geral, ou preencha Type para uma excecao.</p>
            </div>

            <div className="dictionary-actions">
              <select
                value={selectedDictionaryKey}
                onChange={(event) => setSelectedDictionaryKey(event.target.value)}
                disabled={!isElectron}
              >
                {dictionaries.map((dictionary) => (
                  <option key={dictionary.key} value={dictionary.key}>
                    {dictionary.label}
                  </option>
                ))}
              </select>

              <input
                value={effectSearch}
                onChange={(event) => setEffectSearch(event.target.value)}
                placeholder="Buscar Eff, descricao, Type"
                disabled={!isElectron}
              />
              <button type="button" onClick={addEffectEntry} disabled={!isElectron}>
                Adicionar efeito
              </button>
            </div>
          </div>

          <div className="table-summary">
            <strong>{effectEntries.length}</strong> efeitos exibidos
            {isLoadingEffects ? <span>Carregando...</span> : null}
          </div>

          <div className="dictionary-list">
            {effectEntries.map((entry) => (
              <div className="dictionary-row" key={entry.draftId}>
                <input
                  value={entry.itemType}
                  onChange={(event) =>
                    updateEffectEntry(entry.draftId, {
                      itemType: event.target.value,
                    })
                  }
                  placeholder="Type vazio = global"
                />

                <input
                  value={entry.effCode}
                  onChange={(event) =>
                    updateEffectEntry(entry.draftId, {
                      effCode: event.target.value,
                    })
                  }
                  placeholder="Eff"
                />

                <input
                  value={entry.name}
                  onChange={(event) =>
                    updateEffectEntry(entry.draftId, {
                      name: event.target.value,
                    })
                  }
                  placeholder="Nome curto"
                />

                <input
                  value={entry.description}
                  onChange={(event) =>
                    updateEffectEntry(entry.draftId, {
                      description: event.target.value,
                    })
                  }
                  placeholder="Descricao"
                />

                <input
                  value={entry.unitHint}
                  onChange={(event) =>
                    updateEffectEntry(entry.draftId, {
                      unitHint: event.target.value,
                    })
                  }
                  placeholder="Dica de unidade"
                />

                <div className="row-actions">
                  <button type="button" onClick={() => saveEffectEntry(entry)}>
                    Salvar
                  </button>
                  <button type="button" onClick={() => deleteEffectEntry(entry)}>
                    Remover
                  </button>
                </div>
              </div>
            ))}

            {effectEntries.length === 0 ? (
              <div className="empty-state">
                Nenhum efeito encontrado no dicionario.
              </div>
            ) : null}
          </div>
        </section>
      ) : (
        <section className="panel-placeholder">
          <h2>Em breve</h2>
        </section>
      )}
    </main>
  );
}

function getItemRowClass(item: LootItem) {
  const classes: string[] = [];
  if (!/itemlooting/i.test(item.sourceFile)) {
    const gradeClass = getGradeClass(item.grade);
    if (gradeClass) {
      classes.push(gradeClass);
    }
  }
  if (/socket_.*\.csv$/i.test(String(item.sourceFile || ""))) {
    const row = Number(item.excelRow ?? 0);
    if (Number.isFinite(row) && row >= 1 && row <= 7) {
      classes.push("hgk-example-row");
    }
  }
  return classes.join(" ");
}

function getItemCellClass(item: LootItem, column: ColumnKey) {
  if (
    /itemlooting/i.test(item.sourceFile) &&
    item.boss === "Boss" &&
    column === "name"
  ) {
    return `${getMapClass(item.bossMap)}-cell`;
  }

  return "";
}

function getMapClass(mapName: string) {
  const normalized = String(mapName ?? "").trim().toLowerCase();

  if (!normalized) {
    return "";
  }

  if (normalized.includes("cauldron")) {
    return "map-cauldron";
  }

  if (normalized.includes("elan")) {
    return "map-elan";
  }

  if (normalized.includes("exile_land")) {
    return "map-exile-land";
  }

  if (normalized.includes("medicallabs")) {
    return "map-medicallabs";
  }

  if (normalized.includes("mountain_beast")) {
    return "map-mountain-beast";
  }

  if (normalized.includes("neutral")) {
    if (/(^|[^a-z0-9])neutral[^a-z0-9]*a([^a-z0-9]|$)/i.test(normalized)) {
      return "map-neutral-a";
    }

    if (/(^|[^a-z0-9])neutral[^a-z0-9]*b([^a-z0-9]|$)/i.test(normalized)) {
      return "map-neutral-b";
    }

    if (/(^|[^a-z0-9])neutral[^a-z0-9]*c([^a-z0-9]|$)/i.test(normalized)) {
      return "map-neutral-c";
    }
  }

  if (normalized.includes("platform")) {
    return "map-platform";
  }

  if (normalized.includes("resources")) {
    return "map-resources";
  }

  if (normalized.includes("sette")) {
    return "map-sette";
  }

  return "";
}

function getBoxIconPreviewStyle(
  reward: BoxRewardDraft,
  rfIconSheets: Array<{ fileName: string; width: number; height: number; cols: number; rows: number }>
): CSSProperties | undefined {
  const source = String(reward.itemSourceFile || "").toLowerCase();
  if (!/weaponitem/.test(source)) {
    return undefined;
  }
  const iconIndex = Number(String(reward.itemIcon || "").trim());
  if (!Number.isInteger(iconIndex) || iconIndex < 0) {
    return undefined;
  }
  const sheetPrefix = "item-1-";
  const weaponSheets = rfIconSheets
    .filter((sheet) => sheet.fileName.toLowerCase().startsWith(sheetPrefix))
    .sort((a, b) => {
      const na = Number(a.fileName.replace(/[^0-9]/g, ""));
      const nb = Number(b.fileName.replace(/[^0-9]/g, ""));
      return na - nb;
    });
  const firstSheet = weaponSheets[0];
  if (!firstSheet) {
    return undefined;
  }
  const columns = Math.max(1, Number(firstSheet.cols) || 1);
  const rows = Math.max(1, Number(firstSheet.rows) || 1);
  const iconsPerSheet = columns * rows;
  const sheetNumber = Math.floor(iconIndex / iconsPerSheet) + 1;
  const indexInSheet = iconIndex % iconsPerSheet;
  const tileSize = 64;
  const previewSize = 28;
  const scale = previewSize / tileSize;
  const x = (indexInSheet % columns) * tileSize;
  const y = Math.floor(indexInSheet / columns) * tileSize;
  return {
    backgroundImage: `url('/rf-icons/item-1-${sheetNumber}.png')`,
    backgroundPosition: `-${Math.round(x * scale)}px -${Math.round(y * scale)}px`,
    backgroundSize: `${Math.round(columns * tileSize * scale)}px auto`,
  };
}

function getItemIconPreviewStyle(
  item: LootItem,
  iconValue: string,
  rfIconSheets: Array<{ fileName: string; width: number; height: number; cols: number; rows: number }>
): CSSProperties | undefined {
  const iconIndex = Number(String(iconValue ?? "").trim());
  if (!Number.isInteger(iconIndex) || iconIndex < 0) {
    return undefined;
  }
  const source = String(item.sourceFile || "").toLowerCase();
  const family =
    /weaponitem/.test(source) ? 1 :
    /resourceitem/.test(source) ? 9 :
    /bootyitem/.test(source) ? 13 :
    /helmetitem/.test(source) ? 14 :
    /upperitem/.test(source) ? 15 :
    /loweritem/.test(source) ? 16 :
    /gauntletitem/.test(source) ? 17 :
    /shoeitem/.test(source) ? 18 :
    /shielditem/.test(source) ? 19 :
    /(ringitem|amuletitem|cloakitem)/.test(source) ? 20 :
    /town/.test(source) ? 22 :
    /boxitem/.test(source) ? 6 :
    null;
  if (!family) {
    return undefined;
  }
  const prefix = `item-${family}-`;
  const legacySheet = rfIconSheets.find((sheet) => {
    const name = sheet.fileName.toLowerCase();
    return name === `item-1-${family}.png` || name === `item-1-${family}.dds`;
  });
  const pagedSheets = rfIconSheets
    .filter((sheet) => sheet.fileName.toLowerCase().startsWith(prefix))
    .sort((a, b) => a.fileName.localeCompare(b.fileName, undefined, { numeric: true }));
  const useLegacySingleSheet = Boolean(legacySheet);
  const firstSheet = useLegacySingleSheet ? legacySheet : pagedSheets[0];
  if (!firstSheet) return undefined;
  const columns = Math.max(1, Number(firstSheet.cols) || 1);
  const rows = Math.max(1, Number(firstSheet.rows) || 1);
  const iconsPerSheet = columns * rows;
  const sheetNumber = Math.floor(iconIndex / iconsPerSheet) + 1;
  const indexInSheet = iconIndex % iconsPerSheet;
  const tileSize = 64;
  const previewSize = 28;
  const scale = previewSize / tileSize;
  const x = (indexInSheet % columns) * tileSize;
  const y = Math.floor(indexInSheet / columns) * tileSize;
  return {
    backgroundImage: useLegacySingleSheet
      ? `url('/rf-icons/item-1-${family}.png')`
      : `url('/rf-icons/item-${family}-${sheetNumber}.png')`,
    backgroundPosition: `-${Math.round(x * scale)}px -${Math.round(y * scale)}px`,
    backgroundSize: `${Math.round(columns * tileSize * scale)}px auto`,
  };
}

function getGradeClass(grade: string) {
  const normalized = String(grade ?? "").trim().toLowerCase();

  switch (normalized) {
    case "0":
      return "grade-0";
    case "1":
      return "grade-1";
    case "2":
      return "grade-2";
    case "3":
      return "grade-3";
    case "4":
      return "grade-4";
    case "8":
      return "grade-8";
    case "10":
      return "grade-10";
    case "nova":
    case "new":
      return "grade-nova";
    default:
      return "";
  }
}

function getVisiblePageNumbers(currentPage: number, totalPages: number) {
  const start = Math.max(0, Math.min(currentPage - 1, totalPages - 3));
  const end = Math.min(totalPages - 1, start + 2);
  const result: Array<number | "gap"> = [];

  for (let page = start; page <= end; page++) {
    result.push(page);
  }

  return result;
}

function formatSourceLabel(sourceFile: string) {
  const normalized = sourceFile.replaceAll("\\", "/");
  const parts = normalized.split("/");
  const parent = parts.length > 1 ? parts[parts.length - 2] : "";
  const fileName = parts[parts.length - 1] ?? sourceFile;
  const folderMatch = parent.match(/\d+_[^/]+/);

  if (folderMatch) {
    return folderMatch[0];
  }

  return fileName.replace(/\.xlsx$/i, "");
}

function extractSheetNameFromSource(sourceFile: string) {
  const match = String(sourceFile ?? "").match(/::([^/\\]+)\.xlsx$/i);
  return match ? match[1] : "";
}

function getColumnFiltersForLookup(
  columnFilters: ColumnFilters,
  currentColumn: ColumnKey
) {
  const nextFilters = { ...columnFilters };
  delete nextFilters[currentColumn];
  return nextFilters;
}

function ImportProgressBar({ progress }: { progress: ImportProgress }) {
  const stageLabel = getImportStageLabel(progress.stage);
  const percent =
    progress.total > 0
      ? Math.min(Math.round((progress.inserted / progress.total) * 100), 100)
      : 8;
  const sourceLabel = progress.sourceFile
    ? formatSourceLabel(progress.sourceFile)
    : "Selecionando arquivo";

  return (
    <div className="import-progress" aria-live="polite">
      <div className="import-progress-header">
        <strong>{stageLabel}</strong>
        <span>
          Arquivo {progress.fileIndex} de {progress.fileCount}: {sourceLabel}
        </span>
      </div>
      <div className="import-progress-track">
        <div
          className={progress.total > 0 ? "" : "indeterminate"}
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="import-progress-details">
        {progress.total > 0 ? (
          <span>
            {progress.inserted} de {progress.total} linhas ({percent}%)
          </span>
        ) : (
          <span>Preparando importacao...</span>
        )}
        {progress.effectsInserted > 0 ? (
          <span>{progress.effectsInserted} efeitos</span>
        ) : null}
      </div>
    </div>
  );
}

function getImportStageLabel(stage: ImportProgress["stage"]) {
  switch (stage) {
    case "reading":
      return "Lendo Excel";
    case "parsing":
      return "Processando linhas";
    case "saving":
      return "Salvando no banco";
    case "done":
      return "Importacao concluida";
    default:
      return "Importando";
  }
}

function formatColumnFilterValue(column: ColumnKey | null, value: string) {
  if (!value) {
    return "(vazio)";
  }

  if (column === "bossMap") {
    return formatBossMapLabel(value);
  }

  return value;
}

function formatBossMapLabel(value: string) {
  return String(value ?? "")
    .split(",")
    .map((part) => part.trim().replace(/_boss\.ini$/i, ""))
    .filter((part) => part !== "")
    .join(", ");
}

function splitBossMaps(value: string) {
  return formatBossMapLabel(value)
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

function findItemLootingColumnKey(
  sourceColumnLabels: Partial<Record<ColumnKey, string>>,
  expectedName: string,
  fallback: ColumnKey
) {
  const expected = expectedName.toLowerCase();
  const match = ITEM_COLUMNS.find((column) => {
    const label = String(sourceColumnLabels[column.key] || column.label)
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "");
    return label === expected;
  });

  return (match?.key ?? fallback) as ColumnKey;
}

function detectRaceFromBossMap(value: string): RaceKey {
  const normalized = formatBossMapLabel(value).toLowerCase();

  if (normalized.includes("neutrala") || normalized.includes("acc")) {
    return "A";
  }

  if (normalized.includes("neutralb") || normalized.includes("bell")) {
    return "B";
  }

  if (normalized.includes("neutralc") || normalized.includes("cora")) {
    return "C";
  }

  return "unknown";
}

function convertLootValueForRace(value: string, fromRace: RaceKey, toRace: RaceKey) {
  if (!value || fromRace === "unknown" || toRace === "unknown" || fromRace === toRace) {
    return value;
  }

  if (/^\d+(\.\d+)?$/.test(value.trim())) {
    return value;
  }

  let next = value;
  const wordMap: Record<RaceKey, string> = {
    A: "acc",
    B: "bell",
    C: "cora",
    unknown: "",
  };

  next = next.replace(/accretia|acc/gi, wordMap[toRace]);
  next = next.replace(/bellato|bell/gi, wordMap[toRace]);
  next = next.replace(/cora/gi, wordMap[toRace]);

  if (next.length >= 3) {
    const chars = next.split("");
    const fromChar = fromRace.toLowerCase();
    const toChar = toRace.toLowerCase();

    if (chars[2]?.toLowerCase() === fromChar) {
      chars[2] = chars[2] === chars[2].toUpperCase() ? toChar.toUpperCase() : toChar;
      next = chars.join("");
    }
  }

  return next;
}

function hashString(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return hash;
}

function formatChanceForInput(value: string) {
  const numericValue = Number(String(value ?? "").replace(",", "."));

  if (!Number.isFinite(numericValue)) {
    return String(value ?? "");
  }

  const percent = (numericValue / RF_CHANCE_MAX) * 100;
  const rounded = Math.round(percent * 10000) / 10000;
  return String(rounded).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
}

function parsePercentToRfChance(value: string) {
  const normalized = String(value ?? "").trim().replace(",", ".");

  if (!normalized) {
    return "";
  }

  const percent = Number(normalized);

  if (!Number.isFinite(percent)) {
    return String(value ?? "");
  }

  const clamped = Math.min(Math.max(percent, 0), 100);
  return String(Math.round((clamped / 100) * RF_CHANCE_MAX));
}

function toDraftEffectEntry(entry: EffectDictionaryEntry): DraftEffectEntry {
  return {
    ...entry,
    draftId: entry.id ? `saved-${entry.id}` : `new-${Date.now()}`,
  };
}

function loadColumnsForSource(sourceFile: string): ColumnKey[] {
  const saved = window.localStorage.getItem(getColumnStorageKey(sourceFile));

  if (!saved) {
    if (/itemlooting/i.test(sourceFile)) {
      return [
        "name",
        "boss",
        "bossMap",
        "extra1",
        "extra2",
        "extra3",
        "extra4",
        "extra5",
        "extra6",
        "extra7",
        "extra8",
        "extra9",
        "extra10",
        "extra11",
        "extra12",
        "extra13",
        "extra14",
        "extra15",
      ];
    }

    return DEFAULT_COLUMNS;
  }

  try {
    const parsed = JSON.parse(saved);

    if (!Array.isArray(parsed)) {
      return DEFAULT_COLUMNS;
    }

    const validColumns = parsed.filter((key): key is ColumnKey =>
      ITEM_COLUMNS.some((column) => column.key === key)
    );

    return validColumns.length > 0 ? validColumns : DEFAULT_COLUMNS;
  } catch {
    return DEFAULT_COLUMNS;
  }
}

function hasSavedColumnsForSource(sourceFile: string) {
  return window.localStorage.getItem(getColumnStorageKey(sourceFile)) !== null;
}

function getItemPageStorageKey(
  sourceFile: string,
  search: string,
  filters: DraftFilter[],
  columnFilters: ColumnFilters
) {
  const filterKey = filters
    .map(({ field, operator, value }) => `${field}:${operator}:${value}`)
    .join("|");
  const columnFilterKey = Object.entries(columnFilters)
    .map(([field, values]) => `${field}:${values?.join(",")}`)
    .join("|");

  return `${ITEM_PAGE_STORAGE_KEY}.${sourceFile}.${search}.${filterKey}.${columnFilterKey}`;
}

function loadSavedPage(
  sourceFile: string,
  search: string,
  filters: DraftFilter[],
  columnFilters: ColumnFilters,
  pageSize: number
) {
  const saved = window.localStorage.getItem(
    getItemPageStorageKey(sourceFile, search, filters, columnFilters) + `.${pageSize}`
  );
  const page = Number(saved);

  return Number.isInteger(page) && page >= 0 ? page : 0;
}

function saveCurrentPage(
  sourceFile: string,
  search: string,
  filters: DraftFilter[],
  columnFilters: ColumnFilters,
  pageSize: number,
  page: number
) {
  window.localStorage.setItem(
    getItemPageStorageKey(sourceFile, search, filters, columnFilters) + `.${pageSize}`,
    String(page)
  );
}

function loadSavedPageSize() {
  const saved = Number(window.localStorage.getItem(ITEM_PAGE_SIZE_STORAGE_KEY));
  return PAGE_SIZE_OPTIONS.includes(saved) ? saved : 500;
}

function savePageSize(pageSize: number) {
  window.localStorage.setItem(ITEM_PAGE_SIZE_STORAGE_KEY, String(pageSize));
}

function saveColumnsForSource(sourceFile: string, columns: ColumnKey[]) {
  window.localStorage.setItem(
    getColumnStorageKey(sourceFile),
    JSON.stringify(columns)
  );
}

function getFilterStateStorageKey(sourceFile: string) {
  return `${FILTER_STATE_STORAGE_PREFIX}${sourceFile || "all"}`;
}

function saveFilterStateForSource(
  sourceFile: string,
  search: string,
  filters: DraftFilter[],
  columnFilters: ColumnFilters
) {
  const payload = {
    search,
    filters: filters.map(({ field, operator, value }) => ({
      field,
      operator,
      value,
    })),
    columnFilters,
  };

  window.localStorage.setItem(
    getFilterStateStorageKey(sourceFile),
    JSON.stringify(payload)
  );
}

function loadFilterStateForSource(sourceFile: string): {
  search: string;
  filters: DraftFilter[];
  columnFilters: ColumnFilters;
} {
  const saved = window.localStorage.getItem(getFilterStateStorageKey(sourceFile));

  if (!saved) {
    return {
      search: "",
      filters: [],
      columnFilters: {},
    };
  }

  try {
    const parsed = JSON.parse(saved);
    const parsedSearch = String(parsed?.search ?? "");
    const parsedFilters = Array.isArray(parsed?.filters)
      ? parsed.filters
          .map((filter: LootItemFilter, index: number) => ({
            id: Date.now() + index,
            field: filter.field,
            operator: filter.operator,
            value: String(filter.value ?? ""),
          }))
          .filter(
            (filter: DraftFilter) =>
              ITEM_COLUMNS.some((column) => column.key === filter.field)
          )
      : [];
  const parsedColumnFilters =
      parsed?.columnFilters && typeof parsed.columnFilters === "object"
        ? Object.fromEntries(
            Object.entries(parsed.columnFilters).filter(
              ([field, values]) =>
                ITEM_COLUMNS.some((column) => column.key === field) &&
                Array.isArray(values)
            )
          ) as Partial<Record<ColumnKey, string[]>>
        : {};

    return {
      search: parsedSearch,
      filters: parsedFilters,
      columnFilters: parsedColumnFilters,
    };
  } catch {
    return {
      search: "",
      filters: [],
      columnFilters: {},
    };
  }
}

function loadColumnPanelCollapsed() {
  return window.localStorage.getItem(COLUMN_PANEL_COLLAPSED_KEY) === "true";
}

function saveColumnPanelCollapsed(isCollapsed: boolean) {
  window.localStorage.setItem(COLUMN_PANEL_COLLAPSED_KEY, String(isCollapsed));
}

function loadFilterPanelCollapsed() {
  return window.localStorage.getItem(FILTER_PANEL_COLLAPSED_KEY) === "true";
}

function saveFilterPanelCollapsed(isCollapsed: boolean) {
  window.localStorage.setItem(FILTER_PANEL_COLLAPSED_KEY, String(isCollapsed));
}

function getColumnStorageKey(sourceFile: string) {
  return `${COLUMN_STORAGE_PREFIX}${sourceFile || "all"}`;
}

function getHiddenColumnOptionsStorageKey(sourceFile: string) {
  return `${HIDDEN_COLUMN_OPTIONS_PREFIX}${sourceFile || "all"}`;
}

function loadHiddenColumnOptionsForSource(sourceFile: string): ColumnKey[] {
  const saved = window.localStorage.getItem(
    getHiddenColumnOptionsStorageKey(sourceFile)
  );

  if (!saved) {
    return sourceFile ? [] : DEFAULT_HIDDEN_COLUMN_OPTIONS_FOR_ALL;
  }

  try {
    const parsed = JSON.parse(saved);

    if (!Array.isArray(parsed)) {
      return sourceFile ? [] : DEFAULT_HIDDEN_COLUMN_OPTIONS_FOR_ALL;
    }

    return parsed.filter((key): key is ColumnKey =>
      ITEM_COLUMNS.some((column) => column.key === key)
    );
  } catch {
    return sourceFile ? [] : DEFAULT_HIDDEN_COLUMN_OPTIONS_FOR_ALL;
  }
}

function saveHiddenColumnOptionsForSource(
  sourceFile: string,
  columns: ColumnKey[]
) {
  window.localStorage.setItem(
    getHiddenColumnOptionsStorageKey(sourceFile),
    JSON.stringify(columns)
  );
}

function loadRecentSources() {
  const saved = window.localStorage.getItem(RECENT_SOURCES_STORAGE_KEY);

  if (!saved) {
    return [];
  }

  try {
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed)
      ? parsed.filter((sourceFile): sourceFile is string => typeof sourceFile === "string")
      : [];
  } catch {
    return [];
  }
}

function saveRecentSources(sourceFiles: string[]) {
  window.localStorage.setItem(RECENT_SOURCES_STORAGE_KEY, JSON.stringify(sourceFiles));
}

function loadLastSelectedSource() {
  return window.localStorage.getItem(LAST_SELECTED_SOURCE_KEY) || "";
}

function saveLastSelectedSource(sourceFile: string) {
  if (!sourceFile) {
    window.localStorage.removeItem(LAST_SELECTED_SOURCE_KEY);
    return;
  }
  window.localStorage.setItem(LAST_SELECTED_SOURCE_KEY, sourceFile);
}

function getColumnWidthStorageKey(sourceFile: string) {
  return `${COLUMN_WIDTH_STORAGE_PREFIX}${sourceFile || "all"}`;
}

function hasSavedColumnWidthsForSource(sourceFile: string) {
  return window.localStorage.getItem(getColumnWidthStorageKey(sourceFile)) !== null;
}

function loadColumnWidthsForSource(
  sourceFile: string
): Partial<Record<ColumnKey, number>> {
  const saved = window.localStorage.getItem(getColumnWidthStorageKey(sourceFile));

  if (!saved) {
    return DEFAULT_COLUMN_WIDTHS;
  }

  try {
    const parsed = JSON.parse(saved);

    if (!parsed || typeof parsed !== "object") {
      return DEFAULT_COLUMN_WIDTHS;
    }

    const loaded = Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [ColumnKey, number] => {
        const [key, value] = entry;
        return (
          ITEM_COLUMNS.some((column) => column.key === key) &&
          typeof value === "number" &&
          Number.isFinite(value)
        );
      })
    );
    return {
      ...loaded,
      excelRow:
        typeof loaded.excelRow === "number" && Number.isFinite(loaded.excelRow)
          ? loaded.excelRow
          : DEFAULT_COLUMN_WIDTHS.excelRow ?? 36,
    };
  } catch {
    return DEFAULT_COLUMN_WIDTHS;
  }
}

function saveColumnWidthsForSource(
  sourceFile: string,
  widths: Partial<Record<ColumnKey, number>>
) {
  window.localStorage.setItem(
    getColumnWidthStorageKey(sourceFile),
    JSON.stringify(widths)
  );
}

function getAutoColumnWidthsForItems(
  items: LootItem[],
  sourceColumnLabels: Partial<Record<ColumnKey, string>>
) {
  const widths: Partial<Record<ColumnKey, number>> = {};

  for (const column of ITEM_COLUMNS) {
    const label = sourceColumnLabels[column.key] || column.label;
    const maxLength = items.reduce((currentMax, item) => {
      const value = String(item[column.key] ?? "");
      return Math.max(currentMax, value.length);
    }, label.length);

    const estimatedWidth = Math.round(maxLength * 7.4 + 38);
    widths[column.key] = Math.min(
      Math.max(estimatedWidth, MIN_COLUMN_WIDTH),
      MAX_COLUMN_WIDTH
    );
  }

  return widths;
}

export default App;
