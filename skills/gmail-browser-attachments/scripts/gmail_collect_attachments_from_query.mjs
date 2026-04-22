#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { withCDP } from "./lib/cdp.mjs";

const [, , wsUrl, query, rowNeedle, outputDirArg] = process.argv;

if (!wsUrl || !query || !rowNeedle || !outputDirArg) {
  console.error("usage: gmail_collect_attachments_from_query.mjs <wsUrl> <query> <rowNeedle> <outputDir>");
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

function gmailAssetDiagnosticsExpression() {
  return `
    (() => {
      const bodyText = document.body.innerText || '';
      const unique = (items) => Array.from(new Set(items.filter(Boolean)));
      const sanitizeName = (value) => (value || '')
        .trim()
        .replace(/^["'([<{\\s]+/, '')
        .replace(/["')>},;:\\s]+$/, '');
      const attachmentLines = bodyText
        .split('\\n')
        .map(line => sanitizeName(line))
        .filter(line => /\\.(?:pdf|jpe?g|png|gif|webp|tiff?)$/i.test(line));
      const attachmentMatches = Array.from(
        bodyText.matchAll(/[^\\n]{1,220}?\\.(?:pdf|jpe?g|png|gif|webp|tiff?)/ig)
      ).map(match => sanitizeName(match[0]));
      const attachmentCandidateNames = unique([...attachmentLines, ...attachmentMatches]).slice(0, 30);
      const inlineCandidateCount = Array.from(document.querySelectorAll('img[src]')).filter(img => {
        const src = img.currentSrc || img.src || '';
        const w = img.naturalWidth || img.width || 0;
        const h = img.naturalHeight || img.height || 0;
        const isGmailImageAttachment = src.includes('view=fimg') || /[?&]attid=/.test(src);
        return src && !src.startsWith('data:') && (isGmailImageAttachment || (Math.max(w, h) >= 80 && (w * h) >= 12000));
      }).length;
      return {
        attachmentCandidateNames,
        attachmentCandidateCount: attachmentCandidateNames.length,
        downloadUrlCount: document.querySelectorAll('[download_url]').length,
        inlineCandidateCount,
        scanningForViruses: /scanning for viruses|проверка на вирусы|сканирование на вирусы/i.test(bodyText),
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

async function waitForSearchResultsRow(session, rowNeedle, timeoutMs = 20000) {
  return await waitFor(
    session,
    `(() => {
      const needle = ${JSON.stringify(rowNeedle)};
      return Array.from(document.querySelectorAll('tr[role="row"]'))
        .some(tr => (tr.innerText || '').includes(needle));
    })()`,
    timeoutMs,
    500
  );
}

async function waitForSearchQuery(session, timeoutMs = 20000) {
  return await waitFor(
    session,
    `(() => {
      return location.hash.startsWith('#search/') && /^Search results\\b/i.test(document.title || '');
    })()`,
    timeoutMs,
    500
  );
}

async function warmThreadForAssetHydration(session, maxPasses = 8, settleMs = 900) {
  let lastHeight = 0;
  let stablePasses = 0;
  for (let i = 0; i < maxPasses; i += 1) {
    const nextHeight = await session.evaluate(`
      (() => {
        const doc = document.scrollingElement || document.body || document.documentElement;
        if (!doc) return 0;
        window.scrollTo(0, doc.scrollHeight || 0);
        return doc.scrollHeight || 0;
      })()
    `);
    await new Promise((r) => setTimeout(r, settleMs));
    if (nextHeight > 0 && nextHeight === lastHeight) {
      stablePasses += 1;
      if (stablePasses >= 2) break;
    } else {
      stablePasses = 0;
      lastHeight = nextHeight;
    }
  }
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

function isGenericInlineFilename(filename) {
  const lower = (filename || "").toLowerCase();
  return (
    lower.startsWith("gmail-inline-") ||
    lower.startsWith("inline-asset") ||
    lower.startsWith("adkq_")
  );
}

function skipReasonForPayload(payload, { hasAttachmentAssets }) {
  if (payload.kind !== "inline") return null;
  if (payload.size <= 0) return "zero_byte_inline";

  if (!hasAttachmentAssets) return null;

  const genericInline = isGenericInlineFilename(payload.filename);
  const lowerMime = (payload.mimeType || "").toLowerCase();
  const isWebp = lowerMime.includes("image/webp") || (payload.filename || "").toLowerCase().endsWith(".webp");
  const isSmall = payload.size < 150_000;

  if (genericInline && isWebp) return "generic_webp_inline_with_attachments";
  if (genericInline && isSmall) return "small_generic_inline_with_attachments";
  return null;
}

try {
  const result = await withCDP(wsUrl, async (session) => {
    const searchUrl = `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(query)}`;
    await session.evaluate(`location.href = ${JSON.stringify(searchUrl)}`);
    await waitForSearchQuery(session, 20000);
    await waitForSearchResultsRow(session, rowNeedle, 20000);

    const clicked = await session.evaluate(`
      (() => {
        const rowNeedle = ${JSON.stringify(rowNeedle)};
        const row = Array.from(document.querySelectorAll('tr[role="row"]'))
          .find(tr => (tr.innerText || '').includes(rowNeedle));
        if (!row) return false;
        row.click();
        return true;
      })()
    `);
    if (!clicked) throw new Error(`row not found for needle: ${rowNeedle}`);

    await waitFor(
      session,
      `(() => {
        const bodyText = document.body ? (document.body.innerText || '') : '';
        return !/^Search results\\b/i.test(document.title || '') && bodyText.includes(${JSON.stringify(rowNeedle)});
      })()`,
      20000,
      500
    );

    // Expand all messages in the thread if Gmail exposes a control.
    await session.evaluate(`
      (() => {
        const candidates = Array.from(document.querySelectorAll('[role="button"], span, div'));
        const btn = candidates.find(el => /expand all|развернуть все/i.test(el.innerText || ''));
        if (btn) btn.click();
        return true;
      })()
    `);

    await new Promise((r) => setTimeout(r, 1500));
    await warmThreadForAssetHydration(session);
    const diagnosticsExpression = gmailAssetDiagnosticsExpression();
    try {
      await waitFor(
        session,
        `(() => {
          const d = ${diagnosticsExpression};
          return d.downloadUrlCount > 0 || d.inlineCandidateCount > 0 || d.attachmentCandidateCount > 0;
        })()`,
        10000,
        750
      );
    } catch {
      // Some threads genuinely have no visible assets; fall through to diagnostic error below.
    }

    let diagnostics = await session.evaluate(diagnosticsExpression);
    if (diagnostics.attachmentCandidateCount > 0 && diagnostics.downloadUrlCount === 0) {
      try {
        await waitFor(
          session,
          `(() => {
            const d = ${diagnosticsExpression};
            return d.downloadUrlCount > 0 || !d.scanningForViruses;
          })()`,
          diagnostics.scanningForViruses ? 30000 : 12000,
          1000
        );
      } catch {
        // Fall through with diagnostics captured below; caller can inspect counts.
      }
      await new Promise((r) => setTimeout(r, 1500));
      diagnostics = await session.evaluate(diagnosticsExpression);
    }

    if (diagnostics.downloadUrlCount === 0 && diagnostics.inlineCandidateCount > 0) {
      await warmThreadForAssetHydration(session, 5, 1000);
      await new Promise((r) => setTimeout(r, 1000));
      diagnostics = await session.evaluate(diagnosticsExpression);
    }

    const thread = await session.evaluate(gmailThreadContextExpression());
    thread.attachmentNames = diagnostics.attachmentCandidateNames;
    thread.attachmentCandidateCount = diagnostics.attachmentCandidateCount;
    thread.downloadUrlCount = diagnostics.downloadUrlCount;
    thread.inlineCandidateCount = diagnostics.inlineCandidateCount;
    thread.scanningForViruses = diagnostics.scanningForViruses;

    const assets = await session.evaluate(`
      (() => {
        const seen = new Set();
        const assets = [];

        for (const el of Array.from(document.querySelectorAll('[download_url]'))) {
          const raw = el.getAttribute('download_url');
          if (!raw || seen.has(raw)) continue;
          seen.add(raw);
          const parts = raw.split(':');
          assets.push({
            kind: 'attachment',
            raw,
            filename: parts[1] || 'attachment.bin',
            url: parts.slice(2).join(':'),
            text: (el.innerText || '').trim(),
          });
        }

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
          assets.push({
            kind: 'inline',
            raw: src,
            filename: alt || '',
            url: src,
            text: alt,
          });
        }

        return assets;
      })()
    `);
    if (!assets?.length) {
      throw new Error(
        `no assets found for row: ${rowNeedle}; attachment_candidate_count=${diagnostics.attachmentCandidateCount}; download_url_count=${diagnostics.downloadUrlCount}; inline_candidate_count=${diagnostics.inlineCandidateCount}; scanning_for_viruses=${diagnostics.scanningForViruses}`
      );
    }

    const hasAttachmentAssets = assets.some((asset) => asset.kind === "attachment");
    const saved = [];
    const filterSummary = {};
    const fetchErrorSummary = {};
    for (const att of assets) {
      let payload;
      try {
        payload = await session.evaluate(`
          (async () => {
            const url = ${JSON.stringify(att.url)};
            const filename = ${JSON.stringify(att.filename)};
            const kind = ${JSON.stringify(att.kind)};
            const res = await fetch(url, { credentials: 'include' });
            if (!res.ok) throw new Error('fetch failed: ' + res.status + ' for ' + filename);
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
              try { return new URL(url); } catch { return null; }
            })();
            const lastPath = urlObj ? (urlObj.pathname.split('/').filter(Boolean).pop() || '') : '';
            const attId = urlObj ? (urlObj.searchParams.get('attid') || '') : '';
            const hasExtension = (value) => /\\.[A-Za-z0-9]{2,5}$/.test((value || '').trim());
            const isGenericStem = (value) => !value || /^\\d+$/.test(value) || /^image$/i.test(value);
            let resolvedFilename = (filename || '').trim();
            if (!resolvedFilename) {
              if (!isGenericStem(lastPath)) {
                resolvedFilename = lastPath;
              } else if (kind === 'inline' && attId) {
                resolvedFilename = 'gmail-inline-' + attId;
              } else {
                resolvedFilename = kind === 'inline' ? 'inline-asset' : 'attachment';
              }
            }
            if (!hasExtension(resolvedFilename) && ext) {
              resolvedFilename += ext;
            }
            return {
              kind,
              filename: resolvedFilename,
              mimeType,
              base64: btoa(binary),
              size: bytes.length,
            };
          })()
        `);
      } catch (err) {
        const key = `${att.kind}_fetch_error`;
        fetchErrorSummary[key] = (fetchErrorSummary[key] || 0) + 1;
        continue;
      }
      if (!payload?.base64 || !payload.filename) {
        const key = `${att.kind}_invalid_payload`;
        fetchErrorSummary[key] = (fetchErrorSummary[key] || 0) + 1;
        continue;
      }
      const skipReason = skipReasonForPayload(payload, { hasAttachmentAssets });
      if (skipReason) {
        filterSummary[skipReason] = (filterSummary[skipReason] || 0) + 1;
        continue;
      }
      const written = await writeUniqueFile(payload.filename, payload.base64);
      saved.push({ kind: payload.kind, filename: payload.filename, size: payload.size, saved_to: written.outPath });
    }

    const savedCounts = saved.reduce((acc, item) => {
      acc[item.kind] = (acc[item.kind] || 0) + 1;
      return acc;
    }, {});

    return { query, rowNeedle, thread, diagnostics, savedCounts, filterSummary, fetchErrorSummary, saved };
  });
  console.log(JSON.stringify(result, null, 2));
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
