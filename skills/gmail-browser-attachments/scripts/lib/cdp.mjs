export class CDPSession {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  rejectAllPending(error) {
    for (const { reject, timeout } of this.pending.values()) {
      clearTimeout(timeout);
      reject(error);
    }
    this.pending.clear();
  }

  async connect() {
    if (this.ws) return;
    this.ws = new WebSocket(this.wsUrl);
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject, timeout } = this.pending.get(msg.id);
        clearTimeout(timeout);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    });
    this.ws.addEventListener("error", (err) => {
      this.rejectAllPending(err instanceof Error ? err : new Error(String(err)));
    });
    this.ws.addEventListener("close", () => {
      this.rejectAllPending(new Error(`cdp websocket closed: ${this.wsUrl}`));
      this.ws = null;
    });
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
  }

  async send(method, params = {}, timeoutMs = 60000) {
    await this.connect();
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`cdp command timed out after ${timeoutMs}ms: ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timeout });
    });
  }

  async enableRuntime() {
    await this.send("Runtime.enable");
  }

  async evaluate(expression, { returnByValue = true } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue,
      userGesture: true,
    });
    if (result.exceptionDetails) {
      const text = result.exceptionDetails.text || "Runtime.evaluate exception";
      const description = result.exceptionDetails.exception?.description || "";
      throw new Error(description ? `${text}: ${description}` : text);
    }
    return returnByValue ? result.result?.value : result.result;
  }

  async close() {
    if (this.ws) this.ws.close();
    this.ws = null;
  }
}

export async function withCDP(wsUrl, fn) {
  const session = new CDPSession(wsUrl);
  try {
    await session.enableRuntime();
    return await fn(session);
  } finally {
    await session.close();
  }
}

export function printJson(value) {
  console.log(JSON.stringify(value, null, 2));
}
