#!/usr/bin/env node

import { printJson, withCDP } from "./lib/cdp.mjs";

const [, , wsUrl, rowsArg] = process.argv;

if (!wsUrl) {
  console.error("usage: gmail_inbox_snapshot.mjs <page-websocket-url> [rows=8]");
  process.exit(2);
}

const rowCount = Number(rowsArg || 8);

try {
  const value = await withCDP(wsUrl, (session) =>
    session.evaluate(`
      ({
        title: document.title,
        href: location.href,
        firstRows: Array.from(document.querySelectorAll('tr[role="row"]'))
          .slice(0, ${JSON.stringify(rowCount)})
          .map((tr, i) => ({ i, text: (tr.innerText || '').slice(0, 320) }))
      })
    `)
  );
  printJson(value ?? null);
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
