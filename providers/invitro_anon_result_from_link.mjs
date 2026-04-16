#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { withCDP } from "../skills/gmail-browser-attachments/scripts/lib/cdp.mjs";

const [, , portalPageWsUrl, outputDirArg, patientHintArg = ""] = process.argv;

if (!portalPageWsUrl || !outputDirArg) {
  console.error("usage: invitro_anon_result_from_link.mjs <portalPageWsUrl> <outputDir> [patientLastNameHint]");
  process.exit(2);
}

const outputDir = path.resolve(outputDirArg);
const patientHint = patientHintArg.trim();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(session, expression, timeoutMs = 30000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await session.evaluate(expression);
    if (value) return value;
    await sleep(intervalMs);
  }
  throw new Error(`timeout waiting for condition: ${expression}`);
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
  const base = path.basename(input).replace(/[\/:\x00]/g, "_").trim();
  return base || "invitro-result.pdf";
}

function decodeMimeWords(input) {
  return input.replace(/=\?([^?]+)\?([bqBQ])\?([^?]+)\?=/g, (_full, charset, encoding, payload) => {
    const upper = String(encoding).toUpperCase();
    try {
      if (upper === "B") {
        return Buffer.from(payload, "base64").toString("utf8");
      }
      const qp = payload
        .replace(/_/g, " ")
        .replace(/=([0-9A-Fa-f]{2})/g, (_m, hex) => String.fromCharCode(parseInt(hex, 16)));
      return Buffer.from(qp, "binary").toString("utf8");
    } catch {
      return _full;
    }
  });
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

async function readLargeString(session, expression, totalLength, chunkSize = 500000) {
  let out = "";
  for (let offset = 0; offset < totalLength; offset += chunkSize) {
    const end = Math.min(totalLength, offset + chunkSize);
    const chunk = await session.evaluate(`(${expression}).slice(${offset}, ${end})`);
    if (typeof chunk !== "string") {
      throw new Error(`failed to read chunk at offset ${offset}`);
    }
    out += chunk;
  }
  return out;
}

try {
  const result = await withCDP(portalPageWsUrl, async (session) => {
    await waitFor(session, `document.readyState === 'complete'`, 45000);
    await waitFor(
      session,
      `(() => {
        const text = document.body?.innerText || '';
        return location.hostname.includes('invitro.ru') && text.length > 200;
      })()`,
      60000
    );
    await waitFor(
      session,
      `(() => {
        const text = document.body?.innerText || '';
        return /enter patient last name/i.test(text) || /INZ\\s+\\d+/i.test(text) || /Client:/i.test(text);
      })()`,
      90000
    );
    const needsLastName = await session.evaluate(`
      (() => /enter patient last name/i.test(document.body?.innerText || ''))()
    `);
    if (needsLastName) {
      if (!patientHint) {
        throw new Error("last name gate present but patient hint is missing");
      }
      const filled = await session.evaluate(`
        (() => {
          const hint = ${JSON.stringify(patientHint)};
          const input = document.querySelector('input[name="lastName"]');
          if (!input) return false;
          input.focus();
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          if (setter) setter.call(input, hint);
          else input.value = hint;
          input.dispatchEvent(new InputEvent('input', { bubbles: true, data: hint, inputType: 'insertText' }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
          const confirm = document.querySelector('button.LastNameModal_confirmButton__ReUpe')
            || Array.from(document.querySelectorAll('button,[role="button"]')).find(el => {
            const t = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            return t === 'Confirm' || /Confirm/i.test(t);
          });
          if (!confirm) return false;
          confirm.click();
          return true;
        })()
      `);
      if (!filled) {
        throw new Error("failed to satisfy last name gate");
      }
    }
    await waitFor(
      session,
      `(() => {
        const text = document.body?.innerText || '';
        return /INZ\\s+\\d+/i.test(text) || /Client:/i.test(text) || /Birth date:/i.test(text);
      })()`,
      90000
    );
    await waitFor(session, `(document.body?.innerText || '').includes('Download')`, 90000);
    await waitFor(
      session,
      `(() => Array.from(document.querySelectorAll('div,button,a,[role="button"]')).some(el => {
        const t = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
        return t === 'Download' || /Download/.test(t);
      }))()`,
      90000
    );

    const meta = await session.evaluate(`
      (() => {
        const text = document.querySelector('#root')?.innerText || document.body.innerText || '';
        const inz = (text.match(/INZ\\s+(\\d+)/i) || [])[1] || '';
        const client = (text.match(/Client:\\s*([^\\n]+)/i) || [])[1] || '';
        const birthDate = (text.match(/Birth date:\\s*([^\\n]+)/i) || [])[1] || '';
        return { title: document.title, href: location.href, inz, client, birthDate, text: text.slice(0, 4000) };
      })()
    `);

    await session.evaluate(`
      (async () => {
        const pageUrl = new URL(location.href);
        const fullKey = pageUrl.searchParams.get('key') || '';
        const lastName = pageUrl.searchParams.get('lastName') || ${JSON.stringify(patientHint)} || '';
        const parseResp = await fetch('/site/api/unauth/results/parse-key', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'content-type': 'application/json;charset=UTF-8' },
          body: JSON.stringify({ key: fullKey }),
        });
        if (!parseResp.ok) throw new Error('parse-key failed: ' + parseResp.status);
        const parsed = await parseResp.json();
        const transformedKey = parsed?.key || '';
        if (!transformedKey) throw new Error('parse-key returned empty key');

        let resolved = null;
        if (parsed.lastNameRequired) {
          if (!lastName) throw new Error('last name required but unavailable');
          const keyResp = await fetch(
            '/site/api/unauth/results/key?key=' + encodeURIComponent(transformedKey) + '&lastName=' + encodeURIComponent(lastName),
            { credentials: 'same-origin' }
          );
          if (!keyResp.ok) throw new Error('results/key failed: ' + keyResp.status);
          resolved = await keyResp.json();
        }

        const resolvedKey = resolved?.key || transformedKey;
        const result = resolved?.result || null;
        const inz = (result?.inz || ${JSON.stringify(meta.inz)} || '').replace(/\\D+/g, '');
        if (!inz) throw new Error('inz not found');
        const pdfUrl = 'https://lk3.invitro.ru/site/api/unauth/results/pdf?download=true'
          + '&inz=' + encodeURIComponent(inz)
          + '&key=' + encodeURIComponent(resolvedKey)
          + '&lang=ru&territory=RUSSIA';
        const res = await fetch(pdfUrl, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('pdf fetch failed: ' + res.status);

        const bytes = new Uint8Array(await res.arrayBuffer());
        let binary = '';
        const chunk = 0x8000;
        for (let i = 0; i < bytes.length; i += chunk) {
          binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
        }

        const cd = res.headers.get('content-disposition') || '';
        let filename = '';
        const m = cd.match(/filename\\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?/i);
        if (m) filename = decodeURIComponent(m[1] || m[2] || '');
        if (!filename) {
          const inz = (${JSON.stringify(meta.inz)} || 'invitro');
          filename = inz + '_invitro_result.pdf';
        }

        const base64 = btoa(binary);
        globalThis.__codexPdfTransfer = {
          pdfUrl,
          filename,
          mimeType: res.headers.get('content-type') || 'application/pdf',
          base64,
          size: bytes.length,
          flow: {
            lastNameRequired: !!parsed.lastNameRequired,
            transformedKeyLength: transformedKey.length,
            resolvedKeyLength: resolvedKey.length,
          },
          result,
        };
        return true;
      })()
    `);

    const pdfMeta = await session.evaluate(`
      (() => {
        const payload = globalThis.__codexPdfTransfer || null;
        if (!payload) return null;
        return {
          pdfUrl: payload.pdfUrl,
          filename: payload.filename,
          mimeType: payload.mimeType,
          size: payload.size,
          base64Length: (payload.base64 || '').length,
          flow: payload.flow,
          result: payload.result,
        };
      })()
    `);
    if (!pdfMeta?.base64Length) {
      throw new Error("pdf base64 transfer metadata missing");
    }
    const pdfBase64 = await readLargeString(session, `globalThis.__codexPdfTransfer.base64`, pdfMeta.base64Length);
    await session.evaluate(`delete globalThis.__codexPdfTransfer`);

    pdfMeta.filename = decodeMimeWords(pdfMeta.filename || "");
    const written = await writeUniqueFile(pdfMeta.filename, pdfBase64);
    return {
      provider: "invitro",
      saved_to: written.outPath,
      size: written.size,
      pdf_url: pdfMeta.pdfUrl,
      mimeType: pdfMeta.mimeType,
      patient_hint: patientHint,
      meta: {
        ...meta,
        analysisDate: pdfMeta.result?.createdTime || "",
        inz: pdfMeta.result?.inz || meta.inz || "",
        client: pdfMeta.result?.patient
          ? [pdfMeta.result.patient.lastName, pdfMeta.result.patient.firstName, pdfMeta.result.patient.middleName].filter(Boolean).join(" ")
          : meta.client,
        birthDate: pdfMeta.result?.patient?.birthday || meta.birthDate || "",
      },
      flow: pdfMeta.flow,
      result: pdfMeta.result,
    };
  });

  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err));
  process.exitCode = 1;
}
