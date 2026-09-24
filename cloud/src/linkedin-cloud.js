import { launch, connect } from "@cloudflare/playwright";
import {
  sessionKeyReady,
  sealSession,
  openSession,
  linkedinQuery,
  canonicalCloudPost,
  reserveBrowserSeconds,
} from "./linkedin-cloud-core.js";
import { profile, settings, event, lock, unlock } from "./db.js";
import { saveJobs } from "./discovery.js";
import { linkedinJob } from "./linkedin.js";

const reply = (value, status = 200) =>
  Response.json(value, { status, headers: { "Cache-Control": "no-store" } });
class UserError extends Error {}
export function cloudLinkedin(env, action) {
  if (env.USER_LINKEDIN) return env.USER_LINKEDIN(action);
  if (!env.LINKEDIN_CLOUD)
    throw new Error("Publique a configuração do navegador LinkedIn.");
  return env.LINKEDIN_CLOUD.get(env.LINKEDIN_CLOUD.idFromName("owner")).fetch(
    `https://internal/${action}`,
    { method: action === "status" ? "GET" : "POST" },
  );
}
async function authenticated(page) {
  const u = new URL(page.url());
  if (
    !["www.linkedin.com", "linkedin.com"].includes(u.hostname) ||
    !/^\/(feed|search)\//.test(u.pathname)
  )
    throw new UserError(
      "Abra o feed após entrar no LinkedIn. Login ou verificação pendente.",
    );
  if (
    await page
      .locator(
        'input[name="session_key"]:visible,input[type="password"]:visible,iframe[src*="captcha"]:visible',
      )
      .count()
  )
    throw new UserError("LinkedIn exige login ou verificação manual.");
  // Positive authenticated UI evidence; absence is not treated as a valid session.
  if (
    !(await page
      .locator(
        'a[href*="/mynetwork"],a[href*="/messaging"],button.global-nav__primary-link-me-menu-trigger',
      )
      .count())
  )
    throw new UserError(
      "Não foi possível confirmar a sessão. Verifique o navegador remoto ou o layout do LinkedIn.",
    );
}
export class LinkedInCloud {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.busy = false;
    this.browser = null;
  }
  async meta() {
    return (await this.ctx.storage.get("meta")) || {};
  }
  async update(fields) {
    const m = { ...(await this.meta()), ...fields };
    await this.ctx.storage.put("meta", m);
    return m;
  }
  async status() {
    const m = await this.meta();
    return {
      configured: sessionKeyReady(this.env.LINKEDIN_SESSION_KEY),
      state: m.state || "disconnected",
      expiresAt: m.expiresAt || null,
      verifiedAt: m.verifiedAt || null,
      lastRun: m.lastRun || null,
      saved: m.saved ?? null,
      automatic: !!m.automatic,
    };
  }
  async attach() {
    if (this.browser?.isConnected()) return this.browser;
    const m = await this.meta();
    if (!m.sessionId)
      throw new UserError("Sessão remota encerrada. Conecte novamente.");
    this.browser = await connect(this.env.BROWSER, m.sessionId);
    return this.browser;
  }
  async stop() {
    const m = await this.meta();
    if (m.sessionId) {
      try {
        const b = await this.attach();
        const cdp = await b.newBrowserCDPSession();
        await cdp.send("Browser.close").catch(() => {});
        await b.close().catch(() => {});
      } catch {
        /* Already expired/disconnected; provider idle timeout also applies. */
      }
    }
    this.browser = null;
    await this.update({ sessionId: null, expiresAt: null });
    await this.ctx.storage.deleteAlarm();
  }
  async alarm() {
    const m = await this.meta();
    if (m.expiresAt && Date.now() < m.expiresAt) {
      await this.ctx.storage.setAlarm(m.expiresAt);
      return;
    }
    await this.stop();
    if (m.state === "connecting" || m.state === "running")
      await this.update({
        state: m.state === "connecting" ? "login_expired" : "interrupted",
        automatic: false,
      });
  }
  async begin(seconds) {
    if (!(await reserveBrowserSeconds(this.env, seconds + 60)))
      throw new UserError(
        "Cota diária compartilhada de navegador atingida. Tente no próximo dia UTC.",
      );
    const expiresAt = Date.now() + seconds * 1000;
    await this.update({ expiresAt });
    await this.ctx.storage.setAlarm(expiresAt);
    this.browser = await launch(this.env.BROWSER, { keep_alive: 60000 });
    await this.update({ sessionId: this.browser.sessionId() });
    return this.browser;
  }
  async login() {
    const m = await this.meta();
    if (m.sessionId)
      throw new UserError(
        "Já há uma sessão aberta. Confirme ou cancele antes de conectar novamente.",
      );
    await this.update({
      state: "connecting",
      automatic: false,
      verifiedAt: null,
    });
    try {
      const browser = await this.begin(180);
      const context = await browser.newContext();
      const page = await context.newPage();
      page.setDefaultNavigationTimeout(20000);
      await page.goto("https://www.linkedin.com/login", {
        waitUntil: "domcontentloaded",
      });
      const cdp = await context.newCDPSession(page);
      const { devtoolsFrontendUrl } = await cdp.send("Cloudflare.getLiveView", {
        mode: "tab",
        expiresInMs: 180000,
      });
      const u = new URL(devtoolsFrontendUrl);
      if (u.protocol !== "https:" || u.hostname !== "live.browser.run")
        throw new Error("Unexpected Live View origin");
      // Only this authenticated response exposes the short-lived URL; never persist or log it.
      return { liveUrl: u.href, ...(await this.status()) };
    } catch (e) {
      await this.stop();
      await this.update({ state: "error" });
      throw e;
    }
  }
  async confirm() {
    const m = await this.meta();
    if (m.state !== "connecting" || !m.expiresAt || Date.now() >= m.expiresAt)
      throw new UserError("Tempo de login encerrado. Conecte novamente.");
    const browser = await this.attach();
    let selected;
    for (const context of browser.contexts())
      for (const page of context.pages()) {
        if (/^https:\/\/(www\.)?linkedin.com\/feed\//.test(page.url()))
          selected = { context, page };
      }
    if (!selected)
      throw new UserError(
        "No navegador remoto, termine o login e abra o feed antes de confirmar.",
      );
    await authenticated(selected.page);
    const encrypted = await sealSession(
      await selected.context.storageState({ indexedDB: true }),
      this.env.LINKEDIN_SESSION_KEY,
    );
    if (Date.now() >= m.expiresAt)
      throw new UserError("Tempo de login encerrado. Conecte novamente.");
    await this.ctx.storage.put("session", encrypted);
    await this.update({ state: "saved", verifiedAt: null, automatic: false });
    await this.stop();
    await event(
      this.env,
      "linkedin_cloud",
      "Sessão salva criptografada. Execute a coleta de teste para validar a restauração.",
    );
    return await this.status();
  }
  async collect() {
    const m = await this.meta();
    if (m.sessionId)
      throw new UserError("Conclua o login remoto antes da coleta.");
    const encrypted = await this.ctx.storage.get("session");
    if (!encrypted) throw new UserError("Conecte o LinkedIn primeiro.");
    const config = await settings(this.env),
      p = await profile(this.env);
    if (!p?.confirmed)
      throw new UserError("Confirme seu currículo antes da coleta.");
    const query = linkedinQuery(config, m.cursor || 0);
    const lease = await lock(this.env, "pipeline");
    if (!lease)
      throw new UserError("Aguarde o lote em andamento e tente novamente.");
    let timer;
    try {
      const storageState = await openSession(
        encrypted,
        this.env.LINKEDIN_SESSION_KEY,
      );
      const browser = await this.begin(45);
      await this.update({ state: "running" });
      const deadline = Date.now() + 40000;
      timer = setTimeout(() => this.stop().catch(() => {}), 45000);
      const context = await browser.newContext({ storageState });
      const page = await context.newPage();
      page.setDefaultTimeout(3000);
      page.setDefaultNavigationTimeout(15000);
      await page.goto(
        "https://www.linkedin.com/search/results/content/?" +
          new URLSearchParams({
            keywords: query.text,
            sortBy: '"date_posted"',
          }),
        { waitUntil: "domcontentloaded" },
      );
      await page.waitForTimeout(2000);
      await authenticated(page);
      const jobs = new Map();
      for (
        let scroll = 0;
        scroll < 4 && Date.now() < deadline && jobs.size < 20;
        scroll++
      ) {
        await authenticated(page);
        const cards = page.locator(
          'div.feed-shared-update-v2,div[data-urn*="activity"],div[role="listitem"][componentkey]',
        );
        for (
          let i = 0;
          i < Math.min(await cards.count(), 40) &&
          Date.now() < deadline &&
          jobs.size < 20;
          i++
        ) {
          const card = cards.nth(i);
          const more = card
            .locator(
              '[data-testid="expandable-text-button"],.feed-shared-inline-show-more-text__button',
            )
            .first();
          if (await more.isVisible())
            await more.click({ timeout: 1000 }).catch(() => {});
          const raw = await card.evaluate((el) => {
            const box = el.querySelector(
              '[data-testid="expandable-text-box"],.update-components-text,.feed-shared-text,.feed-shared-update-v2__description',
            );
            const a = el.querySelector(
              'a[href*="/feed/update/"],a[href*="/posts/"]',
            );
            const urn =
              el.getAttribute("data-urn") ||
              el.getAttribute("data-occludable-update-urn") ||
              "";
            return {
              text: box?.innerText || "",
              url:
                a?.href ||
                (urn.includes("urn:li:activity:")
                  ? `https://www.linkedin.com/feed/update/${urn}/`
                  : ""),
            };
          });
          const url = canonicalCloudPost(raw.url),
            text = raw.text.trim();
          if (
            url &&
            text.length >= 80 &&
            text.length <= 20000 &&
            !/(…|\.\.\.)$/.test(text)
          )
            jobs.set(url, linkedinJob({ url }, text));
        }
        await page.mouse.wheel(0, 1100);
        await page.waitForTimeout(700);
      }
      // Persist only after authenticated search; an expired login must not replace good state.
      await authenticated(page);
      await this.ctx.storage.put(
        "session",
        await sealSession(
          await context.storageState({ indexedDB: true }),
          this.env.LINKEDIN_SESSION_KEY,
        ),
      );
      const stats = {};
      const saved = await saveJobs(
        this.env,
        { id: "linkedin-cloud", kind: "linkedin", value: "busca autenticada" },
        config,
        [...jobs.values()],
        stats,
      );
      const verified = jobs.size > 0;
      await this.update({
        state: verified ? "verified" : "no_results",
        verifiedAt: verified ? new Date().toISOString() : m.verifiedAt || null,
        lastRun: new Date().toISOString(),
        saved,
        cursor: query.next,
        automatic: verified ? !!m.automatic : false,
      });
      await event(
        this.env,
        "linkedin_cloud",
        verified
          ? `Sessão restaurada e busca validada: ${jobs.size} posts legíveis, ${saved} novos.`
          : "Sessão restaurada, mas nenhum post legível. Verifique filtros e layout; agendamento LinkedIn pausado.",
      );
      return { ...(await this.status()), stats };
    } catch (e) {
      await this.update({
        state: e instanceof UserError ? "needs_login" : "error",
        automatic: false,
      });
      await event(
        this.env,
        "linkedin_cloud",
        "Coleta interrompida. Verifique a sessão e os limites; agendamento LinkedIn pausado.",
      );
      throw e;
    } finally {
      clearTimeout(timer);
      await this.stop();
      await unlock(this.env, "pipeline", lease);
    }
  }
  async fetch(req) {
    const action = new URL(req.url).pathname.slice(1);
    if (action === "status") return reply(await this.status());
    if (this.busy)
      return reply({ error: "Operação LinkedIn em andamento." }, 409);
    this.busy = true;
    try {
      if (
        ![
          "login",
          "confirm",
          "collect",
          "disconnect",
          "cancel",
          "enable",
          "disable",
          "scheduled",
        ].includes(action)
      )
        return reply({ error: "Ação inválida." }, 404);
      if (action === "disconnect") {
        await this.stop();
        await this.ctx.storage.delete("session");
        await this.update({
          state: "disconnected",
          verifiedAt: null,
          automatic: false,
        });
        return reply(await this.status());
      }
      if (action === "cancel") {
        await this.stop();
        await this.update({ state: "cancelled", automatic: false });
        return reply(await this.status());
      }
      if (action === "disable") {
        await this.update({ automatic: false });
        return reply(await this.status());
      }
      if (!sessionKeyReady(this.env.LINKEDIN_SESSION_KEY))
        throw new UserError(
          "Configure LINKEDIN_SESSION_KEY no Worker antes de conectar.",
        );
      if (action === "enable") {
        const m = await this.meta();
        if (m.state !== "verified" || !m.verifiedAt)
          throw new UserError(
            "Execute uma coleta de teste com posts legíveis antes de ativar.",
          );
        await this.update({ automatic: true });
        return reply(await this.status());
      }
      if (action === "scheduled") {
        const m = await this.meta(),
          config = await settings(this.env);
        if (!m.automatic || !config.enabled || m.sessionId)
          return reply({ skipped: true });
        // Daily cap exhaustion must not disable the user's opt-in.
        const used = await this.env.DB.prepare(
          "SELECT count FROM usage WHERE day=date('now') AND kind='browser_seconds'",
        ).first();
        if ((used?.count || 0) > 435) return reply({ skipped: true });
        return reply(await this.collect());
      }
      return reply(await this[action]());
    } catch (e) {
      // Playwright exceptions may include page content or credential-bearing debugger URLs.
      return reply(
        {
          error:
            e instanceof UserError
              ? e.message
              : "Falha no navegador remoto. Verifique o acesso do LinkedIn, a cota Browser Run e tente reconectar.",
        },
        400,
      );
    } finally {
      this.busy = false;
    }
  }
}
