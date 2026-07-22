'use strict';

const imageBase = 0x100000;
const classes = {
  RFExchangeBuySlot: 0xa423ba0,
  RFExchangeItemSlot: 0xa4248b0,
  RFExchangeSellSlot: 0xa424940,
  RFExchangeTransactionSlot: 0xa4249c8,
  RFPanelExchangeMain: 0xa448b78,
};
const moduleRange = Process.enumerateRanges('r--').find(r =>
  r.file && /\/libUnreal\.so$/.test(r.file.path) && r.file.offset === 0);
if (!moduleRange) throw new Error('libUnreal.so não encontrado');
const heaps = Process.enumerateRanges('rw-').filter(r => !r.file && r.size >= 0x100000);

function scan(pattern) {
  return heaps.flatMap(r => Memory.scanSync(r.base, r.size, pattern).map(h => h.address));
}

function isUnrealCode(pointer) {
  const range = Process.findRangeByAddress(pointer);
  return range && range.file && /\/libUnreal\.so$/.test(range.file.path);
}

for (const [name, ghidraGlobal] of Object.entries(classes)) {
  const global = moduleRange.base.add(ghidraGlobal - imageBase);
  const classPointer = global.readPointer();
  const native = scan(classPointer.toMatchPattern())
    .map(hit => hit.sub(0x10))
    .find(object => {
      try { return isUnrealCode(object.readPointer()); } catch (_) { return false; }
    });
  if (!native) {
    console.log(JSON.stringify({ name, global, classPointer, error: 'objeto nativo não encontrado' }));
    continue;
  }
  const vtable = native.readPointer();
  const objects = scan(vtable.toMatchPattern()).map(object => ({
    object,
    flags: object.add(8).readU32(),
    index: object.add(12).readS32(),
    classPointer: object.add(0x10).readPointer(),
    outer: object.add(0x20).readPointer(),
  }));
  console.log(JSON.stringify({ name, global, classPointer, native, vtable, objects }));
}
