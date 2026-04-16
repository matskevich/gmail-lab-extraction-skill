#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { withCDP } from "./lib/cdp.mjs";

const [, , wsUrl, needle, outputDirArg] = process.argv;

if (!wsUrl || !needle || !outputDirArg) {
  console.error("usage: gmail_fetch_attachment_via_cdp.mjs <websocketDebuggerUrl> <needle> <output-dir>");
  process.exit(2);
}

const outputDir = path.resolve(outputDirArg);

try {
  const value = await withCDP(wsUrl, (session) =>
    session.evaluate(`
      (async () => {
        const needle = ${JSON.stringify(needle)};

        const attachmentNode = Array.from(document.querySelectorAll('[download_url]'))
          .find(el => {
            const raw = el.getAttribute('download_url') || '';
            const text = el.innerText || '';
            return raw.includes(needle) || text.includes(needle);
          });

        if (attachmentNode) {
          const raw = attachmentNode.getAttribute('download_url');
          const parts = raw.split(':');
          const filename = parts[1] || 'attachment.bin';
          const url = parts.slice(2).join(':');
          const res = await fetch(url, { credentials: 'include' });
          if (!res.ok) throw new Error('fetch failed: ' + res.status + ' for attachment');
          return await (async () => {
            const bytes = new Uint8Array(await res.arrayBuffer());
            let binary = '';
            const chunk = 0x8000;
            for (let i = 0; i < bytes.length; i += chunk) {
              binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
            }
            return {
              kind: 'attachment',
              filename,
              mimeType: res.headers.get('content-type') || 'application/octet-stream',
              base64: btoa(binary),
              size: bytes.length,
            };
          })();
        }

        const imageNode = Array.from(document.querySelectorAll('img[src]'))
          .find(img => {
            const src = img.currentSrc || img.src || '';
            const alt = img.alt || '';
            return src.includes(needle) || alt.includes(needle);
          });
        if (!imageNode) throw new Error('asset not found for needle: ' + needle);

        const src = imageNode.currentSrc || imageNode.src;
        const alt = (imageNode.alt || '').replace(/\\s+/g, ' ').trim();
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
        const hasExtension = (value) => /\\.[A-Za-z0-9]{2,5}$/.test((value || '').trim());
        const isGenericStem = (value) => !value || /^\\d+$/.test(value) || /^image$/i.test(value);
        let resolvedFilename = alt || (!isGenericStem(lastPath) ? lastPath : 'inline-image');
        if (!hasExtension(resolvedFilename) && ext) {
          resolvedFilename += ext;
        }
        return {
          kind: 'inline',
          filename: resolvedFilename,
          mimeType,
          base64: btoa(binary),
          size: bytes.length,
        };
      })()
    `)
  );

  if (!value?.filename || !value?.base64) {
    throw new Error("unexpected result payload");
  }

  await fs.mkdir(outputDir, { recursive: true });
  const safeFilename = sanitizeFilename(value.filename);
  let outPath = path.join(outputDir, safeFilename);
  const parsed = path.parse(outPath);
  let i = 2;
  while (await exists(outPath)) {
    outPath = path.join(parsed.dir, `${parsed.name} (${i})${parsed.ext}`);
    i += 1;
  }
  const buffer = Buffer.from(value.base64, "base64");
  await fs.writeFile(outPath, buffer);
  console.log(JSON.stringify({ kind: value.kind, saved_to: outPath, size: buffer.length, mimeType: value.mimeType }, null, 2));
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
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
  try {
    name = decodeURIComponent(input);
  } catch {}
  name = path.basename(name).replace(/[\/:\x00]/g, "_").trim();
  if (!name) name = "attachment.bin";
  const parsed = path.parse(name);
  const maxStem = 120;
  const stem = parsed.name.length > maxStem ? parsed.name.slice(0, maxStem) : parsed.name;
  return `${stem}${parsed.ext}`;
}
