import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const classes = [
  ["-2", "強い否定"],
  ["-1", "否定"],
  ["0", "中立"],
  ["1", "肯定"],
  ["2", "強い肯定"],
];
const names = { lora: "LoRA", full: "Full FT" };
const defaults = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "",
  cognitoClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || "",
  cognitoEndpoint: import.meta.env.VITE_COGNITO_ENDPOINT || "/auth",
};

async function predict(text, method, token, config) {
  const apiBase = config.apiBaseUrl.replace(/\/$/, "");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(`${apiBase}/predict/${method}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(
        response.status === 401
          ? "ログインし直してください。"
          : response.status === 403
            ? "権限がありません。"
            : response.status === 503
              ? "モデルを読み込めません。"
              : "分析に失敗しました。",
      );
      error.status = response.status;
      throw error;
    }
    return result;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("タイムアウトしました。");
    if (error instanceof TypeError) throw new Error("接続できません。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function Result({ method, result, error }) {
  const sentiment = result?.sentiment;
  return (
    <section className="result-card" aria-label={`${names[method]}の結果`}>
      <div className="card-heading">
        <h3>{names[method]}</h3>
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : result ? (
        <>
          <div className="prediction">
            <strong>
              {sentiment > 0 ? "+" : ""}
              {sentiment}
            </strong>
            <span>{classes.find(([id]) => Number(id) === sentiment)[1]}</span>
          </div>
          <div className="probabilities">
            {classes.map(([id, label]) => (
              <div
                className={`prob-row ${Number(id) === sentiment ? "selected" : ""}`}
                key={id}
              >
                <span>{label}</span>
                <div className="track">
                  <div
                    style={{ width: `${result.probabilities[id] * 100}%` }}
                  />
                </div>
                <span>{(result.probabilities[id] * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
          {result.truncated && (
            <p className="notice">512トークンで切り詰めました。</p>
          )}
        </>
      ) : (
        <p className="pending" role="status">
          分析中…
        </p>
      )}
    </section>
  );
}

function Login({ config, onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function signIn(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(config.cognitoEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-amz-json-1.1",
          "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        },
        body: JSON.stringify({
          ClientId: config.cognitoClientId,
          AuthFlow: "USER_PASSWORD_AUTH",
          AuthParameters: { USERNAME: username, PASSWORD: password },
        }),
      });
      const result = await response.json();
      if (!response.ok || !result.AuthenticationResult?.AccessToken)
        throw new Error();
      setPassword("");
      onLogin(result.AuthenticationResult.AccessToken);
    } catch {
      setError("ログインできません。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="input-card login-form" onSubmit={signIn}>
      <label htmlFor="username">ユーザー名</label>
      <input
        id="username"
        autoComplete="username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        disabled={busy}
        required
      />
      <label htmlFor="password">パスワード</label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        disabled={busy}
        required
      />
      <button
        className="submit"
        type="submit"
        disabled={busy || !username || !password}
      >
        {busy ? "ログイン中…" : "ログイン"}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

function App({ config }) {
  const [token, setToken] = useState("");
  const [text, setText] = useState("");
  const [method, setMethod] = useState("both");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState({});
  const [errors, setErrors] = useState({});
  const [hasRun, setHasRun] = useState(false);
  const [visibleMethods, setVisibleMethods] = useState(["lora", "full"]);

  async function analyze(event) {
    event.preventDefault();
    if (!text.trim() || busy) return;
    const methods = method === "both" ? ["lora", "full"] : [method];
    setBusy(true);
    setResults({});
    setErrors({});
    setHasRun(true);
    setVisibleMethods(methods);
    try {
      await Promise.all(
        methods.map(async (selected) => {
          try {
            const result = await predict(text, selected, token, config);
            setResults((previous) => ({ ...previous, [selected]: result }));
          } catch (error) {
            if (error.status === 401) {
              setToken("");
              setHasRun(false);
            }
            setErrors((previous) => ({
              ...previous,
              [selected]: error.message || "接続できません。",
            }));
          }
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <h1>感情分析</h1>
        {config.cognitoClientId && token && (
          <button
            className="logout"
            onClick={() => {
              setToken("");
              setHasRun(false);
              setResults({});
              setErrors({});
            }}
            disabled={busy}
          >
            ログアウト
          </button>
        )}
      </header>
      {config.cognitoClientId && !token ? (
        <Login config={config} onLogin={setToken} />
      ) : (
        <>
          <form onSubmit={analyze} className="input-card">
            <div className="input-heading">
              <label htmlFor="text">文章</label>
              <span>{text.length.toLocaleString()} / 10,000文字</span>
            </div>
            <textarea
              id="text"
              value={text}
              maxLength={10000}
              disabled={busy}
              onChange={(event) => {
                setText(event.target.value);
                setHasRun(false);
              }}
              rows={4}
              required
            />
            <div className="form-bottom">
              <fieldset disabled={busy}>
                <legend>モデル</legend>
                {[
                  ["both", "両方"],
                  ["lora", "LoRA"],
                  ["full", "Full FT"],
                ].map(([value, label]) => (
                  <label
                    className={`choice ${method === value ? "active" : ""}`}
                    key={value}
                  >
                    <input
                      type="radio"
                      name="model"
                      value={value}
                      checked={method === value}
                      onChange={() => {
                        setMethod(value);
                        setHasRun(false);
                      }}
                    />
                    {label}
                  </label>
                ))}
              </fieldset>
              <button
                className="submit"
                disabled={busy || !text.trim()}
                type="submit"
              >
                {busy ? "分析中…" : "分析"}
              </button>
            </div>
          </form>
          {hasRun && (
            <section className="results" aria-busy={busy}>
              <h2>結果</h2>
              <div className="result-grid">
                {visibleMethods.map((selected) => (
                  <Result
                    key={selected}
                    method={selected}
                    result={results[selected]}
                    error={errors[selected]}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

async function start() {
  let config = defaults;
  try {
    const response = await fetch("/config.json", { cache: "no-store" });
    if (response.ok) config = { ...defaults, ...(await response.json()) };
  } catch {
    /* Vite can use build-time defaults. */
  }
  createRoot(document.getElementById("root")).render(<App config={config} />);
}
start();
