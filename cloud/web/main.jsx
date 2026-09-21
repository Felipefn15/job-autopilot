import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { countryOptions, countrySelection } from "./countries.js";
const labels = {
  discovered: "Encontrada",
  matched: "Compatível",
  rejected: "Descartada",
  needs_input: "Sua atenção",
  preparing: "Preparando",
  sending: "Enviando",
  submitted: "Enviada",
  unknown: "Verificar envio",
};
function App() {
  const [token, setToken] = useState(""),
    [input, setInput] = useState(""),
    [data, setData] = useState(null),
    [tab, setTab] = useState("overview"),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState(null),
    [filter, setFilter] = useState("all");
  async function api(path, method = "GET", body) {
    const r = await fetch("/api/" + path, {
      method,
      headers: {
        Authorization: "Bearer " + token,
        ...(body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
      },
      body:
        body === undefined
          ? undefined
          : body instanceof FormData
            ? body
            : JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) throw Error(j.error || "Falha na operação.");
    return j;
  }
  async function refresh() {
    setData(await api("state"));
  }
  async function act(fn, message) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      await refresh();
      if (message) setNotice(message);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (token)
      refresh().catch((e) => {
        setError(e.message);
        setToken("");
      });
  }, [token]);
  if (!data)
    return (
      <main className="login">
        <div className="mark">JA</div>
        <h1>Job Autopilot</h1>
        <p>Seu currículo. Oportunidades com contexto.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError("");
            setToken(input);
            setInput("");
          }}
        >
          <label>
            Chave de acesso privada
            <input
              type="password"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              autoComplete="current-password"
              required
              minLength={32}
            />
          </label>
          <button>Entrar no painel</button>
        </form>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <small>
          A chave permanece apenas nesta aba. Configure APP_TOKEN na hospedagem
          para o primeiro acesso.
        </small>
      </main>
    );
  const jobs = data.jobs,
    counts = Object.fromEntries(
      ["discovered", "matched", "submitted", "needs_input", "unknown"].map(
        (s) => [s, jobs.filter((j) => j.status === s).length],
      ),
    );
  const nav = [
    ["overview", "Visão geral"],
    ["profile", "Currículo e preferências"],
    ["sources", "Fontes"],
    ["history", "Atividade"],
  ];
  const current = jobs.find((j) => j.id === selected);
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="#" onClick={() => setTab("overview")}>
          <span className="mark">JA</span>
          <span>
            Job
            <br />
            <strong>Autopilot</strong>
          </span>
        </a>
        <nav>
          {nav.map(([id, label]) => (
            <button
              className={tab === id ? "active" : ""}
              key={id}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="pill">PLANO GRATUITO</span>
          <p>Até 3 tentativas de candidatura por dia.</p>
          <button
            className="quiet"
            onClick={() => {
              setToken("");
              setData(null);
            }}
          >
            Sair
          </button>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <span className="eyebrow">SEU PRÓXIMO PASSO</span>
            <h1>{nav.find((n) => n[0] === tab)[1]}</h1>
          </div>
          <button
            disabled={busy || !data.profile?.confirmed}
            onClick={() =>
              act(
                () => api("run", "POST", {}),
                "Lote concluído. Veja os resultados e a atividade.",
              )
            }
          >
            <span>{busy ? "Processando…" : "Executar um lote"}</span>
          </button>
        </header>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            {notice}
          </div>
        )}
        {(!data.capabilities.ai || !data.profile?.confirmed) && (
          <section className="setup">
            <strong>
              {!data.capabilities.ai
                ? "Conecte a análise de IA"
                : "Seu currículo precisa de revisão"}
            </strong>
            <p>
              {!data.capabilities.ai
                ? "Configure GEMINI_API_KEY na hospedagem para extrair e analisar seu currículo."
                : "Envie o PDF e confirme se os dados extraídos estão corretos antes de iniciar."}
            </p>
            <button className="secondary" onClick={() => setTab("profile")}>
              Abrir currículo
            </button>
          </section>
        )}
        {tab === "overview" && (
          <>
            <div className="stats">
              {[
                ["Encontradas", counts.discovered],
                ["Compatíveis", counts.matched],
                ["Enviadas", counts.submitted],
                ["Sua atenção", counts.needs_input + counts.unknown],
              ].map(([label, value]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </article>
              ))}
            </div>
            <div className="section-heading">
              <h2>Oportunidades</h2>
              <select
                aria-label="Filtrar status"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">Todos os status</option>
                {Object.entries(labels).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <section className="job-list">
              {jobs
                .filter((j) => filter === "all" || j.status === filter)
                .map((j) => (
                  <button
                    className="job"
                    key={j.id}
                    onClick={() => setSelected(j.id)}
                  >
                    <div className="company-avatar">
                      {j.company.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="job-title">
                      <strong>{j.title}</strong>
                      <span>
                        {j.company} · {j.location}
                      </span>
                    </div>
                    <span className={"status " + j.status}>
                      {labels[j.status]}
                    </span>
                    <strong className="score">
                      {j.score === null ? "—" : j.score}
                      <small>{j.score === null ? "" : "/100"}</small>
                    </strong>
                  </button>
                ))}
              {!jobs.length && (
                <div className="empty">
                  <div className="empty-icon">↗</div>
                  <h2>Comece pelo seu currículo</h2>
                  <p>
                    Confirme seu perfil, adicione fontes de vagas e execute o
                    primeiro lote. As oportunidades aparecerão aqui com os
                    motivos da compatibilidade.
                  </p>
                  <button
                    className="secondary"
                    onClick={() =>
                      setTab(data.profile?.confirmed ? "sources" : "profile")
                    }
                  >
                    {data.profile?.confirmed
                      ? "Adicionar fontes"
                      : "Enviar currículo"}
                  </button>
                </div>
              )}
            </section>
            <p className="footnote">
              Mostrando as 200 oportunidades mais recentes. Uma pontuação indica
              compatibilidade, não probabilidade de contratação.
            </p>
            <section className="quota">
              <h2>Uso de hoje</h2>
              <div>
                {[
                  ["ai", "Análises e etapas de IA", 30],
                  ["applications", "Tentativas de candidatura", 3],
                  ["browser", "Sessões de navegador", 3],
                ].map(([key, name, limit]) => (
                  <p key={key}>
                    <span>{name}</span>
                    <strong>
                      {data.usage.find((u) => u.kind === key)?.count || 0} /{" "}
                      {limit}
                    </strong>
                  </p>
                ))}
              </div>
            </section>
          </>
        )}
        {tab === "profile" && (
          <Profile data={data} api={api} act={act} busy={busy} />
        )}
        {tab === "sources" && (
          <Sources data={data} api={api} act={act} busy={busy} />
        )}
        {tab === "history" && (
          <section className="events">
            {data.events.map((e) => (
              <article key={e.id}>
                <time>
                  {new Date(e.created_at + "Z").toLocaleString("pt-BR")}
                </time>
                <p>{e.detail}</p>
                <small>{e.kind}</small>
              </article>
            ))}
            {!data.events.length && (
              <p className="empty">Nenhuma atividade registrada.</p>
            )}
          </section>
        )}
        <footer>
          <span>Job Autopilot · acesso privado</span>
          <span>
            {data.config.enabled
              ? "Coleta agendada ativa"
              : "Coleta agendada pausada"}{" "}
            ·{" "}
            {data.config.autoApply ? "Envio automático ativo" : "Envio manual"}
          </span>
        </footer>
      </main>
      {current && (
        <div className="overlay" onClick={() => setSelected(null)}>
          <section
            className="detail"
            role="dialog"
            aria-modal="true"
            aria-label="Detalhes da vaga"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="close quiet" onClick={() => setSelected(null)}>
              Fechar ×
            </button>
            <span className={"status " + current.status}>
              {labels[current.status]}
            </span>
            <h2>{current.title}</h2>
            <p>
              {current.company} · {current.location}
            </p>
            <a href={current.url} target="_blank" rel="noreferrer">
              Abrir vaga original ↗
            </a>
            {current.analysis && (
              <Analysis value={JSON.parse(current.analysis)} />
            )}{" "}
            {current.draft && (
              <>
                <h3>E-mail preparado</h3>
                <strong>{JSON.parse(current.draft).subject}</strong>
                <pre>{JSON.parse(current.draft).body}</pre>
              </>
            )}
            {current.proof && (
              <>
                <h3>Registro da candidatura</h3>
                <pre>{current.proof}</pre>
              </>
            )}
            {current.status === "matched" && (
              <button
                disabled={busy}
                onClick={() =>
                  act(
                    () => api("apply", "POST", { id: current.id }),
                    "Processamento concluído. Confira o status da candidatura.",
                  )
                }
              >
                Enviar candidatura
              </button>
            )}
            {["unknown", "needs_input"].includes(current.status) && (
              <fieldset>
                <legend>Após verificar o site ou a pasta Enviados</legend>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    act(
                      () =>
                        api("job/reconcile", "POST", {
                          id: current.id,
                          status: "submitted",
                          confirmed: true,
                        }),
                      "Envio confirmado por você.",
                    )
                  }
                >
                  Verifiquei: já foi enviada
                </button>
                <button
                  className="quiet"
                  disabled={busy}
                  onClick={() =>
                    act(
                      () =>
                        api("job/reconcile", "POST", {
                          id: current.id,
                          status: "discovered",
                          confirmed: true,
                        }),
                      "Vaga devolvida para análise.",
                    )
                  }
                >
                  Verifiquei: não foi enviada
                </button>
              </fieldset>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function Analysis({ value: a }) {
  return (
    <>
      <h3>Por que esta vaga?</h3>
      <p>{a.reason}</p>
      <h3>Evidências do currículo</h3>
      {a.evidence.map((e, i) => (
        <blockquote key={i}>
          <p>“{e.resumeQuote}”</p>
          <small>Requisito: {e.jobQuote}</small>
        </blockquote>
      ))}
      {a.gaps.length > 0 && (
        <>
          <h3>Lacunas</h3>
          <ul>
            {a.gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </>
      )}
      {a.blockers.length > 0 && (
        <>
          <h3>Restrições</h3>
          <ul>
            {a.blockers.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
function ResumeProgress({ upload }) {
  const { stage, filename } = upload;
  const failed = stage === -1;
  const done = stage === 3;
  const steps = [
    "Validar arquivo PDF",
    "Enviar e analisar currículo",
    "Carregar dados para revisão",
  ];
  return (
    <section
      className={`resume-progress ${failed ? "failed" : done ? "complete" : ""}`}
      aria-label="Processamento do currículo"
      aria-busy={!failed && !done}
    >
      <div className="resume-progress-heading">
        <span
          className={`resume-progress-icon ${!failed && !done ? "spinning" : ""}`}
          aria-hidden="true"
        >
          {failed ? "!" : done ? "✓" : ""}
        </span>
        <div role="status" aria-live="polite">
          <h3>
            {failed
              ? "Não foi possível concluir"
              : done
                ? "Currículo pronto para revisão"
                : "Preparando seu currículo"}
          </h3>
          <p>
            {failed
              ? "Confira a mensagem de erro e tente novamente."
              : done
                ? "Revise os dados abaixo e confirme seu perfil."
                : steps[stage] + "…"}
          </p>
        </div>
      </div>
      <p className="resume-progress-file">{filename}</p>
      {!failed && (
        <ol className="resume-progress-steps">
          {steps.map((label, index) => (
            <li
              key={label}
              className={
                index < stage ? "done" : index === stage ? "current" : "pending"
              }
              aria-current={index === stage ? "step" : undefined}
            >
              <span aria-hidden="true">{index < stage ? "✓" : index + 1}</span>
              <div>
                {label}
                <small>
                  {index < stage
                    ? "Concluído"
                    : index === stage
                      ? "Em andamento"
                      : "Aguardando"}
                </small>
              </div>
            </li>
          ))}
        </ol>
      )}
      {!done && !failed && (
        <p className="resume-progress-note">
          A análise pode levar alguns instantes. Mantenha esta página aberta.
        </p>
      )}
    </section>
  );
}
function Profile({ data, api, act, busy }) {
  const [upload, setUpload] = useState(null);
  const [config, setConfig] = useState(data.config),
    [fields, setFields] = useState(data.profile?.data.fields || {}),
    [text, setText] = useState(data.profile?.data.text || "");
  useEffect(() => {
    setFields(data.profile?.data.fields || {});
    setText(data.profile?.data.text || "");
  }, [data.profile?.id]);
  useEffect(() => {
    setConfig((current) => ({ ...current, keywords: data.config.keywords }));
  }, [data.config.keywords, data.profile?.id]);
  const update = (key, value) => setConfig({ ...config, [key]: value });
  return (
    <div className="two-column">
      <section className="panel">
        <h2>Seu currículo</h2>
        <p>PDF de até 1 MB. Você revisa a extração antes de usar o perfil.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const file = e.target.elements.pdf.files[0];
            if (!file || busy) return;
            setUpload({ stage: 0, filename: file.name });
            const success = await act(async () => {
              if (file.size > 1024 * 1024)
                throw Error("Escolha um PDF de até 1 MB.");
              const signature = await file.slice(0, 5).text();
              if (signature !== "%PDF-")
                throw Error("O arquivo selecionado não é um PDF válido.");
              const f = new FormData();
              f.append("file", file);
              setUpload({ stage: 1, filename: file.name });
              await api("resume", "POST", f);
              setUpload({ stage: 2, filename: file.name });
            }, "PDF processado. Revise e confirme os dados.");
            setUpload({ stage: success ? 3 : -1, filename: file.name });
          }}
        >
          <input
            name="pdf"
            aria-label="Currículo PDF"
            type="file"
            accept="application/pdf"
            required
            disabled={busy}
            onChange={() => setUpload(null)}
          />
          <button disabled={busy || !data.capabilities.ai}>
            {upload && upload.stage >= 0 && upload.stage < 3
              ? "Processando currículo…"
              : "Processar PDF"}
          </button>
        </form>
        {upload && <ResumeProgress upload={upload} />}
        {data.profile && !(upload && upload.stage >= 0 && upload.stage < 3) && (
          <>
            <p className="filename">
              {data.profile.filename} ·{" "}
              {data.profile.confirmed
                ? "Perfil confirmado"
                : "Revisão pendente"}
            </p>
            {Object.entries({
              name: "Nome completo",
              firstName: "Primeiro nome",
              lastName: "Sobrenome",
              email: "E-mail",
              phone: "Telefone",
              location: "Localização",
              linkedin: "LinkedIn",
            }).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  value={fields[key] || ""}
                  onChange={(e) =>
                    setFields({ ...fields, [key]: e.target.value })
                  }
                />
              </label>
            ))}
            <label>
              Texto extraído
              <textarea
                rows={12}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <button
              disabled={busy}
              onClick={() =>
                act(
                  () =>
                    api("profile/confirm", "POST", {
                      id: data.profile.id,
                      fields,
                      text,
                    }),
                  "Perfil confirmado. Termos de busca atualizados com as tecnologias extraídas, quando disponíveis.",
                )
              }
            >
              Confirmar dados do currículo
            </button>
          </>
        )}
      </section>
      <section className="panel">
        <h2>Preferências de busca</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(
              () => api("settings", "PUT", config),
              "Preferências salvas. Vagas pendentes serão reavaliadas.",
            );
          }}
        >
          <label>
            País ou região de interesse
            <select
              value={countrySelection(config.country)}
              onChange={(e) => update("country", e.target.value)}
              required
            >
              <option value="global">Mundo / World</option>
              <option value="LATAM">América Latina (LATAM)</option>
              {![
                "global",
                "LATAM",
                ...countryOptions.map((c) => c.name),
              ].includes(countrySelection(config.country)) && (
                <option value={config.country}>
                  {config.country} (seleção anterior)
                </option>
              )}
              <optgroup label="Países e territórios">
                {countryOptions.map((c) => (
                  <option key={c.code} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          <label>
            Termos de busca, separados por vírgula
            <input
              value={config.keywords}
              onChange={(e) => update("keywords", e.target.value)}
              maxLength={500}
            />
            <small>
              Preenchidos ao confirmar o currículo. Você pode ajustar os termos
              antes de salvar as preferências.
            </small>
          </label>
          <label>
            Pontuação mínima
            <input
              type="number"
              min={60}
              max={100}
              value={config.minScore}
              onChange={(e) => update("minScore", Number(e.target.value))}
            />
          </label>
          <label>
            Candidaturas por dia
            <input
              type="number"
              min={1}
              max={3}
              value={config.dailyApplications}
              onChange={(e) =>
                update("dailyApplications", Number(e.target.value))
              }
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={config.remoteOnly}
              onChange={(e) => update("remoteOnly", e.target.checked)}
            />
            Somente trabalho remoto
          </label>
          <h3>Informações complementares</h3>
          {[
            ["workAuthorization", "Autorização de trabalho por país"],
            ["sponsorship", "Necessidade de visto/patrocínio"],
            ["salary", "Pretensão salarial e moeda"],
            ["availability", "Disponibilidade para começar"],
          ].map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={config.facts[key] || ""}
                onChange={(e) =>
                  update("facts", { ...config.facts, [key]: e.target.value })
                }
              />
            </label>
          ))}
          <p className="footnote">
            Informações ausentes geram pendências. A busca global não presume
            autorização para trabalhar em outros países.
          </p>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => update("enabled", e.target.checked)}
            />
            Executar a cada duas horas
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={config.autoApply}
              onChange={(e) => update("autoApply", e.target.checked)}
            />
            Enviar automaticamente vagas compatíveis
          </label>
          <button disabled={busy}>Salvar preferências</button>
        </form>
        <div className="connections">
          <h3>Conexões</h3>
          <p>
            IA{" "}
            <strong>{data.capabilities.ai ? "Configurada" : "Pendente"}</strong>
          </p>
          <p>
            Gmail{" "}
            <strong>
              {data.capabilities.email ? "Configurado" : "Pendente"}
            </strong>
          </p>
          <p>
            Navegador{" "}
            <strong>
              {data.capabilities.browser ? "Configurado" : "Pendente"}
            </strong>
          </p>
        </div>
      </section>
    </div>
  );
}
function Sources({ data, api, act, busy }) {
  const [kind, setKind] = useState("greenhouse"),
    [value, setValue] = useState(""),
    [bulk, setBulk] = useState("");
  function parseLine(line) {
    const u = new URL(line);
    let k = "page",
      v = u.href;
    if (
      u.hostname === "boards.greenhouse.io" ||
      u.hostname === "job-boards.greenhouse.io"
    ) {
      k = "greenhouse";
      v = u.pathname.split("/")[1];
    } else if (u.hostname === "jobs.lever.co") {
      k = "lever";
      v = u.pathname.split("/")[1];
    } else if (u.hostname === "jobs.ashbyhq.com") {
      k = "ashby";
      v = u.pathname.split("/")[1];
    }
    return { kind: k, value: v };
  }
  return (
    <>
      <section className="panel">
        <h2>Catálogo de fontes</h2>
        <p>
          Adicione páginas de empresas em plataformas de recrutamento ou páginas
          individuais de vagas com dados estruturados. O catálogo suporta até
          2.000 fontes; cada lote consulta uma fonte.
        </p>
        <form
          className="source-form"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await api("sources", "POST", { sources: [{ kind, value }] });
              setValue("");
            }, "Fonte adicionada.");
          }}
        >
          <label>
            Tipo
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="greenhouse">Greenhouse</option>
              <option value="lever">Lever</option>
              <option value="ashby">Ashby</option>
              <option value="page">Página de vaga</option>
            </select>
          </label>
          <label>
            {kind === "page" ? "URL HTTPS da vaga" : "Identificador da empresa"}
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={
                kind === "page"
                  ? "https://empresa.com/carreiras/vaga"
                  : "Identificador no endereço da plataforma"
              }
              required
            />
          </label>
          <button disabled={busy}>Adicionar</button>
        </form>
        <details>
          <summary>Importar várias páginas de carreira</summary>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                await api("sources", "POST", {
                  sources: bulk
                    .split("\n")
                    .map((s) => s.trim())
                    .filter(Boolean)
                    .map(parseLine),
                });
                setBulk("");
              }, "Fontes importadas.");
            }}
          >
            <label>
              Uma URL por linha, até 100 por importação
              <textarea
                rows={5}
                value={bulk}
                onChange={(e) => setBulk(e.target.value)}
                required
              />
            </label>
            <button disabled={busy}>Importar fontes</button>
          </form>
        </details>
      </section>
      <section className="panel source-list">
        {data.sources.map((s) => (
          <article key={s.id}>
            <div>
              <strong>{s.value}</strong>
              <p>
                {s.kind} ·{" "}
                {s.checked_at
                  ? "Última consulta: " + s.checked_at
                  : "Ainda não consultada"}
              </p>
              {s.error && <p className="error">{s.error}</p>}
            </div>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                act(() =>
                  api("source/toggle", "POST", {
                    id: s.id,
                    enabled: !s.enabled,
                  }),
                )
              }
            >
              {s.enabled ? "Pausar" : "Ativar"}
            </button>
          </article>
        ))}
        {!data.sources.length && <p>Nenhuma fonte cadastrada.</p>}
      </section>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
