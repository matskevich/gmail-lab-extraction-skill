#!/usr/bin/env node

import { CDPSession } from "./lib/cdp.mjs";

const [, , browserWsUrl, targetId] = process.argv;

if (!browserWsUrl || !targetId) {
  console.error("usage: chrome_cdp_close_target.mjs <browser-websocket-url> <target-id>");
  process.exit(2);
}

try {
  const session = new CDPSession(browserWsUrl);
  await session.connect();
  await session.send("Target.closeTarget", { targetId });
  await session.close();
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
