import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { build } from "esbuild";
import {
  sealSession,
  openSession,
  linkedinQuery,
  canonicalCloudPost,
  reserveBrowserSeconds,
} from "../src/linkedin-cloud-core.js";

const secret = "12".repeat(32);
function database() {
  const db = new DatabaseSync(":memory:");
  db.exec(
    readFileSync(
      new URL("../migrations/0001_initial.sql", import.meta.url),
      "utf8",
    ),
  );
  db.exec(
    "INSERT INTO profiles(id,filename,pdf,data,confirmed) VALUES('p','cv.pdf','x','{}',1)",
  );
  db.exec("ALTER TABLE jobs ADD COLUMN triage_key TEXT");
  db.exec(
    readFileSync(
      new URL("../migrations/0010_search_lifecycle.sql", import.meta.url),
      "utf8",
    ),
  );
  db.exec(
    readFileSync(
      new URL("../migrations/0011_catalog_search.sql", import.meta.url),
      "utf8",
    ),
  );
  return {
    db,
    DB: {
      prepare(sql) {
        let args = [];
        return {
          bind(...values) {
            args = values;
            return this;
          },
          async first() {
            return db.prepare(sql).get(...args) || null;
          },
          async all() {
            return { results: db.prepare(sql).all(...args) };
          },
          async run() {
            return { meta: db.prepare(sql).run(...args) };
          },
        };
      },
    },
  };
}
test("session encryption is randomized, authenticated and rejects the wrong key", async () => {
  const value = {
    cookies: [{ name: "li_at", value: "PRIVATE_SESSION" }],
    origins: [],
  };
  const a = await sealSession(value, secret),
    b = await sealSession(value, secret);
  assert.notDeepEqual(a, b);
  assert.deepEqual(await openSession(a, secret), value);
  assert.ok(!JSON.stringify(a).includes("PRIVATE_SESSION"));
  await assert.rejects(openSession(a, "34".repeat(32)));
  a.data[0] ^= 1;
  await assert.rejects(openSession(a, secret));
});
test("search rotates groups, retains region filters and rejects unrelated post URLs", () => {
  const config = {
    keywords: "React,Node.js,Python,SQL",
    country: "LATAM",
    remoteOnly: true,
  };
  const first = linkedinQuery(config);
  const second = linkedinQuery(config, first.next);
  assert.match(first.text, /React/);
  assert.match(first.text, /Latin America/);
  assert.match(second.text, /SQL/);
  assert.equal(second.next, 0);
  assert.throws(() => linkedinQuery({ keywords: "" }));
  assert.equal(
    canonicalCloudPost(
      "https://www.linkedin.com/posts/a_activity-123-xyz?trk=x",
    ),
    "https://www.linkedin.com/feed/update/urn:li:activity:123/",
  );
  assert.equal(
    canonicalCloudPost("https://linkedin.com.evil.com/posts/foo"),
    null,
  );
});
test("shared browser budget is atomic and includes earlier application browser reservations", async () => {
  const e = database();
  try {
    assert.equal(await reserveBrowserSeconds(e, 240), true);
    const attempts = await Promise.all(
      Array.from({ length: 5 }, () => reserveBrowserSeconds(e, 105)),
    );
    assert.equal(attempts.filter(Boolean).length, 2);
    assert.equal(
      e.db.prepare("SELECT count FROM usage WHERE kind='browser_seconds'").get()
        .count,
      450,
    );
    assert.equal(await reserveBrowserSeconds(e, 150), false);
    e.db.exec(
      "DELETE FROM usage; INSERT INTO usage VALUES(date('now'),'browser',3)",
    );
    assert.equal(await reserveBrowserSeconds(e, 105), false);
  } finally {
    e.db.close();
  }
});

// Real application code with only the external browser transport replaced.
const bundled = await build({
  entryPoints: ["src/linkedin-cloud.js"],
  bundle: true,
  write: false,
  format: "esm",
  platform: "node",
  plugins: [
    {
      name: "fake-browser-transport",
      setup(b) {
        b.onResolve({ filter: /^@cloudflare\/playwright$/ }, () => ({
          path: "fake",
          namespace: "fake",
        }));
        b.onLoad({ filter: /.*/, namespace: "fake" }, () => ({
          contents:
            "export const launch=(...a)=>globalThis.__transport.launch(...a);export const connect=(...a)=>globalThis.__transport.connect(...a);",
          loader: "js",
        }));
      },
    },
  ],
});
const { LinkedInCloud } = await import(
  "data:text/javascript;base64," +
    Buffer.from(bundled.outputFiles[0].text).toString("base64")
);
function fixture() {
  const e = database(),
    values = new Map();
  let alarm = null;
  const browsers = [];
  const ctx = {
    storage: {
      async get(k) {
        return structuredClone(values.get(k));
      },
      async put(k, v) {
        values.set(k, structuredClone(v));
      },
      async delete(k) {
        values.delete(k);
      },
      async setAlarm(t) {
        alarm = t;
      },
      async deleteAlarm() {
        alarm = null;
      },
    },
  };
  globalThis.__transport = {
    async launch() {
      const browser = {
        connected: true,
        contextsList: [],
        isConnected() {
          return this.connected;
        },
        sessionId() {
          return "session-" + browsers.indexOf(this);
        },
        contexts() {
          return this.contextsList;
        },
        async close() {
          this.connected = false;
        },
        async newBrowserCDPSession() {
          return {
            send: async () => {
              browser.connected = false;
            },
          };
        },
        async newContext(options) {
          const page = {
            currentUrl: "",
            url() {
              return this.currentUrl;
            },
            setDefaultTimeout() {},
            setDefaultNavigationTimeout() {},
            async goto(u) {
              this.currentUrl = u;
            },
            async waitForTimeout() {},
            mouse: { async wheel() {} },
            locator(s) {
              if (s.startsWith("div.feed"))
                return {
                  async count() {
                    return 1;
                  },
                  nth() {
                    return {
                      locator() {
                        return {
                          first() {
                            return {
                              async isVisible() {
                                return false;
                              },
                            };
                          },
                        };
                      },
                      async evaluate() {
                        return {
                          url: "https://www.linkedin.com/feed/update/urn:li:activity:123/",
                          text: "Vaga React remoto. Experiência em desenvolvimento de aplicações com React e Node.js. Envie sua candidatura pelo link do anúncio.",
                        };
                      },
                    };
                  },
                };
              return {
                async count() {
                  return s.startsWith("input") ? 0 : 1;
                },
              };
            },
          };
          const context = {
            options,
            pages() {
              return [page];
            },
            async newPage() {
              return page;
            },
            async storageState() {
              return {
                cookies: [{ name: "li_at", value: "PRIVATE_SESSION" }],
                origins: [],
              };
            },
            async newCDPSession() {
              return {
                async send() {
                  return {
                    devtoolsFrontendUrl:
                      "https://live.browser.run/ui/view?jwt=PRIVATE_LINK",
                  };
                },
              };
            },
          };
          browser.contextsList.push(context);
          return context;
        },
      };
      browsers.push(browser);
      return browser;
    },
    async connect(binding, id) {
      return browsers.find((b) => b.sessionId() === id);
    },
  };
  const env = { ...e, LINKEDIN_SESSION_KEY: secret, BROWSER: {} };
  return {
    e,
    ctx,
    env,
    values,
    browsers,
    get alarm() {
      return alarm;
    },
    obj: new LinkedInCloud(ctx, env),
  };
}
const request = (obj, action) =>
  obj.fetch(
    new Request("https://internal/" + action, {
      method: action === "status" ? "GET" : "POST",
    }),
  );
test("remote login survives coordinator restart, restores encrypted state and gates scheduling on a real extraction", async () => {
  const f = fixture();
  try {
    assert.equal((await request(f.obj, "enable")).status, 400);
    const login = await (await request(f.obj, "login")).json();
    assert.match(login.liveUrl, /live.browser.run/);
    assert.ok(f.alarm);
    assert.equal((await request(f.obj, "confirm")).status, 400);
    f.browsers[0].contexts()[0].pages()[0].currentUrl =
      "https://www.linkedin.com/feed/";
    f.obj = new LinkedInCloud(f.ctx, f.env);
    assert.equal((await request(f.obj, "confirm")).status, 200);
    assert.equal(f.browsers[0].connected, false);
    assert.ok(!JSON.stringify([...f.values]).includes("PRIVATE_SESSION"));
    assert.ok(
      !JSON.stringify(await (await request(f.obj, "status")).json()).includes(
        "PRIVATE_LINK",
      ),
    );
    assert.equal((await request(f.obj, "enable")).status, 400);
    const result = await (await request(f.obj, "collect")).json();
    assert.equal(result.state, "verified");
    assert.equal(result.saved, 1);
    assert.equal(
      f.browsers[1].contexts()[0].options.storageState.cookies[0].value,
      "PRIVATE_SESSION",
    );
    assert.equal(f.browsers[1].connected, false);
    assert.equal(f.alarm, null);
    assert.equal((await request(f.obj, "enable")).status, 200);
    await request(f.obj, "disconnect");
    assert.equal(f.values.has("session"), false);
  } finally {
    f.e.db.close();
  }
});
test("alarm closes abandoned login and transport errors never disclose debugger credentials", async () => {
  const f = fixture();
  try {
    await request(f.obj, "login");
    await f.obj.update({ expiresAt: 1 });
    f.obj = new LinkedInCloud(f.ctx, f.env);
    await f.obj.alarm();
    assert.equal(f.browsers[0].connected, false);
    assert.equal((await f.obj.status()).state, "login_expired");
    globalThis.__transport.launch = async () => {
      throw new Error("jwt=PRIVATE_LINK cookie=PRIVATE_SESSION");
    };
    const response = await request(f.obj, "login");
    assert.equal(response.status, 400);
    assert.ok(!(await response.text()).includes("PRIVATE_"));
  } finally {
    f.e.db.close();
  }
});
