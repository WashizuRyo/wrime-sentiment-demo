import { useState, useTransition, type SubmitEvent } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const classes = [
  ["2", "強い肯定"],
  ["1", "肯定"],
  ["0", "中立"],
  ["-1", "否定"],
  ["-2", "強い否定"],
] as const;
const methods = ["lora", "full"] as const;
type Method = (typeof methods)[number];
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
const choices = ["both", ...methods] as const;
const names = { both: "両方", lora: "LoRA", full: "Full FT" };

async function predict(text: string, method: Method): Promise<Prediction> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const body = JSON.stringify({ text });
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
    const payloadHash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    const response = await fetch(`/predict/${method}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // CloudFront OAC requires the payload hash for POST requests to Lambda Function URLs.
        "x-amz-content-sha256": payloadHash,
      },
      body,
      signal: controller.signal,
    });
    if (!response.ok) {
      const error = new Error(
        response.status === 503
          ? "モデルを読み込めません。"
          : response.status === 504 ? "タイムアウトしました。" : "分析に失敗しました。",
      );
      throw error;
    }
    return await response.json() as Prediction;
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
        {!error && result && (
          <p className="prediction">
            {classes.find(([id]) => Number(id) === result.sentiment)?.[1]}
          </p>
        )}
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : result && (
        <>
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
      )}
    </section>
  );
}

function App() {
  const [text, setText] = useState("");
  const [method, setMethod] = useState<Selection>("both");
  const [isPending, startTransition] = useTransition();
  const [results, setResults] = useState<Partial<Record<Method, Prediction>>>({});
  const [errors, setErrors] = useState<Partial<Record<Method, string>>>({});
  const completedMethods = methods.filter(
    (selected) => results[selected] !== undefined || errors[selected] !== undefined,
  );

  function analyze(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!text.trim() || isPending) return;
    const selectedMethods = method === "both" ? methods : [method];
    setResults({});
    setErrors({});
    startTransition(async () => {
      await Promise.all(
        selectedMethods.map(async (selected) => {
          try {
            const result = await predict(text, selected);
            startTransition(() => {
              setResults((previous) => ({ ...previous, [selected]: result }));
            });
          } catch (error) {
            startTransition(() => {
              setErrors((previous) => ({
                ...previous,
                [selected]: error instanceof Error ? error.message : "接続できません。",
              }));
            });
          }
        }),
      );
    });
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
          disabled={isPending}
          onChange={(event) => setText(event.target.value)}
          rows={4}
          required
        />
        <div className="form-bottom">
          <fieldset disabled={isPending}>
            <legend>モデル</legend>
            {choices.map((value) => (
              <label
                className={`choice ${method === value ? "active" : ""}`}
                key={value}
              >
                <input
                  type="radio"
                  name="model"
                  value={value}
                  checked={method === value}
                  onChange={() => setMethod(value)}
                />
                {names[value]}
              </label>
            ))}
          </fieldset>
          <button
            className="submit"
            disabled={isPending || !text.trim()}
            type="submit"
          >
            {isPending ? "分析中…" : "分析"}
          </button>
        </div>
      </form>
      {!isPending && completedMethods.length > 0 && (
        <section className="results">
          <div className="result-grid">
            {completedMethods.map((selected) => (
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
createRoot(rootElement).render(<App />);
