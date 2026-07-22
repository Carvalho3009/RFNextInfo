const path = require("path");
const sqlite3 = require("sqlite3").verbose();

const dbPath =
  process.env.RF_LOOT_DB_PATH ||
  path.join(__dirname, "..", "rfloot.db");

const db = new sqlite3.Database(dbPath);
db.configure("busyTimeout", 30000);
db.serialize();

let transactionQueue = Promise.resolve();

const defaultEffectDictionary = [
  ["1", "Discount NPC Purchase/Sell"],
  ["2", "EXP Gain Rate"],
  ["3", "Language Translator"],
  ["4", "Item Level"],
  ["5", "EXP Gain Rate"],
  ["6", "PT Gain Rate"],
  ["7", "Mining Speed"],
  ["8", "Item Drop Rate"],
  ["9", "EXP Gain Rate"],
  ["10", "Discount NPC Purchase"],
  ["11", "Discount NPC Sell"],
  ["12", "HP Regeneration"],
  ["13", "FP Regeneration"],
  ["14", "SP Regeneration"],
  ["15", "Max HP"],
  ["16", "Max FP"],
  ["17", "Max SP"],
  ["18", "Attack"],
  ["19", "Melee Attack"],
  ["20", "Melee Skill Damage"],
  ["21", "Range Attack"],
  ["22", "Range Skill Damage"],
  ["23", "Force Attack"],
  ["24", "Defense"],
  ["25", "Vamp (Damage to HP)"],
  ["26", "Vamp (Damage to FP)"],
  ["27", "Vamp (Damage to SP)"],
  ["28", "Radius of Monster Aggro"],
  ["29", "MAU Attack (Melee Weapon)"],
  ["30", "MAU Attack (Range Weapon)"],
  ["31", "MAU Attack (Force Weapon)"],
  ["32", "MAU Attack (Defense)"],
  ["33", "Animus Attack (Force Weapon)"],
  ["34", "Animus Attack"],
  ["35", "Animus Attack"],
  ["36", "Animus Attack"],
  ["37", "Animus Attack"],
  ["38", "Attack of Melee/Range Weapon"],
  ["39", "Skill Range"],
  ["40", "Ignore Nuclear Debuff"],
  ["41", "Movement Speed"],
  ["42", "Reflects 100% of Received Damages"],
  ["43", "Accuracy (Melee Weapon)"],
  ["44", "Accuracy (Range Weapon)"],
  ["45", "Force Accuracy"],
  ["46", "Skill Accuracy"],
  ["47", "Chance of Critical Attack"],
  ["48", "Accuracy"],
  ["49", "Avoid"],
  ["50", "Restricts Actions"],
  ["51", "Chance Resurrect On Death *DO NOT USE*"],
  ["52", "Monsters Level Requirement"],
  ["53", "Party Level Requirement"],
  ["54", "Reflects of Received Damages"],
  ["55", "Using any teleport scrolls"],
  ["56", "+100% Chance Avoid"],
  ["57", "Block Chance"],
  ["58", "-100% Potion Delay"],
  ["59", "PT Melee Gain Rate"],
  ["60", "PT Range Gain Rate"],
  ["61", "PT Force Gain Rate"],
  ["62", "PT Defense Gain Rate"],
  ["63", "PT Shield Gain Rate"],
  ["64", "PT Animus Gain Rate"],
  ["65", "PT MAU Gain Rate"],
  ["71", "EXP Gain Rate"],
  ["72", "EXP Gain Rate"],
  ["73", "Item Drop Rate"],
  ["74", "Item Drop Rate"],
  ["75", "Item Drop Rate"],
  ["76", "Detect"],
  ["77", "Debuff Duration"],
  ["78", "Chance Ignore Shield Block"],
  ["79", "Ignorant Talic in Weapon"],
  ["80", "Favor Talic in Armors"],
  ["81", "Chance to Protect Items from Dropping on Death *DO NOT USE*"],
  ["82", "All PT Gain Rate"],
  ["84", "Max SP"],
  ["85", "FP Cost"],
  ["86", "Accuracy"],
  ["87", "Avoid"],
  ["88", "Max HP/FP"],
  ["89", "Attack"],
  ["90", "Defense"],
  ["91", "Skill Level"],
  ["92", "Stealth"],
  ["93", "Detect"],
  ["94", "Remove Damage Protection Skill"],
  ["95", "Movement Speed"],
  ["96", "Reveals information about enemy vulnerability"],
  ["97", "FP Regeneration"],
  ["98", "Force Attack"],
  ["99", "Max FP"],
  ["100", "Vamp (Damage to HP)"],
  ["101", "Vamp (Damage to HP)"],
  ["102", "Critical Attack Chance"],
  ["103", "Attack Range"],
  ["104", "Defense"],
  ["105", "Debuff Duration"],
  ["106", "HP Regeneration"],
  ["107", "Avoid"],
  ["108", "Attack Delay (Launcher)"],
  ["109", "Force Attack Range"],
  ["110", "Chance Receiving Critical Attack"],
  ["111", "Block Chance"],
  ["112", "Elemental Resistance"],
  ["113", "Max HP"],
  ["114", "Debuff Duration"],
  ["115", "Chance Ignore Shield Block"],
  ["116", "Range Skill Delay"],
  ["117", "Melee Skill Delay"],
  ["118", "Force Delay"],
  ["120", "Magnet Loot"],
];

const equipmentEffectDictionary = [
  ["0", "None"],
  ["1", "SP"],
  ["2", "FPConsume"],
  ["3", "Accuracy"],
  ["4", "Dodge"],
  ["5", "HPFP"],
  ["6", "Atk"],
  ["7", "Def"],
  ["8", "LvlSkill"],
  ["9", "Stealth"],
  ["10", "Detect"],
  ["11", "DmgProt"],
  ["12", "Speed"],
  ["14", "FPRecov"],
  ["15", "Fatk"],
  ["16", "FP"],
  ["17", "Vamp"],
  ["18", "fpVamp"],
  ["19", "Crit"],
  ["20", "Range"],
  ["21", "Def"],
  ["22", "DebuffTime"],
  ["23", "HPRecov"],
  ["24", "Dodge"],
  ["25", "LauDelay"],
  ["26", "ForceRange"],
  ["27", "AntiCrit"],
  ["28", "Protect"],
  ["29", "Resist"],
  ["30", "MaxHP"],
  ["31", "DebuffTime"],
  ["32", "IgShield"],
  ["34", "SkillDelay"],
  ["35", "ForDelay"],
];

const weaponEffectFormatMap = new Map([
  ["2", { label: "FP Consumption", format: "percent_0_1" }],
  ["3", { label: "Accuracy", format: "int" }],
  ["4", { label: "Dodge", format: "int" }],
  ["5", { label: "Max HP/FP", format: "percent_0_1" }],
  ["6", { label: "Attack", format: "percent_0_1" }],
  ["7", { label: "Defense", format: "percent_0_1" }],
  ["12", { label: "Movement Speed", format: "int" }],
  ["15", { label: "Force Attack", format: "percent_0_1" }],
  ["17", { label: "Vampiric", format: "percent_0_1" }],
  ["19", { label: "Critical Chance", format: "percent_0_100" }],
  ["20", { label: "Range", format: "int" }],
  ["25", { label: "Launcher Attack Delay", format: "ms" }],
  ["28", { label: "Block Chance", format: "percent_0_100" }],
  ["29", { label: "All Resistance", format: "int" }],
  ["30", { label: "Max HP", format: "percent_0_1" }],
  ["31", { label: "Debuff Duration", format: "percent_0_1" }],
  ["32", { label: "Ignore Block Chance", format: "percent_0_100" }],
  ["35", { label: "Force Skill Delay", format: "ms" }],
]);

const effectDictionaries = [
  { key: "resource", label: "Efeitos Resource" },
  { key: "equipment", label: "Efeitos Equipamentos" },
];

const equipmentShortNames = new Map([
  ["3", "Accuracy"],
  ["4", "Dodge"],
  ["5", "HP/FP"],
  ["6", "Attack"],
  ["7", "Defense"],
  ["12", "Speed"],
  ["17", "Vamp"],
  ["19", "Crit"],
  ["20", "Range"],
  ["29", "Resist"],
  ["30", "HP"],
  ["31", "Debuff"],
]);

const extraItemColumns = Array.from({ length: 160 }, (_value, index) => ({
  property: `extra${index + 1}`,
  database: `extra_${String(index + 1).padStart(2, "0")}`,
}));

function run(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function onRun(err) {
      if (err) reject(err);
      else resolve(this);
    });
  });
}

function get(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => {
      if (err) reject(err);
      else resolve(row);
    });
  });
}

function all(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      if (err) reject(err);
      else resolve(rows);
    });
  });
}

function prepare(sql) {
  return new Promise((resolve, reject) => {
    const statement = db.prepare(sql, (err) => {
      if (err) reject(err);
      else resolve(statement);
    });
  });
}

function runStatement(statement, params = []) {
  return new Promise((resolve, reject) => {
    statement.run(params, function onRun(err) {
      if (err) reject(err);
      else resolve(this);
    });
  });
}

function finalize(statement) {
  return new Promise((resolve, reject) => {
    statement.finalize((err) => {
      if (err) reject(err);
      else resolve();
    });
  });
}

async function ensureColumn(tableName, columnName, definition) {
  const columns = await all(`PRAGMA table_info(${tableName})`);
  const exists = columns.some((column) => column.name === columnName);

  if (!exists) {
    await run(`ALTER TABLE ${tableName} ADD COLUMN ${columnName} ${definition}`);
  }
}

async function initializeDatabase() {
  await run("PRAGMA busy_timeout = 30000");
  await run("PRAGMA journal_mode = WAL");
  await run("PRAGMA synchronous = NORMAL");
  await run("PRAGMA foreign_keys = ON");

  await run(`
    CREATE TABLE IF NOT EXISTS items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_file TEXT NOT NULL,
      excel_row INTEGER,
      code TEXT NOT NULL,
      name TEXT,
      model TEXT,
      icon TEXT,
      kind_clt TEXT,
      grade TEXT,
      type TEXT,
      subtype TEXT,
      level_lim TEXT,
      money TEXT,
      upgrade TEXT,
      tooltip TEXT
    )
  `);

  await ensureColumn("items", "model", "TEXT");
  await ensureColumn("items", "excel_row", "INTEGER");
  await ensureColumn("items", "icon", "TEXT");
  await ensureColumn("items", "kind_clt", "TEXT");
  await ensureColumn("items", "grade", "TEXT");
  await ensureColumn("items", "type", "TEXT");
  await ensureColumn("items", "subtype", "TEXT");
  await ensureColumn("items", "level_lim", "TEXT");
  await ensureColumn("items", "money", "TEXT");
  await ensureColumn("items", "upgrade", "TEXT");
  await ensureColumn("items", "tooltip", "TEXT");

  for (const column of extraItemColumns) {
    await ensureColumn("items", column.database, "TEXT");
  }

  await run(`
    CREATE TABLE IF NOT EXISTS item_effects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      item_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      eff_code TEXT NOT NULL,
      eff_unit TEXT,
      FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS effect_dictionary (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      dictionary_key TEXT DEFAULT 'resource',
      item_type TEXT,
      eff_code TEXT NOT NULL,
      name TEXT,
      description TEXT,
      unit_hint TEXT,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await ensureColumn("effect_dictionary", "dictionary_key", "TEXT DEFAULT 'resource'");
  await run("UPDATE effect_dictionary SET item_type = '' WHERE item_type IS NULL");
  await run("UPDATE effect_dictionary SET dictionary_key = 'resource' WHERE dictionary_key IS NULL OR dictionary_key = ''");

  await run(`
    CREATE TABLE IF NOT EXISTS source_settings (
      source_file TEXT PRIMARY KEY,
      dictionary_key TEXT NOT NULL DEFAULT 'resource',
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS source_columns (
      source_file TEXT NOT NULL,
      column_key TEXT NOT NULL,
      label TEXT,
      ordinal INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (source_file, column_key)
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS excel_file_state (
      source_file TEXT PRIMARY KEY,
      absolute_path TEXT NOT NULL,
      last_mtime_ms INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS app_settings (
      setting_key TEXT PRIMARY KEY,
      setting_value TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS boss_monsters (
      source_file TEXT,
      monster_code TEXT,
      imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (monster_code, source_file)
    )
  `);
  await migrateBossMonstersSchema();

  await run(`
    CREATE INDEX IF NOT EXISTS idx_items_source_code
    ON items (source_file, code)
  `);

  await run(`
    CREATE INDEX IF NOT EXISTS idx_items_extra_01
    ON items (extra_01)
  `);

  await run(`
    CREATE INDEX IF NOT EXISTS idx_item_effects_item_id
    ON item_effects (item_id)
  `);

  await run("DROP INDEX IF EXISTS idx_effect_dictionary_type_code");

  await run(`
    CREATE UNIQUE INDEX IF NOT EXISTS idx_effect_dictionary_dictionary_type_code
    ON effect_dictionary (dictionary_key, item_type, eff_code)
  `);

  await seedEffectDictionary();
}

async function migrateBossMonstersSchema() {
  const columns = await all("PRAGMA table_info(boss_monsters)");
  const monsterCodeColumn = columns.find((column) => column.name === "monster_code");
  const sourceFileColumn = columns.find((column) => column.name === "source_file");
  const hasCompositeKey =
    monsterCodeColumn?.pk === 1 && sourceFileColumn?.pk === 2;

  if (hasCompositeKey) {
    return;
  }

  await run(`
    CREATE TABLE IF NOT EXISTS boss_monsters_next (
      source_file TEXT,
      monster_code TEXT,
      imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (monster_code, source_file)
    )
  `);
  await run(`
    INSERT OR IGNORE INTO boss_monsters_next (
      source_file,
      monster_code,
      imported_at
    )
    SELECT
      source_file,
      monster_code,
      imported_at
    FROM boss_monsters
  `);
  await run("DROP TABLE boss_monsters");
  await run("ALTER TABLE boss_monsters_next RENAME TO boss_monsters");
}

async function seedEffectDictionary() {
  await seedDictionary("resource", defaultEffectDictionary, false);
  await seedDictionary("equipment", equipmentEffectDictionary, true);
  await seedEquipmentShortNames();
  await seedWeaponEffectFormatMap();
  await setDefaultSourceDictionary("WeaponItem.xlsx", "equipment");
}

async function seedDictionary(dictionaryKey, entries, useName) {
  const statement = await prepare(`
    INSERT OR IGNORE INTO effect_dictionary (
      dictionary_key,
      item_type,
      eff_code,
      name,
      description,
      unit_hint
    )
    VALUES (?, '', ?, ?, ?, '')
  `);

  try {
    for (const [effCode, description] of entries) {
      await runStatement(statement, [
        dictionaryKey,
        effCode,
        useName ? description : "",
        description,
      ]);
    }
  } finally {
    await finalize(statement);
  }
}

async function seedEquipmentShortNames() {
  for (const [effCode, shortName] of equipmentShortNames) {
    await run(
      `
      UPDATE effect_dictionary
      SET
        name = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE dictionary_key = 'equipment'
        AND item_type = ''
        AND eff_code = ?
        AND (name = '' OR name = description)
      `,
      [shortName, effCode]
    );
  }
}

async function seedWeaponEffectFormatMap() {
  for (const [effCode, meta] of weaponEffectFormatMap) {
    for (const dictionaryKey of ["resource", "equipment"]) {
      const existing = await get(
        `
        SELECT id
        FROM effect_dictionary
        WHERE dictionary_key = ?
          AND item_type = ''
          AND eff_code = ?
        `,
        [dictionaryKey, effCode]
      );

      if (existing) {
        await run(
          `
          UPDATE effect_dictionary
          SET
            name = ?,
            description = ?,
            unit_hint = ?,
            updated_at = CURRENT_TIMESTAMP
          WHERE id = ?
          `,
          [meta.label, meta.label, meta.format, existing.id]
        );
      } else {
        await run(
          `
          INSERT INTO effect_dictionary (
            dictionary_key,
            item_type,
            eff_code,
            name,
            description,
            unit_hint
          )
          VALUES (?, '', ?, ?, ?, ?)
          `,
          [dictionaryKey, effCode, meta.label, meta.label, meta.format]
        );
      }
    }
  }
}

async function setDefaultSourceDictionary(sourceFile, dictionaryKey) {
  const existing = await get(
    `
    SELECT source_file
    FROM source_settings
    WHERE source_file = ?
    `,
    [sourceFile]
  );

  if (existing) {
    return;
  }

  await run(
    `
    INSERT INTO source_settings (
      source_file,
      dictionary_key
    )
    VALUES (?, ?)
    `,
    [sourceFile, dictionaryKey]
  );
}

const ready = initializeDatabase();

async function clearItemsBySource(sourceFile) {
  await ready;
  await run("DELETE FROM items WHERE source_file = ?", [sourceFile]);
  await run("DELETE FROM source_columns WHERE source_file = ?", [sourceFile]);

  if (/monstercharacter/i.test(sourceFile)) {
    monsterCharacterSourceFile = null;
  }
}

async function replaceSourceColumns(sourceFile, columns) {
  await ready;
  await run("DELETE FROM source_columns WHERE source_file = ?", [sourceFile]);

  const statement = await prepare(`
    INSERT INTO source_columns (
      source_file,
      column_key,
      label,
      ordinal
    )
    VALUES (?, ?, ?, ?)
  `);

  try {
    for (const column of columns) {
      await runStatement(statement, [
        sourceFile,
        column.key,
        column.label,
        column.ordinal,
      ]);
    }
  } finally {
    await finalize(statement);
  }
}

async function listSourceColumns(sourceFile) {
  await ready;

  if (!sourceFile) {
    return [];
  }

  return await all(
    `
    SELECT
      column_key AS key,
      label,
      ordinal
    FROM source_columns
    WHERE source_file = ?
    ORDER BY ordinal
    `,
    [sourceFile]
  );
}

async function replaceExcelFileState(entries) {
  await ready;
  await run("DELETE FROM excel_file_state");

  const statement = await prepare(`
    INSERT INTO excel_file_state (
      source_file,
      absolute_path,
      last_mtime_ms
    )
    VALUES (?, ?, ?)
  `);

  try {
    for (const entry of entries) {
      await runStatement(statement, [
        entry.sourceFile,
        entry.absolutePath,
        Number(entry.lastMtimeMs) || 0,
      ]);
    }
  } finally {
    await finalize(statement);
  }
}

async function listExcelFileState() {
  await ready;
  return await all(`
    SELECT
      source_file AS sourceFile,
      absolute_path AS absolutePath,
      last_mtime_ms AS lastMtimeMs
    FROM excel_file_state
  `);
}

async function getExcelFilePath(sourceFile) {
  await ready;
  const row = await get(
    `
    SELECT absolute_path AS absolutePath
    FROM excel_file_state
    WHERE source_file = ?
    `,
    [sourceFile]
  );

  return row?.absolutePath ?? "";
}

async function getItemsForEdit(sourceFile, itemIds) {
  await ready;

  if (!sourceFile || !Array.isArray(itemIds) || itemIds.length === 0) {
    return [];
  }

  const safeIds = itemIds
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value > 0);

  if (safeIds.length === 0) {
    return [];
  }

  const placeholders = safeIds.map(() => "?").join(", ");
  return await all(
    `
    SELECT
      id,
      source_file AS sourceFile,
      excel_row AS excelRow,
      extra_01 AS extra1,
      ${itemBossMapExpression} AS bossMap
    FROM items
    LEFT JOIN (
      SELECT
        monster_code,
        GROUP_CONCAT(source_file, ', ') AS map_names
      FROM boss_monsters
      GROUP BY monster_code
    ) AS boss_maps
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND boss_maps.monster_code = items.extra_01
    WHERE source_file = ?
      AND id IN (${placeholders})
    `,
    [sourceFile, ...safeIds]
  );
}

async function setAppSetting(settingKey, settingValue) {
  await ready;
  await run(
    `
    INSERT INTO app_settings (
      setting_key,
      setting_value
    )
    VALUES (?, ?)
    ON CONFLICT(setting_key) DO UPDATE SET
      setting_value = excluded.setting_value
    `,
    [settingKey, settingValue]
  );
}

async function getAppSetting(settingKey) {
  await ready;
  const row = await get(
    `
    SELECT setting_value AS settingValue
    FROM app_settings
    WHERE setting_key = ?
    `,
    [settingKey]
  );

  return row?.settingValue ?? "";
}

async function insertItem(item) {
  await ready;

  const result = await run(
    `
    INSERT INTO items (
      source_file,
      excel_row,
      code,
      name,
      model,
      icon,
      kind_clt,
      grade,
      type,
      subtype,
      level_lim,
      money,
      upgrade,
      tooltip
      ${extraItemColumns.map((column) => `, ${column.database}`).join("")}
    )
    VALUES (${Array.from({ length: 14 + extraItemColumns.length }, () => "?").join(", ")})
    `,
    [
      item.sourceFile,
      item.excelRow,
      item.code,
      item.name,
      item.model,
      item.icon,
      item.kindClt,
      item.grade,
      item.type,
      item.subtype,
      item.levelLim,
      item.money,
      item.upgrade,
      item.tooltip,
      ...extraItemColumns.map((column) => item[column.property] ?? ""),
    ]
  );

  return result.lastID;
}

async function insertItemEffect(itemId, effect) {
  await ready;

  await run(
    `
    INSERT INTO item_effects (
      item_id,
      slot,
      eff_code,
      eff_unit
    )
    VALUES (?, ?, ?, ?)
    `,
    [
      itemId,
      effect.slot,
      effect.effCode,
      effect.effUnit,
    ]
  );
}

async function replaceItemsFromSource(sourceFile, items, options = {}) {
  const { onProgress } = options;

  return await transaction(async () => {
    if (/monstercharacter/i.test(sourceFile)) {
      monsterCharacterSourceFile = null;
    }

    await run("DELETE FROM items WHERE source_file = ?", [sourceFile]);
    await run("DELETE FROM source_columns WHERE source_file = ?", [sourceFile]);

    const itemStatement = await prepare(`
      INSERT INTO items (
        source_file,
        excel_row,
        code,
        name,
        model,
        icon,
        kind_clt,
        grade,
        type,
        subtype,
        level_lim,
        money,
        upgrade,
        tooltip
        ${extraItemColumns.map((column) => `, ${column.database}`).join("")}
      )
      VALUES (${Array.from({ length: 14 + extraItemColumns.length }, () => "?").join(", ")})
    `);

    const effectStatement = await prepare(`
      INSERT INTO item_effects (
        item_id,
        slot,
        eff_code,
        eff_unit
      )
      VALUES (?, ?, ?, ?)
    `);

    let inserted = 0;
    let effectsInserted = 0;

    try {
      for (const item of items) {
        const result = await runStatement(itemStatement, [
          sourceFile,
          item.excelRow,
          item.code,
          item.name,
          item.model,
          item.icon,
          item.kindClt,
          item.grade,
          item.type,
          item.subtype,
          item.levelLim,
          item.money,
          item.upgrade,
          item.tooltip,
          ...extraItemColumns.map((column) => item[column.property] ?? ""),
        ]);

        for (const effect of item.effects) {
          await runStatement(effectStatement, [
            result.lastID,
            effect.slot,
            effect.effCode,
            effect.effUnit,
          ]);

          effectsInserted++;
        }

        inserted++;

        if (onProgress && (inserted === 1 || inserted % 250 === 0 || inserted === items.length)) {
          onProgress({
            inserted,
            total: items.length,
            effectsInserted,
          });
        }
      }
    } finally {
      await finalize(itemStatement);
      await finalize(effectStatement);
    }

    return {
      inserted,
      effectsInserted,
    };
  });
}

function transaction(work) {
  const nextTransaction = transactionQueue.then(
    () => runTransaction(work),
    () => runTransaction(work)
  );

  transactionQueue = nextTransaction.catch(() => {});

  return nextTransaction;
}

async function runTransaction(work) {
  await ready;

  let began = false;

  try {
    await run("BEGIN IMMEDIATE TRANSACTION");
    began = true;

    const result = await work();
    await run("COMMIT");
    return result;
  } catch (error) {
    if (began) {
      await run("ROLLBACK").catch(() => {});
    }

    throw error;
  }
}

async function countItems() {
  await ready;
  const row = await get(`
    SELECT COUNT(*) AS total
    FROM items
  `);

  return row.total;
}

async function countItemEffects() {
  await ready;
  const row = await get(`
    SELECT COUNT(*) AS total
    FROM item_effects
  `);

  return row.total;
}

async function listSourceFiles() {
  await ready;
  return await all(`
    SELECT
      items.source_file AS sourceFile,
      COUNT(*) AS itemCount,
      COALESCE(source_settings.dictionary_key, 'resource') AS dictionaryKey
    FROM items
    LEFT JOIN source_settings
      ON source_settings.source_file = items.source_file
    GROUP BY items.source_file
    ORDER BY items.source_file COLLATE NOCASE
  `);
}

const itemNameExpression = `CASE
  WHEN LOWER(items.source_file) LIKE '%itemlooting%' THEN COALESCE(NULLIF(monsters.name, ''), items.name)
  ELSE items.name
END`;
const itemBossExpression = `CASE
  WHEN boss_monsters.monster_code IS NOT NULL THEN 'Boss'
  ELSE ''
END`;
const itemBossMapExpression = "COALESCE(boss_maps.map_names, '')";
let monsterCharacterSourceFile = null;

const itemFilterColumns = new Map([
  ["sourceFile", "items.source_file"],
  ["code", "items.code"],
  ["name", itemNameExpression],
  ["boss", itemBossExpression],
  ["bossMap", itemBossMapExpression],
  ["model", "items.model"],
  ["icon", "items.icon"],
  ["kindClt", "items.kind_clt"],
  ["grade", "items.grade"],
  ["type", "items.type"],
  ["subtype", "items.subtype"],
  ["levelLim", "items.level_lim"],
  ["money", "items.money"],
  ["upgrade", "items.upgrade"],
  ["tooltip", "items.tooltip"],
  ...extraItemColumns.map((column, index) => [
    `extra${index + 1}`,
    `items.${column.database}`,
  ]),
]);

function buildItemWhere({
  sourceFile = "",
  search = "",
  filters = [],
  columnFilters = {},
  excludeColumnFilter = "",
} = {}) {
  const where = [];
  const params = [];

  if (sourceFile) {
    where.push("items.source_file = ?");
    params.push(sourceFile);
  }

  if (search) {
    const searchableColumns = [
      "items.code",
      itemNameExpression,
      itemBossExpression,
      itemBossMapExpression,
      "items.type",
      "items.subtype",
      ...extraItemColumns.map((column) => `items.${column.database}`),
    ];
    where.push(
      `(${searchableColumns.map((column) => `${column} LIKE ?`).join(" OR ")})`
    );
    const pattern = `%${search}%`;
    params.push(...searchableColumns.map(() => pattern));
  }

  for (const filter of filters) {
    const column = itemFilterColumns.get(filter.field);
    const value = String(filter.value ?? "").trim();

    if (!column || !value) {
      continue;
    }

    switch (filter.operator) {
      case "equals":
        where.push(`${column} = ? COLLATE NOCASE`);
        params.push(value);
        break;
      case "startsWith":
        where.push(`${column} LIKE ? COLLATE NOCASE`);
        params.push(`${value}%`);
        break;
      case "endsWith":
        where.push(`${column} LIKE ? COLLATE NOCASE`);
        params.push(`%${value}`);
        break;
      case "notContains":
        where.push(`${column} NOT LIKE ? COLLATE NOCASE`);
        params.push(`%${value}%`);
        break;
      case "contains":
      default:
        where.push(`${column} LIKE ? COLLATE NOCASE`);
        params.push(`%${value}%`);
        break;
    }
  }

  for (const [field, values] of Object.entries(columnFilters)) {
    const column = itemFilterColumns.get(field);
    const safeValues = Array.isArray(values)
      ? values.map((value) => String(value)).filter((value) => value !== "")
      : [];

    if (!column || field === excludeColumnFilter || safeValues.length === 0) {
      continue;
    }

    const placeholders = safeValues.map(() => "?").join(", ");
    where.push(`${column} IN (${placeholders})`);
    params.push(...safeValues);
  }

  return {
    whereSql: where.length > 0 ? `WHERE ${where.join(" AND ")}` : "",
    params,
  };
}

function formatItemEffect(effect) {
  const label =
    effect.effectName ||
    effect.effectDescription ||
    (effect.effCode ? `Eff ${effect.effCode}` : "");
  const value = formatEffectUnit(effect.effUnit, effect.unitHint);

  if (!label) {
    return value;
  }

  if (!value) {
    return label;
  }

  return `${value} ${label}`;
}

function formatEffectUnit(value, unitHint = "") {
  const raw = String(value ?? "").trim();

  if (!raw) {
    return "";
  }

  const normalized = raw.replace(",", ".");
  const parsed = Number(normalized);

  if (!Number.isFinite(parsed)) {
    return raw;
  }

  const format = String(unitHint || "").trim().toLowerCase();

  if (format === "percent_0_1") {
    return `${formatDecimal(parsed * 100, 1)}%`;
  }

  if (format === "percent_0_100") {
    const percentValue = Math.abs(parsed) <= 1 && normalized.includes(".")
      ? parsed * 100
      : parsed;
    return `${formatDecimal(percentValue, 2)}%`;
  }

  if (format === "ms") {
    return `${formatDecimal(parsed, 0)}ms`;
  }

  if (format === "float") {
    return formatDecimal(parsed, 3);
  }

  if (format === "int") {
    return Number.isInteger(parsed) ? String(parsed) : formatDecimal(parsed, 3);
  }

  if (normalized.includes(".")) {
    return `${formatDecimal(parsed * 100, 1)}%`;
  }

  return String(Math.trunc(parsed));
}

function formatDecimal(value, maximumFractionDigits) {
  return Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  });
}

async function listItems({
  sourceFile = "",
  search = "",
  filters = [],
  columnFilters = {},
  sortField = "",
  sortDirection = "asc",
  limit = 1000,
  offset = 0,
} = {}) {
  await ready;
  const monsterSourceFile = await getMonsterCharacterSourceFile();

  const { whereSql, params } = buildItemWhere({
    sourceFile,
    search,
    filters,
    columnFilters,
  });
  const safeLimit = Math.min(Math.max(Number(limit) || 1000, 1), 1000);
  const safeOffset = Math.max(Number(offset) || 0, 0);

  const totalRow = await get(
    `
    SELECT COUNT(*) AS total
    FROM items
    LEFT JOIN source_settings
      ON source_settings.source_file = items.source_file
    LEFT JOIN items AS monsters
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND monsters.source_file = ?
      AND monsters.code = items.extra_01
    LEFT JOIN (
      SELECT
        monster_code,
        GROUP_CONCAT(source_file, ', ') AS map_names
      FROM boss_monsters
      GROUP BY monster_code
    ) AS boss_maps
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND boss_maps.monster_code = items.extra_01
    LEFT JOIN boss_monsters
      ON boss_monsters.monster_code = boss_maps.monster_code
    ${whereSql}
    `,
    [monsterSourceFile, ...params]
  );

  const sourceFileText = String(sourceFile || "");
  const isCsvSource = /\.csv$/i.test(sourceFileText);
  const isBoxItemOutSource = /boxitemout/i.test(sourceFileText) && !isCsvSource;
  const isCombineSource = /(^|[\\/])(combinetable2?|linkedcombines?)\.xlsx$/i.test(sourceFileText);
  const sortMap = {
    excelRow: "items.excel_row",
    code: "items.code",
    name: itemNameExpression,
    grade: "items.grade",
    type: "items.type",
    subtype: "items.subtype",
    levelLim: "items.level_lim",
    money: "items.money",
    icon: "items.icon",
    ...Object.fromEntries(
      extraItemColumns.map((column, index) => [`extra${index + 1}`, `items.${column.database}`])
    ),
  };
  const safeSortField = String(sortField || "");
  const safeSortDirection = String(sortDirection || "").toLowerCase() === "desc" ? "DESC" : "ASC";
  const csvCustomOrder =
    isCsvSource && sortMap[safeSortField]
      ? `ORDER BY ${sortMap[safeSortField]} COLLATE NOCASE ${safeSortDirection}, items.excel_row ASC, items.id ASC`
      : "";
  const orderBySql = csvCustomOrder
    ? csvCustomOrder
    : sourceFile || isBoxItemOutSource || isCsvSource || isCombineSource
    ? "ORDER BY items.excel_row ASC, items.id ASC"
    : `ORDER BY
        CASE WHEN LOWER(items.source_file) LIKE '%boxitemout%' THEN 0 ELSE 1 END,
        CASE WHEN LOWER(items.source_file) LIKE '%boxitemout%' THEN items.excel_row END ASC,
        items.source_file COLLATE NOCASE,
        items.code COLLATE NOCASE`;

  const items = await all(
    `
    SELECT
      items.id,
      items.source_file AS sourceFile,
      items.excel_row AS excelRow,
      items.code,
      ${itemNameExpression} AS name,
      ${itemBossExpression} AS boss,
      ${itemBossMapExpression} AS bossMap,
      items.model,
      items.icon,
      items.kind_clt AS kindClt,
      items.grade,
      items.type,
      items.subtype,
      items.level_lim AS levelLim,
      items.money,
      items.upgrade,
      items.tooltip,
      ${extraItemColumns
        .map((column, index) => `items.${column.database} AS extra${index + 1}`)
        .join(",\n      ")},
      COALESCE(source_settings.dictionary_key, 'resource') AS dictionaryKey
    FROM items
    LEFT JOIN source_settings
      ON source_settings.source_file = items.source_file
    LEFT JOIN items AS monsters
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND monsters.source_file = ?
      AND monsters.code = items.extra_01
    LEFT JOIN (
      SELECT
        monster_code,
        GROUP_CONCAT(source_file, ', ') AS map_names
      FROM boss_monsters
      GROUP BY monster_code
    ) AS boss_maps
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND boss_maps.monster_code = items.extra_01
    LEFT JOIN boss_monsters
      ON boss_monsters.monster_code = boss_maps.monster_code
    ${whereSql}
    ${orderBySql}
    LIMIT ? OFFSET ?
    `,
    [monsterSourceFile, ...params, safeLimit, safeOffset]
  );

  if (items.length === 0) {
    return {
      items: [],
      total: totalRow.total,
    };
  }

  const placeholders = items.map(() => "?").join(", ");
  const effects = await all(
    `
    SELECT
      item_effects.item_id AS itemId,
      item_effects.slot,
      item_effects.eff_code AS effCode,
      item_effects.eff_unit AS effUnit,
      COALESCE(
        NULLIF(type_dictionary.name, ''),
        NULLIF(global_dictionary.name, '')
      ) AS effectName,
      COALESCE(
        NULLIF(type_dictionary.description, ''),
        NULLIF(global_dictionary.description, '')
      ) AS effectDescription,
      COALESCE(
        NULLIF(type_dictionary.unit_hint, ''),
        NULLIF(global_dictionary.unit_hint, '')
      ) AS unitHint
    FROM item_effects
    INNER JOIN items ON items.id = item_effects.item_id
    LEFT JOIN source_settings
      ON source_settings.source_file = items.source_file
    LEFT JOIN effect_dictionary AS type_dictionary
      ON type_dictionary.eff_code = item_effects.eff_code
      AND type_dictionary.item_type = items.type
      AND type_dictionary.dictionary_key = COALESCE(source_settings.dictionary_key, 'resource')
    LEFT JOIN effect_dictionary AS global_dictionary
      ON global_dictionary.eff_code = item_effects.eff_code
      AND global_dictionary.item_type = ''
      AND global_dictionary.dictionary_key = COALESCE(source_settings.dictionary_key, 'resource')
    WHERE item_effects.item_id IN (${placeholders})
      AND TRIM(item_effects.eff_code) <> ''
      AND TRIM(item_effects.eff_code) <> '0'
    ORDER BY item_effects.item_id, item_effects.slot
    `,
    items.map((item) => item.id)
  );

  const effectsByItem = new Map();

  for (const effect of effects) {
    const currentEffects = effectsByItem.get(effect.itemId) ?? [];
    currentEffects.push({
      slot: effect.slot,
      effCode: effect.effCode,
      effUnit: effect.effUnit,
      name: effect.effectName || "",
      description: effect.effectDescription || "",
      unitHint: effect.unitHint || "",
      display: formatItemEffect(effect),
    });
    effectsByItem.set(effect.itemId, currentEffects);
  }

  const itemsWithEffects = items.map((item) => {
    const itemEffects = effectsByItem.get(item.id) ?? [];

    return {
      ...item,
      effect1: itemEffects.find((effect) => effect.slot === 1)?.display ?? "",
      effect2: itemEffects.find((effect) => effect.slot === 2)?.display ?? "",
      effect3: itemEffects.find((effect) => effect.slot === 3)?.display ?? "",
      effect4: itemEffects.find((effect) => effect.slot === 4)?.display ?? "",
      effects: itemEffects,
    };
  });

  return {
    items: itemsWithEffects,
    total: totalRow.total,
  };
}

async function listItemColumnValues({
  sourceFile = "",
  search = "",
  filters = [],
  columnFilters = {},
  field = "",
  valueSearch = "",
} = {}) {
  await ready;
  const monsterSourceFile = await getMonsterCharacterSourceFile();

  const column = itemFilterColumns.get(field);

  if (!column) {
    return [];
  }

  const { whereSql, params } = buildItemWhere({
    sourceFile,
    search,
    filters,
    columnFilters,
    excludeColumnFilter: field,
  });
  const valueWhere = [];
  const valueParams = [...params];

  if (valueSearch) {
    valueWhere.push(`${column} LIKE ? COLLATE NOCASE`);
    valueParams.push(`%${valueSearch}%`);
  }

  const combinedWhere = [whereSql.replace(/^WHERE\s*/, ""), ...valueWhere]
    .filter(Boolean)
    .join(" AND ");
  const finalWhereSql = combinedWhere ? `WHERE ${combinedWhere}` : "";

  if (field === "bossMap") {
    const mapRows = await all(
      `
      SELECT DISTINCT
        boss_monsters_filter.source_file AS value
      FROM items
      LEFT JOIN source_settings
        ON source_settings.source_file = items.source_file
      LEFT JOIN items AS monsters
        ON LOWER(items.source_file) LIKE '%itemlooting%'
        AND monsters.source_file = ?
        AND monsters.code = items.extra_01
      LEFT JOIN (
        SELECT
          monster_code,
          GROUP_CONCAT(source_file, ', ') AS map_names
        FROM boss_monsters
        GROUP BY monster_code
      ) AS boss_maps
        ON LOWER(items.source_file) LIKE '%itemlooting%'
        AND boss_maps.monster_code = items.extra_01
      LEFT JOIN boss_monsters
        ON boss_monsters.monster_code = boss_maps.monster_code
      LEFT JOIN boss_monsters AS boss_monsters_filter
        ON LOWER(items.source_file) LIKE '%itemlooting%'
        AND boss_monsters_filter.monster_code = items.extra_01
      ${finalWhereSql}
      ORDER BY value COLLATE NOCASE
      LIMIT 1000
      `,
      [monsterSourceFile, ...valueParams]
    );

    return mapRows
      .map((row) => String(row.value ?? "").trim())
      .filter((value) => value !== "")
      .sort(compareFilterValues);
  }

  const rows = await all(
    `
    SELECT DISTINCT
      ${column} AS value
    FROM items
    LEFT JOIN source_settings
      ON source_settings.source_file = items.source_file
    LEFT JOIN items AS monsters
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND monsters.source_file = ?
      AND monsters.code = items.extra_01
    LEFT JOIN (
      SELECT
        monster_code,
        GROUP_CONCAT(source_file, ', ') AS map_names
      FROM boss_monsters
      GROUP BY monster_code
    ) AS boss_maps
      ON LOWER(items.source_file) LIKE '%itemlooting%'
      AND boss_maps.monster_code = items.extra_01
    LEFT JOIN boss_monsters
      ON boss_monsters.monster_code = boss_maps.monster_code
    ${finalWhereSql}
    ORDER BY value COLLATE NOCASE
    LIMIT 1000
    `,
    [monsterSourceFile, ...valueParams]
  );

  return rows
    .map((row) => String(row.value ?? ""))
    .sort(compareFilterValues);
}

async function getMonsterCharacterSourceFile() {
  if (monsterCharacterSourceFile !== null) {
    return monsterCharacterSourceFile;
  }

  const row = await get(`
    SELECT source_file AS sourceFile
    FROM items
    WHERE LOWER(source_file) LIKE '%monstercharacter%'
    GROUP BY source_file
    ORDER BY source_file COLLATE NOCASE
    LIMIT 1
  `);

  monsterCharacterSourceFile = row?.sourceFile ?? "";
  return monsterCharacterSourceFile;
}

function compareFilterValues(firstValue, secondValue) {
  const firstNumber = Number(firstValue);
  const secondNumber = Number(secondValue);
  const firstIsNumber = firstValue.trim() !== "" && Number.isFinite(firstNumber);
  const secondIsNumber = secondValue.trim() !== "" && Number.isFinite(secondNumber);

  if (firstIsNumber && secondIsNumber) {
    return firstNumber - secondNumber;
  }

  if (firstIsNumber) {
    return -1;
  }

  if (secondIsNumber) {
    return 1;
  }

  return firstValue.localeCompare(secondValue, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

async function listEffectDictionaries() {
  await ready;
  return effectDictionaries;
}

async function setSourceDictionary(sourceFile, dictionaryKey) {
  await ready;

  if (!sourceFile) {
    throw new Error("Arquivo de origem e obrigatorio.");
  }

  if (!effectDictionaries.some((dictionary) => dictionary.key === dictionaryKey)) {
    throw new Error("Dicionario invalido.");
  }

  await run(
    `
    INSERT INTO source_settings (
      source_file,
      dictionary_key,
      updated_at
    )
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(source_file) DO UPDATE SET
      dictionary_key = excluded.dictionary_key,
      updated_at = CURRENT_TIMESTAMP
    `,
    [sourceFile, dictionaryKey]
  );
}

async function listEffectDictionary({ search = "", dictionaryKey = "resource" } = {}) {
  await ready;

  const where = ["dictionary_key = ?"];
  const params = [dictionaryKey];

  if (search) {
    where.push(`
      (
        eff_code LIKE ?
        OR item_type LIKE ?
        OR name LIKE ?
        OR description LIKE ?
        OR unit_hint LIKE ?
      )
    `);
    const pattern = `%${search}%`;
    params.push(pattern, pattern, pattern, pattern, pattern);
  }

  const whereSql = `WHERE ${where.join(" AND ")}`;

  return await all(
    `
    SELECT
      id,
      dictionary_key AS dictionaryKey,
      item_type AS itemType,
      eff_code AS effCode,
      name,
      description,
      unit_hint AS unitHint,
      updated_at AS updatedAt
    FROM effect_dictionary
    ${whereSql}
    ORDER BY CAST(eff_code AS INTEGER), item_type COLLATE NOCASE
    LIMIT 500
    `,
    params
  );
}

async function saveEffectDictionaryEntry(entry) {
  await ready;

  const dictionaryKey = String(entry.dictionaryKey ?? "resource").trim();
  const itemType = String(entry.itemType ?? "").trim();
  const effCode = String(entry.effCode ?? "").trim();
  const name = String(entry.name ?? "").trim();
  const description = String(entry.description ?? "").trim();
  const unitHint = String(entry.unitHint ?? "").trim();

  if (!effCode) {
    throw new Error("Eff e obrigatorio.");
  }

  if (!effectDictionaries.some((dictionary) => dictionary.key === dictionaryKey)) {
    throw new Error("Dicionario invalido.");
  }

  if (entry.id) {
    await run(
      `
      UPDATE effect_dictionary
      SET
        dictionary_key = ?,
        item_type = ?,
        eff_code = ?,
        name = ?,
        description = ?,
        unit_hint = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
      `,
      [dictionaryKey, itemType, effCode, name, description, unitHint, entry.id]
    );

    return entry.id;
  }

  const existing = await get(
    `
    SELECT id
    FROM effect_dictionary
    WHERE dictionary_key = ? AND item_type = ? AND eff_code = ?
    `,
    [dictionaryKey, itemType, effCode]
  );

  if (existing) {
    await run(
      `
      UPDATE effect_dictionary
      SET
        name = ?,
        description = ?,
        unit_hint = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
      `,
      [name, description, unitHint, existing.id]
    );

    return existing.id;
  }

  const result = await run(
    `
    INSERT INTO effect_dictionary (
      dictionary_key,
      item_type,
      eff_code,
      name,
      description,
      unit_hint
    )
    VALUES (?, ?, ?, ?, ?, ?)
    `,
    [dictionaryKey, itemType, effCode, name, description, unitHint]
  );

  return result.lastID;
}

async function deleteEffectDictionaryEntry(id) {
  await ready;
  await run("DELETE FROM effect_dictionary WHERE id = ?", [id]);
}

async function replaceBossMonsters(entries) {
  return await transaction(async () => {
    await run("DELETE FROM boss_monsters");

    const statement = await prepare(`
      INSERT OR IGNORE INTO boss_monsters (
        monster_code,
        source_file
      )
      VALUES (?, ?)
    `);

    let inserted = 0;

    try {
      for (const entry of entries) {
        const code = String(entry.code ?? "").trim();

        if (!code) {
          continue;
        }

        const result = await runStatement(statement, [
          code,
          entry.sourceFile ?? "",
        ]);

        if (result.changes > 0) {
          inserted++;
        }
      }
    } finally {
      await finalize(statement);
    }

    return {
      inserted,
    };
  });
}

async function countBossMonsters() {
  await ready;
  const row = await get(`
    SELECT COUNT(*) AS total
    FROM boss_monsters
  `);

  return row.total;
}

function chunkItems(items, size) {
  const chunks = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

function buildSlotValue(slot) {
  return `${slot}${"F".repeat(Math.max(0, 8 - String(slot).length))}`;
}

function buildWeaponUpgradeValue(slot, upgradeCount) {
  const safeSlot = Math.max(0, Math.min(7, Number(slot) || 0));
  const safeUpgrade = Math.max(0, Math.min(safeSlot, Number(upgradeCount) || 0));
  return `${safeSlot}${"F".repeat(7 - safeUpgrade)}${"0".repeat(safeUpgrade)}`;
}

async function generateGrade1WeaponSocketCombines() {
  await ready;

  const weaponSource = "06_WeaponItem\\WeaponItem.xlsx";
  const combineSource = "CombineTable2.xlsx";
  const linkedSource = "LinkedCombines.xlsx";
  const inputPrefix = "LLwgb";
  const resultPrefix = "LRwgb";
  const codePrefix = "cocsa";

  const weapons = await all(
    `
    SELECT code, name, model, icon, level_lim AS levelLim
    FROM items
    WHERE source_file = ?
      AND grade = '1'
      AND (name LIKE '%+%' OR name LIKE '%++%')
      AND name NOT LIKE '%Darkray%'
    ORDER BY type COLLATE NOCASE, subtype COLLATE NOCASE, level_lim + 0, model COLLATE NOCASE, code COLLATE NOCASE
    `,
    [weaponSource]
  );

  if (weapons.length === 0) {
    throw new Error("Nenhuma arma grade 1 com + ou ++ encontrada.");
  }

  const groups = chunkItems(weapons, 79).map((items, index) => {
    const suffix = String(index + 1).padStart(2, "0");
    return {
      inputCode: `${inputPrefix}${suffix}`,
      resultCode: `${resultPrefix}${suffix}`,
      items,
    };
  });

  return await transaction(async () => {
    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND (code LIKE ? OR code LIKE ? OR code LIKE ? OR code LIKE ?)
      `,
      [linkedSource, `${inputPrefix}%`, `${resultPrefix}%`, "LLwg1%", "LRwg1%"]
    );

    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND (extra_05 LIKE 'RF Editor: Weapon Grade 1 Socket%' OR extra_05 LIKE 'Weapon Grade 1 Socket%')
      `,
      [combineSource]
    );

    const linkedMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [linkedSource]
    );
    const combineMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [combineSource]
    );
    const combineCodeMax = await get(
      `
      SELECT COALESCE(MAX(CAST(REPLACE(code, ?, '') AS INTEGER)), 0) AS maxCode
      FROM items
      WHERE source_file = ?
        AND code LIKE ?
      `,
      [codePrefix, combineSource, `${codePrefix}%`]
    );

    const insertColumns = [
      "code",
      "name",
      "source_file",
      "excel_row",
      ...Array.from({ length: 160 }, (_, index) => `extra_${String(index + 1).padStart(2, "0")}`),
    ];
    const placeholders = insertColumns.map(() => "?").join(", ");
    const statement = await prepare(`
      INSERT INTO items (${insertColumns.join(", ")})
      VALUES (${placeholders})
    `);

    let linkedRow = Number(linkedMax.maxRow || 1) + 1;
    let combineRow = Number(combineMax.maxRow || 1) + 1;
    let combineCode = Number(combineCodeMax.maxCode || 0) + 1;
    let linkedInserted = 0;
    let combinesInserted = 0;

    try {
      for (const group of groups) {
        for (const groupCode of [group.inputCode, group.resultCode]) {
          const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
          values.code = groupCode;
          values.name = group.items[0]?.code ?? "";
          values.source_file = linkedSource;
          values.excel_row = linkedRow++;

          group.items.forEach((item, index) => {
            values[`extra_${String(index + 2).padStart(2, "0")}`] = item.code;
          });

          await runStatement(statement, insertColumns.map((column) => values[column]));
          linkedInserted++;
        }
      }

      for (let slot = 0; slot < 7; slot++) {
        for (let upgrade = 0; upgrade <= slot; upgrade++) {
          for (const group of groups) {
            const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
            values.code = `${codePrefix}${combineCode++}`;
            values.name = "100000";
            values.source_file = combineSource;
            values.excel_row = combineRow++;
            values.extra_02 = "100000";
            values.extra_03 = "11111";
            values.extra_04 = "1";
            values.extra_05 = `Weapon Grade 1 Socket ${slot} -> ${slot + 1} +${upgrade}`;
            values.extra_06 = "-1";
            values.extra_07 = "iycsa55";
            values.extra_08 = "FFFFFFFF";
            values.extra_09 = "1";
            values.extra_10 = group.inputCode;
            values.extra_11 = buildWeaponUpgradeValue(slot, upgrade);
            values.extra_12 = "1";
            values.extra_22 = "0";
            values.extra_23 = "1";
            values.extra_24 = group.resultCode;
            values.extra_25 = buildWeaponUpgradeValue(slot + 1, upgrade);
            values.extra_26 = "1";
            values.extra_27 = "3605";
            values.extra_28 = "10000";
            values.extra_29 = "1";

            await runStatement(statement, insertColumns.map((column) => values[column]));
            combinesInserted++;
          }
        }
      }
    } finally {
      await finalize(statement);
    }

    return {
      weapons: weapons.length,
      groups: groups.length,
      linkedInserted,
      combinesInserted,
    };
  });
}

async function generateLeonWeaponSocketCombines() {
  await ready;

  const weaponSource = "06_WeaponItem\\WeaponItem.xlsx";
  const combineSource = "CombineTable2.xlsx";
  const linkedSource = "LinkedCombines.xlsx";
  const inputPrefix = "LLwle";
  const resultPrefix = "LRwle";
  const codePrefix = "cocsa";

  const weapons = await all(
    `
    SELECT code, name, model, icon, level_lim AS levelLim, grade
    FROM items
    WHERE source_file = ?
      AND grade IN ('3', '8')
      AND (name LIKE '%+%' OR name LIKE '%++%')
      AND name LIKE '%Leon%'
      AND name NOT LIKE '%Darkray%'
    ORDER BY grade + 0, type COLLATE NOCASE, subtype COLLATE NOCASE, level_lim + 0, model COLLATE NOCASE, code COLLATE NOCASE
    `,
    [weaponSource]
  );

  if (weapons.length === 0) {
    throw new Error("Nenhuma arma Leon grade 3/8 com + ou ++ encontrada.");
  }

  const groups = chunkItems(weapons, 79).map((items, index) => {
    const suffix = String(index + 1).padStart(2, "0");
    return {
      inputCode: `${inputPrefix}${suffix}`,
      resultCode: `${resultPrefix}${suffix}`,
      items,
    };
  });

  return await transaction(async () => {
    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND (code LIKE ? OR code LIKE ?)
      `,
      [linkedSource, `${inputPrefix}%`, `${resultPrefix}%`]
    );

    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND extra_05 LIKE 'Weapon Leon Socket%'
      `,
      [combineSource]
    );

    const linkedMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [linkedSource]
    );
    const combineMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [combineSource]
    );
    const combineCodeMax = await get(
      `
      SELECT COALESCE(MAX(CAST(REPLACE(code, ?, '') AS INTEGER)), 0) AS maxCode
      FROM items
      WHERE source_file = ?
        AND code LIKE ?
      `,
      [codePrefix, combineSource, `${codePrefix}%`]
    );

    const insertColumns = [
      "code",
      "name",
      "source_file",
      "excel_row",
      ...Array.from({ length: 160 }, (_, index) => `extra_${String(index + 1).padStart(2, "0")}`),
    ];
    const placeholders = insertColumns.map(() => "?").join(", ");
    const statement = await prepare(`
      INSERT INTO items (${insertColumns.join(", ")})
      VALUES (${placeholders})
    `);

    let linkedRow = Number(linkedMax.maxRow || 1) + 1;
    let combineRow = Number(combineMax.maxRow || 1) + 1;
    let combineCode = Number(combineCodeMax.maxCode || 0) + 1;
    let linkedInserted = 0;
    let combinesInserted = 0;

    try {
      for (const group of groups) {
        for (const groupCode of [group.inputCode, group.resultCode]) {
          const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
          values.code = groupCode;
          values.name = group.items[0]?.code ?? "";
          values.source_file = linkedSource;
          values.excel_row = linkedRow++;

          group.items.forEach((item, index) => {
            values[`extra_${String(index + 2).padStart(2, "0")}`] = item.code;
          });

          await runStatement(statement, insertColumns.map((column) => values[column]));
          linkedInserted++;
        }
      }

      for (let slot = 0; slot < 7; slot++) {
        for (let upgrade = 0; upgrade <= slot; upgrade++) {
          for (const group of groups) {
            const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
            values.code = `${codePrefix}${combineCode++}`;
            values.name = "100000";
            values.source_file = combineSource;
            values.excel_row = combineRow++;
            values.extra_02 = "100000";
            values.extra_03 = "11111";
            values.extra_04 = "1";
            values.extra_05 = `Weapon Leon Socket ${slot} -> ${slot + 1} +${upgrade}`;
            values.extra_06 = "-1";
            values.extra_07 = "iywsu02";
            values.extra_08 = "FFFFFFFF";
            values.extra_09 = "1";
            values.extra_10 = group.inputCode;
            values.extra_11 = buildWeaponUpgradeValue(slot, upgrade);
            values.extra_12 = "1";
            values.extra_22 = "0";
            values.extra_23 = "1";
            values.extra_24 = group.resultCode;
            values.extra_25 = buildWeaponUpgradeValue(slot + 1, upgrade);
            values.extra_26 = "1";
            values.extra_27 = "3605";
            values.extra_28 = "10000";
            values.extra_29 = "1";

            await runStatement(statement, insertColumns.map((column) => values[column]));
            combinesInserted++;
          }
        }
      }
    } finally {
      await finalize(statement);
    }

    return {
      weapons: weapons.length,
      groups: groups.length,
      linkedInserted,
      combinesInserted,
    };
  });
}

async function generateCrimsonWeaponSocketCombines() {
  await ready;

  const weaponSource = "06_WeaponItem\\WeaponItem.xlsx";
  const combineSource = "CombineTable2.xlsx";
  const linkedSource = "LinkedCombines.xlsx";
  const inputPrefix = "LLwcr";
  const resultPrefix = "LRwcr";
  const codePrefix = "cocsa";

  const weapons = await all(
    `
    SELECT code, name, model, icon, level_lim AS levelLim, grade
    FROM items
    WHERE source_file = ?
      AND grade = '3'
      AND (name LIKE '%+%' OR name LIKE '%++%')
      AND (name LIKE '%Crimson%' OR name LIKE '%Crimsom%')
      AND name NOT LIKE '%Darkray%'
    ORDER BY type COLLATE NOCASE, subtype COLLATE NOCASE, level_lim + 0, model COLLATE NOCASE, code COLLATE NOCASE
    `,
    [weaponSource]
  );

  if (weapons.length === 0) {
    throw new Error("Nenhuma arma Crimson grade 3 com + ou ++ encontrada.");
  }

  const groups = chunkItems(weapons, 79).map((items, index) => {
    const suffix = String(index + 1).padStart(2, "0");
    return {
      inputCode: `${inputPrefix}${suffix}`,
      resultCode: `${resultPrefix}${suffix}`,
      items,
    };
  });

  return await transaction(async () => {
    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND (code LIKE ? OR code LIKE ?)
      `,
      [linkedSource, `${inputPrefix}%`, `${resultPrefix}%`]
    );

    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND extra_05 LIKE 'Weapon Crimson Socket%'
      `,
      [combineSource]
    );

    const linkedMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [linkedSource]
    );
    const combineMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [combineSource]
    );
    const combineCodeMax = await get(
      `
      SELECT COALESCE(MAX(CAST(REPLACE(code, ?, '') AS INTEGER)), 0) AS maxCode
      FROM items
      WHERE source_file = ?
        AND code LIKE ?
      `,
      [codePrefix, combineSource, `${codePrefix}%`]
    );

    const insertColumns = [
      "code",
      "name",
      "source_file",
      "excel_row",
      ...Array.from({ length: 160 }, (_, index) => `extra_${String(index + 1).padStart(2, "0")}`),
    ];
    const placeholders = insertColumns.map(() => "?").join(", ");
    const statement = await prepare(`
      INSERT INTO items (${insertColumns.join(", ")})
      VALUES (${placeholders})
    `);

    let linkedRow = Number(linkedMax.maxRow || 1) + 1;
    let combineRow = Number(combineMax.maxRow || 1) + 1;
    let combineCode = Number(combineCodeMax.maxCode || 0) + 1;
    let linkedInserted = 0;
    let combinesInserted = 0;

    try {
      for (const group of groups) {
        for (const groupCode of [group.inputCode, group.resultCode]) {
          const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
          values.code = groupCode;
          values.name = group.items[0]?.code ?? "";
          values.source_file = linkedSource;
          values.excel_row = linkedRow++;

          group.items.forEach((item, index) => {
            values[`extra_${String(index + 2).padStart(2, "0")}`] = item.code;
          });

          await runStatement(statement, insertColumns.map((column) => values[column]));
          linkedInserted++;
        }
      }

      for (let slot = 0; slot < 7; slot++) {
        for (let upgrade = 0; upgrade <= slot; upgrade++) {
          for (const group of groups) {
            const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
            values.code = `${codePrefix}${combineCode++}`;
            values.name = "100000";
            values.source_file = combineSource;
            values.excel_row = combineRow++;
            values.extra_02 = "100000";
            values.extra_03 = "11111";
            values.extra_04 = "1";
            values.extra_05 = `Weapon Crimson Socket ${slot} -> ${slot + 1} +${upgrade}`;
            values.extra_06 = "-1";
            values.extra_07 = "iywsu01";
            values.extra_08 = "FFFFFFFF";
            values.extra_09 = "1";
            values.extra_10 = group.inputCode;
            values.extra_11 = buildWeaponUpgradeValue(slot, upgrade);
            values.extra_12 = "1";
            values.extra_22 = "0";
            values.extra_23 = "1";
            values.extra_24 = group.resultCode;
            values.extra_25 = buildWeaponUpgradeValue(slot + 1, upgrade);
            values.extra_26 = "1";
            values.extra_27 = "3605";
            values.extra_28 = "10000";
            values.extra_29 = "1";

            await runStatement(statement, insertColumns.map((column) => values[column]));
            combinesInserted++;
          }
        }
      }
    } finally {
      await finalize(statement);
    }

    return {
      weapons: weapons.length,
      groups: groups.length,
      linkedInserted,
      combinesInserted,
    };
  });
}

function getWeaponCapFromLevel(levelValue) {
  const level = Number(String(levelValue ?? "").trim());
  for (const cap of [45, 50, 55, 60, 65]) {
    if (level >= cap - 5 && level <= cap) return cap;
  }
  return null;
}

async function generateCWeaponSocketCombines() {
  await ready;

  const weaponSource = "06_WeaponItem\\WeaponItem.xlsx";
  const combineSource = "CombineTable2.xlsx";
  const linkedSource = "LinkedCombines.xlsx";
  const codePrefix = "cocsa";
  const capPrefixes = new Map([
    [45, "wca"],
    [50, "wcb"],
    [55, "wcc"],
    [60, "wcd"],
    [65, "wce"],
  ]);

  const weapons = await all(
    `
    SELECT code, name, model, icon, level_lim AS levelLim, grade, type, subtype
    FROM items
    WHERE source_file = ?
      AND grade = '3'
      AND (name LIKE '%+%' OR name LIKE '%++%')
      AND name NOT LIKE '%Leon%'
      AND name NOT LIKE '%Crimson%'
      AND name NOT LIKE '%Crimsom%'
      AND name NOT LIKE '%Darkray%'
    ORDER BY level_lim + 0, type COLLATE NOCASE, subtype COLLATE NOCASE, model COLLATE NOCASE, code COLLATE NOCASE
    `,
    [weaponSource]
  );

  if (weapons.length === 0) {
    throw new Error("Nenhuma arma tipo C normal com + ou ++ encontrada.");
  }

  const weaponsByCap = new Map();
  for (const weapon of weapons) {
    const cap = getWeaponCapFromLevel(weapon.levelLim);
    if (!cap) continue;
    if (!weaponsByCap.has(cap)) weaponsByCap.set(cap, []);
    weaponsByCap.get(cap).push(weapon);
  }

  const groups = [];
  for (const [cap, items] of weaponsByCap.entries()) {
    const prefix = capPrefixes.get(cap);
    if (!prefix) continue;
    chunkItems(items, 79).forEach((chunk, index) => {
      const suffix = String(index + 1).padStart(2, "0");
      groups.push({
        cap,
        inputCode: `LL${prefix}${suffix}`,
        resultCode: `LR${prefix}${suffix}`,
        items: chunk,
      });
    });
  }

  return await transaction(async () => {
    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND (
          code LIKE 'LLwca%' OR code LIKE 'LRwca%'
          OR code LIKE 'LLwcb%' OR code LIKE 'LRwcb%'
          OR code LIKE 'LLwcc%' OR code LIKE 'LRwcc%'
          OR code LIKE 'LLwcd%' OR code LIKE 'LRwcd%'
          OR code LIKE 'LLwce%' OR code LIKE 'LRwce%'
        )
      `,
      [linkedSource]
    );

    await run(
      `
      DELETE FROM items
      WHERE source_file = ?
        AND extra_05 LIKE 'Weapon Type C Socket%'
      `,
      [combineSource]
    );

    const linkedMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [linkedSource]
    );
    const combineMax = await get(
      "SELECT COALESCE(MAX(excel_row), 1) AS maxRow FROM items WHERE source_file = ?",
      [combineSource]
    );
    const combineCodeMax = await get(
      `
      SELECT COALESCE(MAX(CAST(REPLACE(code, ?, '') AS INTEGER)), 0) AS maxCode
      FROM items
      WHERE source_file = ?
        AND code LIKE ?
      `,
      [codePrefix, combineSource, `${codePrefix}%`]
    );

    const insertColumns = [
      "code",
      "name",
      "source_file",
      "excel_row",
      ...Array.from({ length: 160 }, (_, index) => `extra_${String(index + 1).padStart(2, "0")}`),
    ];
    const placeholders = insertColumns.map(() => "?").join(", ");
    const statement = await prepare(`
      INSERT INTO items (${insertColumns.join(", ")})
      VALUES (${placeholders})
    `);

    let linkedRow = Number(linkedMax.maxRow || 1) + 1;
    let combineRow = Number(combineMax.maxRow || 1) + 1;
    let combineCode = Number(combineCodeMax.maxCode || 0) + 1;
    let linkedInserted = 0;
    let combinesInserted = 0;

    try {
      for (const group of groups) {
        for (const groupCode of [group.inputCode, group.resultCode]) {
          const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
          values.code = groupCode;
          values.name = group.items[0]?.code ?? "";
          values.source_file = linkedSource;
          values.excel_row = linkedRow++;
          group.items.forEach((item, index) => {
            values[`extra_${String(index + 2).padStart(2, "0")}`] = item.code;
          });
          await runStatement(statement, insertColumns.map((column) => values[column]));
          linkedInserted++;
        }
      }

      for (let slot = 0; slot < 7; slot++) {
        for (let upgrade = 0; upgrade <= slot; upgrade++) {
          for (const group of groups) {
            const values = Object.fromEntries(insertColumns.map((column) => [column, null]));
            values.code = `${codePrefix}${combineCode++}`;
            values.name = "100000";
            values.source_file = combineSource;
            values.excel_row = combineRow++;
            values.extra_02 = "100000";
            values.extra_03 = "11111";
            values.extra_04 = "1";
            values.extra_05 = `Weapon Type C Socket ${group.cap} ${slot} -> ${slot + 1} +${upgrade}`;
            values.extra_06 = "-1";
            values.extra_07 = "iycsa56";
            values.extra_08 = "FFFFFFFF";
            values.extra_09 = "1";
            values.extra_10 = group.inputCode;
            values.extra_11 = buildWeaponUpgradeValue(slot, upgrade);
            values.extra_12 = "1";
            values.extra_22 = "0";
            values.extra_23 = "1";
            values.extra_24 = group.resultCode;
            values.extra_25 = buildWeaponUpgradeValue(slot + 1, upgrade);
            values.extra_26 = "1";
            values.extra_27 = "3605";
            values.extra_28 = "10000";
            values.extra_29 = "1";
            await runStatement(statement, insertColumns.map((column) => values[column]));
            combinesInserted++;
          }
        }
      }
    } finally {
      await finalize(statement);
    }

    return {
      weapons: weapons.length,
      groups: groups.length,
      linkedInserted,
      combinesInserted,
    };
  });
}

async function listGeneratedWeaponSocketCombineRows() {
  await ready;

  const combineRows = await all(
    `
    SELECT *
    FROM items
    WHERE source_file = 'CombineTable2.xlsx'
      AND (
        extra_05 LIKE 'Weapon Grade 1 Socket%'
        OR extra_05 LIKE 'Weapon Leon Socket%'
        OR extra_05 LIKE 'Weapon Crimson Socket%'
        OR extra_05 LIKE 'Weapon Type C Socket%'
      )
    ORDER BY excel_row
    `
  );
  const linkedRows = await all(
    `
    SELECT *
    FROM items
    WHERE source_file = 'LinkedCombines.xlsx'
      AND (
        code LIKE 'LLwgb%' OR code LIKE 'LRwgb%'
        OR code LIKE 'LLwle%' OR code LIKE 'LRwle%'
        OR code LIKE 'LLwcr%' OR code LIKE 'LRwcr%'
        OR code LIKE 'LLwca%' OR code LIKE 'LRwca%'
        OR code LIKE 'LLwcb%' OR code LIKE 'LRwcb%'
        OR code LIKE 'LLwcc%' OR code LIKE 'LRwcc%'
        OR code LIKE 'LLwcd%' OR code LIKE 'LRwcd%'
        OR code LIKE 'LLwce%' OR code LIKE 'LRwce%'
      )
    ORDER BY excel_row
    `
  );

  return { combineRows, linkedRows };
}

function getExtraItemColumnCount() {
  return extraItemColumns.length;
}

module.exports = {
  clearItemsBySource,
  replaceSourceColumns,
  listSourceColumns,
  replaceExcelFileState,
  listExcelFileState,
  getExcelFilePath,
  getItemsForEdit,
  setAppSetting,
  getAppSetting,
  insertItem,
  insertItemEffect,
  replaceItemsFromSource,
  transaction,
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
  generateLeonWeaponSocketCombines,
  generateCrimsonWeaponSocketCombines,
  generateCWeaponSocketCombines,
  listGeneratedWeaponSocketCombineRows,
  getExtraItemColumnCount,
};
