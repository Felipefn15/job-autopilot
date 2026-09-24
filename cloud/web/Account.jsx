import React, { useState } from "react";
export function AuthScreen({ api, onAuthenticated, onAdmin }) {
  const [mode, setMode] = useState("login"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const change = (next) => {
    setMode(next);
    setError("");
  };
  return (
    <main className="auth-layout">
      <section className="auth-story">
        <div className="brand">
          <span className="mark">JA</span>
          <strong>Job Autopilot</strong>
        </div>
        <svg className="auth-art" viewBox="0 0 320 190" aria-hidden="true">
          <rect x="25" y="25" width="180" height="135" rx="18" fill="#20394a" />
          <rect x="48" y="48" width="50" height="50" rx="12" fill="#8ee1d0" />
          <path
            d="M117 53h63M117 72h45M48 117h131M48 135h94"
            stroke="#a7c0cb"
            strokeWidth="8"
            strokeLinecap="round"
          />
          <circle cx="244" cy="118" r="49" fill="#8ee1d0" />
          <path
            d="m222 119 15 15 30-33"
            stroke="#12695e"
            strokeWidth="9"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <h1>Seu próximo passo começa com você.</h1>
        <p>
          Transforme sua experiência em uma busca de oportunidades com mais
          contexto.
        </p>
        <ol>
          <li>Cadastre seu currículo</li>
          <li>Confirme seu perfil e preferências</li>
          <li>Acompanhe vagas e recomendações</li>
        </ol>
      </section>
      <section className="auth-form-panel">
        <span className="eyebrow">SUA ÁREA PESSOAL</span>
        <h2>
          {mode === "register"
            ? "Crie sua conta"
            : mode === "recover"
              ? "Recupere seu acesso"
              : "Bem-vindo de volta"}
        </h2>
        <p>
          {mode === "register"
            ? "Seu currículo e histórico ficam na sua conta."
            : mode === "recover"
              ? "Use o código de recuperação recebido ao criar sua conta."
              : "Entre para continuar sua busca."}
        </p>
        <form
          key={mode}
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const values = Object.fromEntries(new FormData(e.currentTarget));
            if (
              mode !== "login" &&
              values.password !== values.confirmPassword
            ) {
              setError("As senhas precisam ser iguais.");
              setBusy(false);
              return;
            }
            delete values.confirmPassword;
            try {
              const result = await api("auth/" + mode, "POST", values);
              await onAuthenticated(result);
            } catch (err) {
              setError(err.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {mode === "register" && (
            <label>
              Seu nome
              <input
                name="name"
                autoComplete="name"
                minLength={2}
                maxLength={80}
                required
              />
            </label>
          )}
          <label>
            E-mail
            <input
              name="email"
              type="email"
              autoComplete="username"
              maxLength={254}
              required
            />
          </label>
          {mode === "recover" && (
            <label>
              Código de recuperação
              <input
                name="recoveryCode"
                autoComplete="off"
                maxLength={100}
                required
              />
            </label>
          )}
          <label>
            {mode === "recover" ? "Nova senha" : "Senha"}
            <input
              name="password"
              type="password"
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              minLength={12}
              maxLength={128}
              required
            />
            <small>Pelo menos 12 caracteres.</small>
          </label>
          {mode !== "login" && (
            <label>
              Confirme a senha
              <input
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                required
              />
            </label>
          )}
          <button disabled={busy}>
            {busy
              ? "Aguarde…"
              : mode === "register"
                ? "Criar conta e continuar"
                : mode === "recover"
                  ? "Definir nova senha"
                  : "Entrar"}
          </button>
        </form>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="auth-links">
          <button
            disabled={busy}
            className="text-button"
            onClick={() => change(mode === "register" ? "login" : "register")}
          >
            {mode === "register" ? "Já tenho uma conta" : "Criar uma conta"}
          </button>
          <button
            disabled={busy}
            className="text-button"
            onClick={() => change(mode === "recover" ? "login" : "recover")}
          >
            {mode === "recover" ? "Voltar ao login" : "Esqueci minha senha"}
          </button>
        </div>
        <details className="legacy-access">
          <summary>Acessar painel anterior</summary>
          <p>
            Para o responsável pela instalação, usando a chave de acesso
            existente.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onAdmin(adminKey);
              setAdminKey("");
            }}
          >
            <label>
              Chave administrativa
              <input
                type="password"
                value={adminKey}
                onChange={(e) => setAdminKey(e.target.value)}
                minLength={32}
                required
                autoComplete="off"
              />
            </label>
            <button disabled={busy}>Abrir painel anterior</button>
          </form>
        </details>
      </section>
    </main>
  );
}
export function AccountSettings({ user, api, onRecovery, onLogout }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <section className="panel account-panel">
      <h2>Minha conta</h2>
      <button className="secondary" disabled={busy} onClick={onLogout}>
        Sair da conta
      </button>
      <p>{user.name}</p>
      <p>{user.email}</p>
      <h3>Alterar senha</h3>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const values = Object.fromEntries(new FormData(form));
          setError("");
          if (values.password !== values.confirmPassword) {
            setError("As senhas precisam ser iguais.");
            return;
          }
          delete values.confirmPassword;
          setBusy(true);
          try {
            const result = await api("auth/password", "POST", values);
            form.reset();
            onRecovery(result.recoveryCode);
          } catch (err) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Senha atual
          <input
            name="currentPassword"
            type="password"
            autoComplete="current-password"
            maxLength={128}
            required
          />
        </label>
        <label>
          Nova senha
          <input
            name="password"
            type="password"
            autoComplete="new-password"
            minLength={12}
            maxLength={128}
            required
          />
        </label>
        <label>
          Confirme a nova senha
          <input
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            minLength={12}
            maxLength={128}
            required
          />
        </label>
        <button disabled={busy}>
          {busy ? "Salvando…" : "Atualizar senha"}
        </button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p className="footnote">
        Ao alterar sua senha, as outras sessões são encerradas e um novo código
        de recuperação é gerado.
      </p>
    </section>
  );
}
