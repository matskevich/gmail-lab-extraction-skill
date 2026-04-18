#!/usr/bin/env node

import { withCDP } from "./lib/cdp.mjs";

const [, , wsUrl, query, rowNeedle] = process.argv;

if (!wsUrl || !query || !rowNeedle) {
  console.error("usage: gmail_discover_thread_from_query.mjs <wsUrl> <query> <rowNeedle>");
  process.exit(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(session, checkExpression, timeoutMs = 15000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await session.evaluate(checkExpression);
    if (value) return value;
    await sleep(intervalMs);
  }
  throw new Error(`timeout waiting for condition: ${checkExpression}`);
}

async function warmThreadForHydration(session, maxPasses = 8, settleMs = 900) {
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
    await sleep(settleMs);
    if (nextHeight > 0 && nextHeight === lastHeight) {
      stablePasses += 1;
      if (stablePasses >= 2) break;
    } else {
      stablePasses = 0;
      lastHeight = nextHeight;
    }
  }
}

function diagnosticsExpression() {
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
      const attachmentCandidateNames = unique([...attachmentLines, ...attachmentMatches]).slice(0, 40);
      const inlineCandidateCount = Array.from(document.querySelectorAll('img[src]')).filter(img => {
        const src = img.currentSrc || img.src || '';
        const w = img.naturalWidth || img.width || 0;
        const h = img.naturalHeight || img.height || 0;
        const isGmailImageAttachment = src.includes('view=fimg') || /[?&]attid=/.test(src);
        return src && !src.startsWith('data:') && (isGmailImageAttachment || (Math.max(w, h) >= 80 && (w * h) >= 12000));
      }).length;
      const externalLinks = Array.from(document.querySelectorAll('a[href]'))
        .map((a) => ({ text: (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim(), href: a.href }))
        .filter((x) => x.href && !x.href.startsWith('https://mail.google.com/'));
      return {
        attachmentCandidateNames,
        attachmentCandidateCount: attachmentCandidateNames.length,
        downloadUrlCount: document.querySelectorAll('[download_url]').length,
        inlineCandidateCount,
        scanningForViruses: /scanning for viruses|проверка на вирусы|сканирование на вирусы/i.test(bodyText),
        openResultsPresent: /Открыть результаты|Open results/i.test(bodyText),
        externalLinks,
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

function classifyThread(diag) {
  if ((diag.attachmentCandidateCount || 0) > 0 || (diag.downloadUrlCount || 0) > 0) {
    return "candidate_attachment";
  }
  if ((diag.inlineCandidateCount || 0) > 0) {
    return "candidate_inline_only";
  }
  if (diag.openResultsPresent || (diag.externalLinks || []).some((x) => /invitro|cmd|kdl|dnkom|gemotest|prodia/i.test(x.href || ""))) {
    return "candidate_portal_only";
  }
  return "candidate_context_only";
}

try {
  const result = await withCDP(wsUrl, async (session) => {
    const searchUrl = `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(query)}`;
    await session.evaluate(`location.href = ${JSON.stringify(searchUrl)}`);
    await waitFor(session, `location.href.includes('#search/')`);
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

    await waitFor(session, `document.body && document.body.innerText.includes(${JSON.stringify(rowNeedle)}) && !location.href.endsWith('#inbox')`, 20000);

    await session.evaluate(`
      (() => {
        const btn = Array.from(document.querySelectorAll('[role="button"], span, div'))
          .find(el => /expand all|развернуть все/i.test(el.innerText || ''));
        if (btn) btn.click();
        return true;
      })()
    `);

    await sleep(1500);
    await warmThreadForHydration(session);
    let diagnostics = await session.evaluate(diagnosticsExpression());
    if (diagnostics.attachmentCandidateCount > 0 && diagnostics.downloadUrlCount === 0) {
      try {
        await waitFor(
          session,
          `(() => {
            const d = ${diagnosticsExpression()};
            return d.downloadUrlCount > 0 || !d.scanningForViruses;
          })()`,
          diagnostics.scanningForViruses ? 30000 : 12000,
          1000
        );
      } catch {}
      await sleep(1500);
      diagnostics = await session.evaluate(diagnosticsExpression());
    }

    const thread = await session.evaluate(`
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
        };
      })()
    `);

    return {
      query,
      rowNeedle,
      thread,
      diagnostics,
      discoveryClass: classifyThread(diagnostics),
    };
  });

  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
