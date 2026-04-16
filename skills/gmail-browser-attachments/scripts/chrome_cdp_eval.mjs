#!/usr/bin/env node

import { printJson, withCDP } from "./lib/cdp.mjs";

const [, , wsUrl, ...exprParts] = process.argv;

if (!wsUrl || exprParts.length === 0) {
  console.error("usage: chrome_cdp_eval.mjs <websocketDebuggerUrl> <javascript expression>");
  process.exit(2);
}

const expression = exprParts.join(" ");

try {
  const value = await withCDP(wsUrl, (session) => session.evaluate(expression, { returnByValue: false }));
  printJson(value);
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
