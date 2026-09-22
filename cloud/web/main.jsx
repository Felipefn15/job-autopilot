import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { countryOptions, countrySelection } from "./countries.js";
const labels = {
  discovered: "Aguardando análise",
  filtered: "Fora das preferências",
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
    [filter, setFilter] = useState("active");
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
                ["Aguardando análise", counts.discovered],
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
                <option value="active">Em avaliação e candidaturas</option>
                <option value="all">Todos os status</option>
                {Object.entries(labels).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <section className="job-list">
              <p>
                “Aguardando análise” ainda não indica compatibilidade. A
                pontuação mínima é aplicada após a avaliação do currículo pela
                IA.
              </p>
              {jobs
                .filter(
                  (j) =>
                    filter === "all" ||
                    (filter === "active"
                      ? !["filtered", "rejected"].includes(j.status)
                      : j.status === filter),
                )
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
              antes de salvar as preferências. Termos genéricos como Scrum não
              bastam para selecionar qualquer cargo que os mencione.
            </small>
          </label>
          <label>
            Cargos de interesse, separados por vírgula
            <input
              value={config.targetRoles || ""}
              onChange={(e) => update("targetRoles", e.target.value)}
              maxLength={500}
              placeholder="Ex.: Scrum Master, Gerente de projetos, Project Manager"
            />
            <small>
              Opcional. O título precisa conter um dos cargos informados. Inclua
              variações em inglês quando desejar. As competências são avaliadas
              separadamente.
            </small>
          </label>
          <label>
            Prioridade das fontes
            <select
              value={config.sourceFocus || "brasil"}
              onChange={(e) => update("sourceFocus", e.target.value)}
            >
              <option value="brasil">Brasil primeiro</option>
              <option value="global">Todas as regiões por igual</option>
            </select>
            <small>
              A prioridade de coleta é independente do país escolhido para as
              vagas.
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
function LinkedInCloudPanel({ api, act, busy }) {
  const [state, setState] = useState(null),
    [liveUrl, setLiveUrl] = useState(""),
    [loadError, setLoadError] = useState("");
  const refresh = async () => setState(await api("linkedin/cloud/status"));
  useEffect(() => {
    refresh().catch((e) => setLoadError(e.message));
  }, []);
  const run = (action) =>
    act(async () => {
      try {
        const result = await api(`linkedin/cloud/${action}`, "POST");
        if (action === "login") setLiveUrl(result.liveUrl);
        else if (["confirm", "cancel", "disconnect"].includes(action))
          setLiveUrl("");
      } finally {
        await refresh();
      }
    });
  const names = {
    disconnected: "Desconectado",
    connecting: "Aguardando seu login",
    saved: "Sessão salva — teste a restauração",
    verified: "Busca validada em uma nova sessão",
    running: "Buscando posts",
    no_results: "Nenhum post legível — revise filtros e sessão",
    needs_login: "Reconexão necessária",
    error: "Falha no navegador remoto",
    login_expired: "Tempo de login encerrado",
    interrupted: "Coleta interrompida",
    cancelled: "Login cancelado",
  };
  return (
    <section className="panel">
      <h2>LinkedIn na Cloudflare</h2>
      <p>
        Entre no navegador remoto, salve a sessão e teste uma busca pelos termos
        do seu currículo. Após conectar, as buscas podem rodar com seu
        computador desligado.
      </p>
      {loadError && <p role="alert">{loadError}</p>}
      {state && (
        <>
          <p role="status">
            <strong>{names[state.state] || state.state}</strong>
          </p>
          {!state.configured && (
            <p>
              Configure o segredo LINKEDIN_SESSION_KEY conforme o guia de
              instalação para habilitar a conexão.
            </p>
          )}
          <p>
            O login tem até 3 minutos. A coleta usa até 45 segundos e
            compartilha a cota diária de navegador com as candidaturas.
          </p>
          {state.expiresAt && (
            <p>
              Sessão temporária até{" "}
              {new Date(state.expiresAt).toLocaleTimeString()}.
            </p>
          )}
          {liveUrl && state.state === "connecting" && (
            <p>
              <a
                href={liveUrl}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                Abrir navegador remoto e fazer login no LinkedIn
              </a>
            </p>
          )}
          <div className="actions">
            <button
              disabled={
                busy ||
                !state.configured ||
                state.state === "connecting" ||
                state.state === "running"
              }
              onClick={() => run("login")}
            >
              Conectar LinkedIn
            </button>
            {state.state === "connecting" && (
              <>
                <button disabled={busy} onClick={() => run("confirm")}>
                  Já entrei — salvar sessão
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => run("cancel")}
                >
                  Cancelar login
                </button>
              </>
            )}
            <button
              disabled={
                busy ||
                !state.configured ||
                !["saved", "verified", "no_results"].includes(state.state)
              }
              onClick={() => run("collect")}
            >
              Testar busca na nuvem
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => act(refresh)}
            >
              Atualizar estado
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => run("disconnect")}
            >
              Desconectar e apagar sessão
            </button>
          </div>
          {busy && (
            <p role="status">
              Processando… a coleta pode levar até 45 segundos.
            </p>
          )}
          {state.lastRun && (
            <p>
              Última coleta: {new Date(state.lastRun).toLocaleString()} ·{" "}
              {state.saved ?? 0} novos posts. Veja os detalhes em Atividade.
            </p>
          )}
          <p>
            Agendamento LinkedIn:{" "}
            <strong>{state.automatic ? "ativado" : "desativado"}</strong>.
            Também depende do agendamento geral em Preferências.
          </p>
          <button
            className="secondary"
            disabled={busy || (!state.automatic && state.state !== "verified")}
            onClick={() => run(state.automatic ? "disable" : "enable")}
          >
            {state.automatic
              ? "Pausar busca automática"
              : "Ativar busca automática após teste"}
          </button>
          <p>
            Se aparecer login, verificação ou bloqueio, a coleta para e pede sua
            atenção. Nenhuma candidatura é enviada por este teste.
          </p>
        </>
      )}
    </section>
  );
}
function Sources({ data, api, act, busy }) {
  const [post, setPost] = useState({ url: "", text: "", title: "" });
  const [sourceFilter, setSourceFilter] = useState("");
  const [region, setRegion] = useState("BR");
  const sourceLink = (s) =>
    (({
      greenhouse: "https://job-boards.greenhouse.io/",
      lever: "https://jobs.lever.co/",
      ashby: "https://jobs.ashbyhq.com/",
      github: "https://github.com/",
      telegram: "https://t.me/s/",
    })[s.kind] || "") + s.value;
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
    } else if (/^(www\.)?linkedin\.com$/.test(u.hostname)) {
      k = "linkedin";
    } else if (u.hostname === "github.com") {
      k = "github";
      v = u.pathname.split("/").filter(Boolean).slice(0, 2).join("/");
    } else if (u.hostname === "t.me") {
      k = "telegram";
      v = u.pathname
        .split("/")
        .filter(Boolean)
        .filter((s) => s !== "s")[0];
    }
    return { kind: k, value: v };
  }
  return (
    <>
      <LinkedInCloudPanel api={api} act={act} busy={busy} />
      <section className="panel">
        <h2>Catálogo de fontes</h2>
        <p>
          Adicione páginas de empresas em plataformas de recrutamento ou páginas
          individuais de vagas com dados estruturados. O catálogo suporta até
          2.000 fontes; cada lote consulta até cinco fontes, priorizando as
          brasileiras por padrão (até quatro brasileiras e uma global, conforme
          disponibilidade).
        </p>
        <p>
          <strong>{data.sources.length} fontes cadastradas</strong> ·{" "}
          {data.sources.filter((s) => s.enabled).length} ativas ·{" "}
          {data.sources.filter((s) => s.checked_at && !s.error).length}{" "}
          consultadas sem erro
        </p>
        <p>
          O catálogo inicial contém referências de carreira. A disponibilidade e
          as vagas são verificadas durante cada consulta; uma referência
          cadastrada não significa uma vaga compatível.
        </p>
        <label>
          Região das novas fontes
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="BR">Brasil</option>
            <option value="global">Global / outras regiões</option>
          </select>
        </label>
        <form
          className="source-form"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await api("sources", "POST", {
                sources: [{ kind, value }],
                region,
              });
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
              <option value="linkedin">Post público do LinkedIn</option>
              <option value="github">Comunidade GitHub</option>
              <option value="telegram">Canal público Telegram</option>
            </select>
          </label>
          <label>
            {["page", "linkedin"].includes(kind)
              ? "URL HTTPS"
              : kind === "github"
                ? "Organização/repositório"
                : kind === "telegram"
                  ? "Nome do canal público"
                  : "Identificador da empresa"}
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={
                ["page", "linkedin"].includes(kind)
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
                  region,
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
      <section className="panel">
        <h2>Busca LinkedIn com sessão autenticada</h2>
        <p>
          O coletor usa Chromium no seu computador, mantém a sessão local e
          envia os posts encontrados para este painel. Ele busca usando as
          tecnologias e a região das preferências.
        </p>
        <p>
          <strong>Último registro:</strong>{" "}
          {data.collector
            ? `${data.collector.detail} (${data.collector.created_at} UTC)`
            : "Nenhuma execução registrada."}
        </p>
        <p>
          O registro não confirma que o coletor continua conectado. O computador
          e o processo precisam permanecer ligados.
        </p>
        <a
          href="https://github.com/Felipefn15/job-autopilot/blob/main/collector/README.md"
          target="_blank"
          rel="noopener noreferrer"
        >
          Instalar ou reutilizar a sessão anterior
        </a>
        <p>
          <code>python linkedin_collector.py run</code> — uma coleta
        </p>
        <p>
          <code>python linkedin_collector.py watch</code> — coleta periódica,
          com agendamento habilitado nas preferências
        </p>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => act(async () => {})}
        >
          Atualizar registro do coletor
        </button>
      </section>
      <section className="panel">
        <h2>Importar post do LinkedIn</h2>
        <p>
          Cole a URL de um post com oportunidade. Tentaremos extrair o texto
          público. Se o LinkedIn pedir login ou bloquear a leitura, cole o texto
          integral abaixo. Não é necessário fornecer senha ou cookies.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            await act(async () => {
              const result = await api("linkedin/import", "POST", post);
              if (!result.saved) throw Error("Este post já foi importado.");
              setPost({ url: "", text: "", title: "" });
            }, "Post importado. A oportunidade entrou na fila de análise.");
          }}
        >
          <label>
            URL do post
            <input
              type="url"
              required
              value={post.url}
              onChange={(e) => setPost({ ...post, url: e.target.value })}
              placeholder="https://www.linkedin.com/posts/..."
            />
          </label>
          <label>
            Título da vaga (opcional)
            <input
              maxLength={300}
              value={post.title}
              onChange={(e) => setPost({ ...post, title: e.target.value })}
            />
          </label>
          <label>
            Texto integral do post (opcional quando a leitura pública funcionar)
            <textarea
              rows={6}
              maxLength={20000}
              value={post.text}
              onChange={(e) => setPost({ ...post, text: e.target.value })}
            />
          </label>
          <button disabled={busy}>Importar e colocar na fila</button>
        </form>
        <p>
          Posts com instruções explícitas de candidatura por e-mail seguem a
          análise normal. Candidaturas pelo LinkedIn ou links externos no post
          precisam de revisão manual.
        </p>
      </section>
      <section className="panel source-list">
        <label>
          Filtrar fontes
          <input
            type="search"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            placeholder="Empresa ou plataforma"
          />
        </label>
        {data.sources
          .filter((s) =>
            `${s.value} ${s.kind}`
              .toLowerCase()
              .includes(sourceFilter.toLowerCase()),
          )
          .map((s) => (
            <article key={s.id}>
              <div>
                <strong>{s.value}</strong>
                <p>
                  <a
                    href={sourceLink(s)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Abrir referência de carreira
                  </a>
                </p>
                <p>
                  {s.kind} · {s.region === "BR" ? "Brasil" : "Global"} ·{" "}
                  {s.checked_at
                    ? "Última consulta: " + s.checked_at
                    : "Ainda não consultada"}
                </p>
                {s.error && <p className="error">{s.error}</p>}
                {s.last_stats &&
                  (() => {
                    const m = JSON.parse(s.last_stats);
                    return (
                      <p>
                        {m.received} recebidas · {m.scanned} examinadas ·{" "}
                        {m.filtered} fora das preferências · {m.duplicates} já
                        cadastradas · <strong>{m.saved} novas</strong>
                      </p>
                    );
                  })()}
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
