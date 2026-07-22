'use strict';

const modelVtableOffset = 0x9b248a8; // RF Online NEXT 1.28.5
const unreal = Process.enumerateRanges('r--').find(range =>
  range.file && /\/libUnreal\.so$/.test(range.file.path) && range.file.offset === 0);
if (!unreal) throw new Error('libUnreal.so não encontrado');

const modelVtable = unreal.base.add(modelVtableOffset);
const prices = new Set([4990, 7000]);
const rows = [];

for (const range of Process.enumerateRanges('rw-').filter(range => !range.file)) {
  for (const hit of Memory.scanSync(range.base, range.size, modelVtable.toMatchPattern())) {
    try {
      const price = Number(hit.address.add(0x48).readU64().toString());
      if (!prices.has(price)) continue;

      const small = {};
      for (let offset = 0x60; offset < 0x200; offset += 4) {
        const value = hit.address.add(offset).readU32();
        if (value > 0 && value <= 10000) small['0x' + offset.toString(16)] = value;
      }
      rows.push({ address: hit.address.toString(), price, small });
    } catch (_) {}
  }
}

console.log('RFNEXT_MARKET=' + JSON.stringify({
  timestamp: new Date().toISOString(),
  unrealBase: unreal.base.toString(),
  modelVtable: modelVtable.toString(),
  rows,
}));
