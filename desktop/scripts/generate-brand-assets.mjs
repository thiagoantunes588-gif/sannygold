import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const iconsDir = resolve(root, "resources", "icons");
const iconsetDir = resolve(iconsDir, "icon.iconset");

const crcTable = new Uint32Array(256);
for (let n = 0; n < 256; n += 1) {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  crcTable[n] = c >>> 0;
}

function crc32(buffer) {
  let c = 0xffffffff;
  for (const byte of buffer) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function makePng(width, height, paint) {
  const pixels = Buffer.alloc(width * height * 4);
  const image = {
    width,
    height,
    set(x, y, rgba) {
      if (x < 0 || y < 0 || x >= width || y >= height) return;
      const index = (y * width + x) * 4;
      pixels[index] = rgba[0];
      pixels[index + 1] = rgba[1];
      pixels[index + 2] = rgba[2];
      pixels[index + 3] = rgba[3];
    },
    fillRect(x, y, w, h, rgba) {
      const x0 = Math.max(0, Math.floor(x));
      const y0 = Math.max(0, Math.floor(y));
      const x1 = Math.min(width, Math.ceil(x + w));
      const y1 = Math.min(height, Math.ceil(y + h));
      for (let py = y0; py < y1; py += 1) {
        for (let px = x0; px < x1; px += 1) this.set(px, py, rgba);
      }
    },
    roundedRect(x, y, w, h, r, rgba) {
      const x0 = Math.floor(x);
      const y0 = Math.floor(y);
      const x1 = Math.ceil(x + w);
      const y1 = Math.ceil(y + h);
      const radius = Math.max(0, r);
      for (let py = y0; py < y1; py += 1) {
        for (let px = x0; px < x1; px += 1) {
          const cx = px < x + radius ? x + radius : px > x + w - radius ? x + w - radius : px;
          const cy = py < y + radius ? y + radius : py > y + h - radius ? y + h - radius : py;
          if ((px - cx) ** 2 + (py - cy) ** 2 <= radius ** 2) this.set(px, py, rgba);
        }
      }
    },
  };

  paint(image);

  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * (width * 4 + 1)] = 0;
    pixels.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(raw, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function brandIcon(size) {
  const scale = size / 1024;
  const c = (value) => Math.round(value * scale);
  return makePng(size, size, (img) => {
    img.roundedRect(c(64), c(64), c(896), c(896), c(176), [17, 24, 39, 255]);
    img.roundedRect(c(116), c(116), c(792), c(792), c(128), [24, 39, 52, 255]);
    img.fillRect(c(128), c(704), c(768), c(88), [23, 107, 135, 255]);
    img.fillRect(c(128), c(792), c(768), c(104), [244, 197, 66, 255]);
    img.roundedRect(c(292), c(254), c(440), c(82), c(34), [248, 250, 252, 255]);
    img.roundedRect(c(292), c(300), c(88), c(236), c(34), [248, 250, 252, 255]);
    img.roundedRect(c(328), c(472), c(364), c(82), c(34), [248, 250, 252, 255]);
    img.roundedRect(c(644), c(510), c(88), c(236), c(34), [248, 250, 252, 255]);
    img.roundedRect(c(292), c(688), c(440), c(82), c(34), [248, 250, 252, 255]);
    img.roundedRect(c(420), c(390), c(184), c(72), c(24), [244, 197, 66, 255]);
  });
}

function dmgBackground() {
  return makePng(660, 420, (img) => {
    img.fillRect(0, 0, 660, 420, [246, 247, 249, 255]);
    img.fillRect(0, 0, 660, 96, [17, 24, 39, 255]);
    img.fillRect(0, 96, 660, 6, [244, 197, 66, 255]);
    img.roundedRect(52, 42, 56, 56, 12, [244, 197, 66, 255]);
    img.roundedRect(130, 240, 96, 12, 6, [23, 107, 135, 255]);
    img.roundedRect(410, 240, 96, 12, 6, [23, 107, 135, 255]);
    img.roundedRect(176, 196, 284, 2, 1, [217, 222, 231, 255]);
  });
}

function makeIco(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  const entries = [];
  let offset = 6 + images.length * 16;
  for (const image of images) {
    const entry = Buffer.alloc(16);
    entry[0] = image.size >= 256 ? 0 : image.size;
    entry[1] = image.size >= 256 ? 0 : image.size;
    entry[2] = 0;
    entry[3] = 0;
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(image.data.length, 8);
    entry.writeUInt32LE(offset, 12);
    entries.push(entry);
    offset += image.data.length;
  }
  return Buffer.concat([header, ...entries, ...images.map((image) => image.data)]);
}

await rm(iconsetDir, { recursive: true, force: true });
await mkdir(iconsetDir, { recursive: true });

const pngs = new Map();
for (const size of [16, 32, 48, 64, 128, 256, 512, 1024]) {
  const data = brandIcon(size);
  pngs.set(size, data);
  await writeFile(resolve(iconsDir, `icon-${size}.png`), data);
}

await writeFile(resolve(iconsDir, "icon.png"), pngs.get(1024));
await writeFile(resolve(iconsDir, "icon.ico"), makeIco([16, 32, 48, 64, 128, 256].map((size) => ({ size, data: pngs.get(size) }))));

const iconsetMap = [
  ["icon_16x16.png", 16],
  ["icon_16x16@2x.png", 32],
  ["icon_32x32.png", 32],
  ["icon_32x32@2x.png", 64],
  ["icon_128x128.png", 128],
  ["icon_128x128@2x.png", 256],
  ["icon_256x256.png", 256],
  ["icon_256x256@2x.png", 512],
  ["icon_512x512.png", 512],
  ["icon_512x512@2x.png", 1024],
];

for (const [name, size] of iconsetMap) {
  await writeFile(resolve(iconsetDir, name), pngs.get(size));
}

const background = dmgBackground();
await writeFile(resolve(root, "resources", "dmg-background.png"), background);

const iconutil = spawnSync("iconutil", ["-c", "icns", "-o", resolve(iconsDir, "icon.icns"), iconsetDir], {
  stdio: "ignore",
});
const icnsGenerated = iconutil.status === 0;

const manifest = {
  generatedAt: new Date().toISOString(),
  iconSha256: createHash("sha256").update(pngs.get(1024)).digest("hex"),
  dmgBackgroundSha256: createHash("sha256").update(background).digest("hex"),
  icnsGenerated,
};
await writeFile(resolve(iconsDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
