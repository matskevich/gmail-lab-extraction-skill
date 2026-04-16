#!/usr/bin/env node

import { CDPSession, printJson } from "./lib/cdp.mjs";

const [, , browserWsUrl, targetUrl] = process.argv;

if (!browserWsUrl || !targetUrl) {
  console.error("usage: chrome_cdp_create_target.mjs <browser-websocket-url> <target-url>");
  process.exit(2);
}

try {
  const session = new CDPSession(browserWsUrl);
  await session.connect();
  const value = await session.send("Target.createTarget", { url: targetUrl });
  await session.close();
  printJson(value);
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
