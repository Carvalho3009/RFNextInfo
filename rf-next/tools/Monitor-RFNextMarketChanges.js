'use strict';

const unreal = Process.enumerateRanges('r--').find(range =>
  range.file && /\/libUnreal\.so$/.test(range.file.path) && range.file.offset === 0);
if (!unreal) throw new Error('libUnreal.so não encontrado');

const vtable = unreal.base.add(0x9b248a8);
const watched = [];
for (const range of Process.enumerateRanges('rw-').filter(range => !range.file)) {
  for (const hit of Memory.scanSync(range.base, range.size, vtable.toMatchPattern())) {
    try {
      const price = Number(hit.address.add(0x48).readU64().toString());
      if (price === 4990 || price === 7000) {
        watched.push({ address: hit.address, bytes: new Uint8Array(hit.address.readByteArray(0x400)) });
      }
    } catch (_) {}
  }
}

console.log('RFNEXT_WATCH=' + JSON.stringify(watched.map(row => row.address.toString())));
let ticks = 0;
const timer = setInterval(() => {
  ticks++;
  for (const row of watched) {
    try {
      const next = new Uint8Array(row.address.readByteArray(0x400));
      for (let offset = 0; offset < next.length; offset += 4) {
        const oldValue = row.bytes[offset] | row.bytes[offset + 1] << 8 |
          row.bytes[offset + 2] << 16 | row.bytes[offset + 3] << 24;
        const newValue = next[offset] | next[offset + 1] << 8 |
          next[offset + 2] << 16 | next[offset + 3] << 24;
        if (oldValue !== newValue) {
          console.log(`RFNEXT_CHANGE=${row.address}+0x${offset.toString(16)} ${oldValue >>> 0}->${newValue >>> 0}`);
        }
      }
      row.bytes = next;
    } catch (_) {}
  }
  if (ticks >= 150) {
    clearInterval(timer);
    console.log('RFNEXT_WATCH_DONE');
  }
}, 100);
