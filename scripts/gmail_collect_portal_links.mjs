#!/usr/bin/env node

import { withCDP } from "../skills/gmail-browser-attachments/scripts/lib/cdp.mjs";

const [, , wsUrl, locator, rowNeedle = ""] = process.argv;

if (!wsUrl || !locator) {
  console.error("usage: gmail_collect_portal_links.mjs <gmailPageWsUrl> <locator> [rowNeedle]");
  process.exit(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(session, expression, timeoutMs = 25000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await session.evaluate(expression);
    if (value) return value;
    await sleep(intervalMs);
  }
  throw new Error(`timeout waiting for condition: ${expression}`);
}

async function waitForSearchResultsRow(session, rowNeedle, timeoutMs = 25000) {
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

async function waitForSearchQuery(session, timeoutMs = 25000) {
  return await waitFor(
    session,
    `(() => {
      return location.hash.startsWith('#search/') && /^Search results\\b/i.test(document.title || '');
    })()`,
    timeoutMs,
    500
  );
}

function locatorToUrl(value) {
  if (/^https:\/\/mail\.google\.com\//.test(value)) return value;
  if (/^[0-9a-f]{16,}$/i.test(value)) return `https://mail.google.com/mail/u/0/#all/${value}`;
  return null;
}

try {
  const result = await withCDP(wsUrl, async (session) => {
    const directUrl = locatorToUrl(locator);
    if (directUrl) {
      await session.evaluate(`location.href = ${JSON.stringify(directUrl)}`);
      await waitFor(session, `document.title.length > 0 && !document.title.startsWith('Search results')`, 30000);
    } else {
      if (!rowNeedle) throw new Error("rowNeedle is required for query locator");
      const searchUrl = `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(locator)}`;
      await session.evaluate(`location.href = ${JSON.stringify(searchUrl)}`);
      await waitForSearchQuery(session, 25000);
      await waitForSearchResultsRow(session, rowNeedle, 25000);
      const clicked = await session.evaluate(`
        (() => {
          const needle = ${JSON.stringify(rowNeedle)};
          const row = Array.from(document.querySelectorAll('tr[role="row"]'))
            .find(tr => (tr.innerText || '').includes(needle));
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
        30000,
        500
      );
    }

    await session.evaluate(`
      (() => {
        const btn = Array.from(document.querySelectorAll('[role="button"], span, div'))
          .find(el => /expand all|развернуть все/i.test(el.innerText || ''));
        if (btn) btn.click();
        return true;
      })()
    `);
    await sleep(1500);

    return await session.evaluate(`
      (() => {
        const links = Array.from(document.querySelectorAll('a[href]'))
          .map((a, i) => ({
            i,
            text: (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim(),
            href: a.href,
          }))
          .filter(x => x.href && !x.href.startsWith('https://mail.google.com/'));
        const attachmentNames = Array.from(document.querySelectorAll('[download_url]'))
          .map((el) => {
            const raw = el.getAttribute('download_url') || '';
            const parts = raw.split(':');
            return (parts[1] || '').trim();
          })
          .filter(Boolean);

        const bodyText = document.body.innerText || '';
        return {
          title: document.title,
          href: location.href,
          locator: ${JSON.stringify(locator)},
          rowNeedle: ${JSON.stringify(rowNeedle)},
          attachmentCount: document.querySelectorAll('[download_url]').length,
          openResultsPresent: /Открыть результаты/i.test(bodyText),
          providerHints: {
            invitro: /ИНВИТРО|INVITRO/i.test(bodyText),
            cmd: /CMD/i.test(bodyText),
            kdl: /KDL/i.test(bodyText),
            hemotest: /Гемотест|Hemotest/i.test(bodyText),
          },
          attachmentNames,
          bodySnippet: bodyText.slice(0, 5000),
          links,
        };
      })()
    `);
  });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
