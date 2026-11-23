// Gera todos os icones do app a partir de recursos/vaca.svg.
//
//   npm i -D sharp      (uma vez)
//   node scripts/gerar-icones.mjs
//
// Saidas: icones do Android (legado, redondo, adaptativo), icone de
// notificacao, splash e os icones do PWA em public/.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
const res = join(raiz, "android/app/src/main/res");
const vaca = readFileSync(join(raiz, "recursos/vaca.svg"), "utf8");
const silhueta = readFileSync(join(raiz, "recursos/vaca-notificacao.svg"), "utf8");

const VERDE_A = "#3DBB78";
const VERDE_B = "#1F7A4A";
const FUNDO_SPLASH = "#0F1417";

// So o conteudo do <svg> da vaca, para compor com fundo e escala.
const miolo = vaca.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");

const fundoVerde = (forma) => `
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="${VERDE_A}"/><stop offset="1" stop-color="${VERDE_B}"/>
  </linearGradient></defs>${forma}`;

/** Monta um SVG 1024 com fundo opcional e a vaca escalada em torno do centro. */
function composto({ fundo = "", escala = 1, deslocY = 0 }) {
  const t = `translate(512 ${512 + deslocY}) scale(${escala}) translate(-512 -512)`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">${fundo}<g transform="${t}">${miolo}</g></svg>`;
}

const quadrado = fundoVerde(`<rect width="1024" height="1024" rx="224" fill="url(#bg)"/>`);
const redondo = fundoVerde(`<circle cx="512" cy="512" r="512" fill="url(#bg)"/>`);
const cheio = fundoVerde(`<rect width="1024" height="1024" fill="url(#bg)"/>`);

async function png(svg, tamanho, destino, { largura, altura } = {}) {
  mkdirSync(dirname(destino), { recursive: true });
  await sharp(Buffer.from(svg), { density: 300 })
    .resize(largura ?? tamanho, altura ?? tamanho)
    .png()
    .toFile(destino);
}

const densidades = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };

for (const [nome, f] of Object.entries(densidades)) {
  const dir = join(res, `mipmap-${nome}`);
  // Legado (Android 7 e anteriores): 48dp, com fundo desenhado.
  await png(composto({ fundo: quadrado, escala: 0.92, deslocY: 18 }), 48 * f, join(dir, "ic_launcher.png"));
  await png(composto({ fundo: redondo, escala: 0.86, deslocY: 18 }), 48 * f, join(dir, "ic_launcher_round.png"));
  // Adaptativo: 108dp, so a vaca; o launcher recorta em circulo/squircle e
  // mostra apenas os 72dp do meio, por isso a escala menor.
  await png(composto({ escala: 0.72, deslocY: 14 }), 108 * f, join(dir, "ic_launcher_foreground.png"));
  // Notificacao: 24dp, branco puro.
  await png(silhueta, 24 * f, join(res, `drawable-${nome}`, "ic_stat_rastro.png"));
}

// Fundo do icone adaptativo: o mesmo degrade, em vetor.
writeFileSync(
  join(res, "drawable/ic_launcher_background.xml"),
  `<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:aapt="http://schemas.android.com/aapt"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:pathData="M0,0h108v108h-108z">
        <aapt:attr name="android:fillColor">
            <gradient android:type="linear" android:startX="0" android:startY="0"
                android:endX="108" android:endY="108"
                android:startColor="${VERDE_A}" android:endColor="${VERDE_B}"/>
        </aapt:attr>
    </path>
</vector>
`,
);

// Splash: vaca pequena no centro, fundo escuro do app.
const splashes = {
  "drawable": [480, 320],
  "drawable-land-mdpi": [480, 320], "drawable-land-hdpi": [800, 480],
  "drawable-land-xhdpi": [1280, 720], "drawable-land-xxhdpi": [1600, 960],
  "drawable-land-xxxhdpi": [1920, 1280],
  "drawable-port-mdpi": [320, 480], "drawable-port-hdpi": [480, 800],
  "drawable-port-xhdpi": [720, 1280], "drawable-port-xxhdpi": [960, 1600],
  "drawable-port-xxxhdpi": [1280, 1920],
};
for (const [pasta, [w, h]] of Object.entries(splashes)) {
  const lado = Math.round(Math.min(w, h) * 0.42);
  const icone = await sharp(Buffer.from(composto({ fundo: quadrado, escala: 0.92, deslocY: 18 })), { density: 300 })
    .resize(lado, lado).png().toBuffer();
  await sharp({ create: { width: w, height: h, channels: 4, background: FUNDO_SPLASH } })
    .composite([{ input: icone, gravity: "center" }])
    .png()
    .toFile(join(res, pasta, "splash.png"));
}

// PWA / navegador.
const pub = join(raiz, "public");
writeFileSync(join(pub, "icone.svg"), composto({ fundo: quadrado, escala: 0.92, deslocY: 18 }));
await png(composto({ fundo: quadrado, escala: 0.92, deslocY: 18 }), 192, join(pub, "icone-192.png"));
await png(composto({ fundo: quadrado, escala: 0.92, deslocY: 18 }), 512, join(pub, "icone-512.png"));
// Maskable: o sistema recorta; fundo cheio e vaca na zona segura (80%).
await png(composto({ fundo: cheio, escala: 0.66, deslocY: 12 }), 512, join(pub, "icone-maskable-512.png"));
await png(composto({ fundo: quadrado, escala: 0.92, deslocY: 18 }), 1024, join(raiz, "recursos/vaca-preview.png"));

console.log("icones gerados");
