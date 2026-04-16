export class CDPSession {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    if (this.ws) return;
    this.ws = new WebSocket(this.wsUrl);
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    });
    this.ws.addEventListener("error", (err) => {
      for (const { reject } of this.pending.values()) reject(err);
      this.pending.clear();
    });
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
  }

  async send(method, params = {}) {
    await this.connect();
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return await new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
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
