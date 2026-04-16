#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { withCDP } from "./lib/cdp.mjs";

const [, , wsUrl, query, rowNeedle, outputDirArg] = process.argv;

if (!wsUrl || !query || !rowNeedle || !outputDirArg) {
  console.error("usage: gmail_collect_inline_assets_from_query.mjs <wsUrl> <query> <rowNeedle> <outputDir>");
  process.exit(2);
}

const outputDir = path.resolve(outputDirArg);

function gmailThreadContextExpression() {
  return `
    (() => {
      const bodyText = document.body.innerText || '';
      const unique = (items) => Array.from(new Set(items.filter(Boolean)));
      const englishDates = Array.from(bodyText.matchAll(/(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d{1,2},\\s+\\d{4}(?:,\\s+\\d{1,2}:\\d{2}\\s*[AP]M)?/g)).map(m => m[0]);
      const simpleDates = Array.from(bodyText.matchAll(/(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d{1,2},\\s+\\d{4}/g)).map(m => m[0]);
      const ruDates = Array.from(bodyText.matchAll(/\\d{1,2}\\s+[А-Яа-яЁё]+\\s+\\d{4}/g)).map(m => m[0]);
      return {
        title: document.title,
        href: location.href,
        bodySnippet: bodyText.slice(0, 5000),
        visibleDates: unique([...englishDates, ...simpleDates, ...ruDates]).slice(0, 20),
        providerHints: {
          invitro: /ИНВИТРО|INVITRO/i.test(bodyText),
          cmd: /CMD/i.test(bodyText),
          kdl: /KDL/i.test(bodyText),
          hemotest: /Гемотест|Hemotest/i.test(bodyText),
          dnkom: /ДНКОМ|DNKOM/i.test(bodyText),
          prodia: /Prodia/i.test(bodyText),
        },
      };
    })()
  `;
}

async function waitFor(session, checkExpression, timeoutMs = 15000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await session.evaluate(checkExpression);
    if (value) return value;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`timeout waiting for condition: ${checkExpression}`);
}

async function exists(p) {
  try {
    await fs.stat(p);
    return true;
  } catch {
    return false;
  }
}

function sanitizeFilename(input) {
  let name = input;
  try { name = decodeURIComponent(input); } catch {}
  name = path.basename(name).replace(/[\/:\x00]/g, "_").trim();
  if (!name) name = "inline-asset.bin";
  const parsed = path.parse(name);
  const stem = parsed.name.length > 120 ? parsed.name.slice(0, 120) : parsed.name;
  return `${stem}${parsed.ext}`;
}

async function writeUniqueFile(filename, bytesBase64) {
  await fs.mkdir(outputDir, { recursive: true });
  let outPath = path.join(outputDir, sanitizeFilename(filename));
  const parsed = path.parse(outPath);
  let i = 2;
  while (await exists(outPath)) {
    outPath = path.join(parsed.dir, `${parsed.name} (${i})${parsed.ext}`);
    i += 1;
  }
  const buffer = Buffer.from(bytesBase64, "base64");
  await fs.writeFile(outPath, buffer);
  return { outPath, size: buffer.length };
}

try {
  const result = await withCDP(wsUrl, async (session) => {
    const searchUrl = `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(query)}`;
    await session.evaluate(`location.href = ${JSON.stringify(searchUrl)}`);
    await waitFor(session, `document.body && document.body.innerText.includes(${JSON.stringify(rowNeedle)})`, 20000);
    const clicked = await session.evaluate(`
      (() => {
        const row = Array.from(document.querySelectorAll('tr[role="row"]'))
          .find(tr => (tr.innerText || '').includes(${JSON.stringify(rowNeedle)}));
        if (!row) return false;
        row.click();
        return true;
      })()
    `);
    if (!clicked) throw new Error(`row not found for needle: ${rowNeedle}`);
    await waitFor(session, `!location.href.endsWith('#inbox')`, 20000);
    await new Promise((r) => setTimeout(r, 1500));

    const thread = await session.evaluate(gmailThreadContextExpression());

    const inlineAssets = await session.evaluate(`
      (() => {
        const seen = new Set();
        const out = [];
        for (const img of Array.from(document.querySelectorAll('img[src]'))) {
          const src = img.currentSrc || img.src || '';
          const alt = (img.alt || '').trim();
          const w = img.naturalWidth || img.width || 0;
          const h = img.naturalHeight || img.height || 0;
          const isGmailImageAttachment = src.includes('view=fimg') || /[?&]attid=/.test(src);
          if (!src || src.startsWith('data:')) continue;
          if (!isGmailImageAttachment && (Math.max(w, h) < 80 || (w * h) < 12000)) continue;
          if (seen.has(src)) continue;
          seen.add(src);
          out.push({ src, alt, width: w, height: h });
        }
        return out;
      })()
    `);
    if (!inlineAssets.length) throw new Error(`no inline assets found for row: ${rowNeedle}`);

    const saved = [];
    for (const asset of inlineAssets) {
      const payload = await session.evaluate(`
        (async () => {
          const src = ${JSON.stringify(asset.src)};
          const alt = ${JSON.stringify(asset.alt)};
          const res = await fetch(src, { credentials: 'include' });
          if (!res.ok) throw new Error('fetch failed: ' + res.status + ' for inline asset');
          const bytes = new Uint8Array(await res.arrayBuffer());
          let binary = '';
          const chunk = 0x8000;
          for (let i = 0; i < bytes.length; i += chunk) {
            binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
          }
          const mimeType = res.headers.get('content-type') || 'application/octet-stream';
          const ext = mimeType.includes('png') ? '.png' :
            mimeType.includes('jpeg') ? '.jpg' :
            mimeType.includes('webp') ? '.webp' :
            mimeType.includes('gif') ? '.gif' :
            mimeType.includes('tiff') ? '.tif' : '';
          const urlObj = (() => {
            try { return new URL(src); } catch { return null; }
          })();
          const lastPath = urlObj ? (urlObj.pathname.split('/').filter(Boolean).pop() || '') : '';
          const attId = urlObj ? (urlObj.searchParams.get('attid') || '') : '';
          const hasExtension = (value) => /\\.[A-Za-z0-9]{2,5}$/.test((value || '').trim());
          const isGenericStem = (value) => !value || /^\\d+$/.test(value) || /^image$/i.test(value);
          let filename = alt || (!isGenericStem(lastPath) ? lastPath : '');
          if (!filename) {
            filename = attId ? ('gmail-inline-' + attId) : 'inline-asset';
          }
          if (!hasExtension(filename) && ext) {
            filename += ext;
          }
          return {
            filename,
            mimeType,
            base64: btoa(binary),
            size: bytes.length,
          };
        })()
      `);
      const written = await writeUniqueFile(payload.filename, payload.base64);
      saved.push({ filename: payload.filename, size: payload.size, saved_to: written.outPath });
    }
    return { query, rowNeedle, thread, saved };
  });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
