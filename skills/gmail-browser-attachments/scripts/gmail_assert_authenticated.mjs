#!/usr/bin/env node

import { printJson, withCDP } from "./lib/cdp.mjs";

const [, , wsUrl] = process.argv;

if (!wsUrl) {
  console.error("usage: gmail_assert_authenticated.mjs <page-websocket-url>");
  process.exit(2);
}

try {
  const value = await withCDP(wsUrl, (session) =>
    session.evaluate(`
      (() => {
        const bodyText = document.body ? (document.body.innerText || '') : '';
        const href = location.href;
        const title = document.title || '';
        const rowCount = document.querySelectorAll('tr[role="row"]').length;
        const hasGmailShell = Boolean(document.querySelector('[role="main"]')) || rowCount > 0;
        const looksLikeAuthGate =
          /accounts\\.google\\.|ServiceLogin|signin|identifier|challenge/i.test(href) ||
          /sign in|choose an account|use your google account|войдите|выберите аккаунт/i.test(bodyText) ||
          /gmail/i.test(title) === false && /google/i.test(title) && rowCount === 0;

        return {
          title,
          href,
          rowCount,
          authenticated: hasGmailShell && !looksLikeAuthGate,
          authGate: looksLikeAuthGate,
        };
      })()
    `)
  );

  printJson(value ?? null);
  if (!value?.authenticated) {
    console.error(
      "gmail_not_authenticated: CDP page is not an authenticated Gmail mailbox; use Gmail API for native attachments, or start start_chrome_cdp_profile.sh and log into Gmail once for browser fallback."
    );
    process.exitCode = 1;
  }
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
