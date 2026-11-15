import { useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const classes = [
  ["-2", "強い否定"],
  ["-1", "否定"],
  ["0", "中立"],
  ["1", "肯定"],
  ["2", "強い肯定"],
] as const;
type Method = "lora" | "full";
type Selection = Method | "both";
type Sentiment = -2 | -1 | 0 | 1 | 2;
type Prediction = {
  model: Method;
  model_version: string;
  sentiment: Sentiment;
  probabilities: Record<`${Sentiment}`, number>;
  truncated: boolean;
  elapsed_ms: number;
};
type ResultProps = {
  method: Method;
  result: Prediction | undefined;
  error: string | undefined;
};
const choices: [Selection, string][] = [
  ["both", "両方"],
  ["lora", "LoRA"],
  ["full", "Full FT"],
];
const names = { lora: "LoRA", full: "Full FT" };
let apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
let enabledMethods: Method[] = ["lora", "full"];

function isMethod(value: unknown): value is Method {
  return value === "lora" || value === "full";
}

async function predict(text: string, method: Method): Promise<Prediction> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(`${apiBase}/predict/${method}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(
        response.status === 503
          ? "モデルを読み込めません。"
          : "分析に失敗しました。",
      );
      throw error;
    }
    return result as Prediction;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw new Error("タイムアウトしました。");
    if (error instanceof TypeError) throw new Error("接続できません。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function Result({ method, result, error }: ResultProps) {
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
              {result.sentiment > 0 ? "+" : ""}
              {result.sentiment}
            </strong>
            <span>{classes.find(([id]) => Number(id) === result.sentiment)?.[1]}</span>
          </div>
          <div className="probabilities">
            {classes.map(([id, label]) => (
              <div
                className={`prob-row ${Number(id) === result.sentiment ? "selected" : ""}`}
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
  const [method, setMethod] = useState<Selection>(enabledMethods.length > 1 ? "both" : enabledMethods[0]);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Partial<Record<Method, Prediction>>>({});
  const [errors, setErrors] = useState<Partial<Record<Method, string>>>({});
  const [hasRun, setHasRun] = useState(false);
  const [visibleMethods, setVisibleMethods] = useState(enabledMethods);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!text.trim() || busy) return;
    const methods = method === "both" ? enabledMethods : [method];
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
              [selected]: error instanceof Error ? error.message : "接続できません。",
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
            {choices.filter(([value]) => value === "both"
              ? enabledMethods.length > 1 : enabledMethods.includes(value)
            ).map(([value, label]) => (
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

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element unavailable");
const root = createRoot(rootElement);
async function start() {
  if (import.meta.env.PROD) {
    const response = await fetch("/config.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Configuration unavailable");
    const config = await response.json() as { methods?: unknown; apiBaseUrl?: unknown };
    if (!Array.isArray(config.methods) || !config.methods.length
      || !config.methods.every(isMethod)
      || typeof config.apiBaseUrl !== "string") {
      throw new Error("Invalid configuration");
    }
    apiBase = (import.meta.env.VITE_API_BASE_URL || config.apiBaseUrl).replace(/\/$/, "");
    enabledMethods = config.methods;
  }
  root.render(<App />);
}
start().catch(() => {
  root.render(<p role="alert">設定を読み込めませんでした。ページを再読み込みしてください。</p>);
});
