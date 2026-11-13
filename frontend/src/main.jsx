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
const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function predict(text, method) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(`${apiBase}/predict/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        response.status === 503
          ? "モデルを読み込めません。"
          : "分析に失敗しました。",
      );
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

function App() {
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
            const result = await predict(text, selected);
            setResults((previous) => ({ ...previous, [selected]: result }));
          } catch (error) {
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
      </header>
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
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
