import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const classes = [
  ['-2', '強い否定'], ['-1', '否定'], ['0', '中立'], ['1', '肯定'], ['2', '強い肯定'],
];
const names = { lora: 'LoRA', full: 'Full FT' };
const samples = ['今日はとても楽しかった！', '最悪な一日だった。', '明日は月曜日です。'];
const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

async function predict(text, method) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(`${apiBase}/predict/${method}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }), signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('応答がタイムアウトしました。少し待ってから再度お試しください。');
    throw error;
  } finally { clearTimeout(timer); }
}

function Result({ method, result, error }) {
  const sentiment = result?.sentiment;
  return <section className="result-card" aria-label={`${names[method]}の結果`}>
    <div className="card-heading"><h3>{names[method]}</h3><span className="tag">{method === 'lora' ? '低ランク適応' : '全パラメータ更新'}</span></div>
    {error ? <p className="error" role="alert">{error}</p> : result ? <>
      <div className="prediction"><strong>{sentiment > 0 ? '+' : ''}{sentiment}</strong><span>{classes.find(([id]) => Number(id) === sentiment)[1]}</span></div>
      <div className="probabilities">{classes.map(([id, label]) => <div className={`prob-row ${Number(id) === sentiment ? 'selected' : ''}`} key={id}>
        <span>{label}</span><div className="track"><div style={{ width: `${result.probabilities[id] * 100}%` }} /></div><span>{(result.probabilities[id] * 100).toFixed(1)}%</span>
      </div>)}</div>
      <div className="result-meta"><span>{(result.elapsed_ms / 1000).toFixed(2)}秒</span><span>モデル {result.model_version}</span></div>
      {result.truncated && <p className="notice">512トークンを超えたため、入力の一部を切り詰めて分析しました。</p>}
    </> : <div className="empty-result">分析すると、ここに結果が表示されます。</div>}
  </section>;
}

function App() {
  const [text, setText] = useState('');
  const [method, setMethod] = useState('both');
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState({});
  const [errors, setErrors] = useState({});
  const [submitted, setSubmitted] = useState(null);
  const [visibleMethods, setVisibleMethods] = useState(['lora', 'full']);

  async function analyze(event) {
    event.preventDefault();
    if (!text.trim() || busy) return;
    const methods = method === 'both' ? ['lora', 'full'] : [method];
    setBusy(true); setResults({}); setErrors({}); setSubmitted(text); setVisibleMethods(methods);
    try {
      await Promise.all(methods.map(async selected => {
        try {
          const result = await predict(text, selected);
          setResults(previous => ({ ...previous, [selected]: result }));
        } catch (error) {
          setErrors(previous => ({ ...previous, [selected]: error.message || 'APIに接続できませんでした。' }));
        }
      }));
    } finally { setBusy(false); }
  }

  return <main>
    <header><a className="brand" href="/">ことばの温度<span>WRIME SENTIMENT LAB</span></a><span className="header-note">Gemma 3 · 270M</span></header>
    <section className="intro"><p className="eyebrow">日本語の感情を、ふたつのモデルで。</p><h1>そのことばは、<br />どんな気持ち？</h1><p>文章の感情を5段階で分析。LoRAとFull FTの<br className="desktop-break" />学習方法による違いを、並べて確かめられます。</p></section>
    <form onSubmit={analyze} className="input-card">
      <div className="input-heading"><label htmlFor="text">分析する文章</label><span>{text.length.toLocaleString()} / 10,000文字</span></div>
      <textarea id="text" value={text} maxLength={10000} disabled={busy} onChange={event => setText(event.target.value)} placeholder="今日はどんな一日でしたか？" rows={4} required />
      <div className="samples"><span>例文</span>{samples.map(sample => <button disabled={busy} key={sample} type="button" onClick={() => setText(sample)}>{sample}</button>)}</div>
      <div className="form-bottom"><fieldset disabled={busy}><legend>使用するモデル</legend>{[['both', '両方を比較'], ['lora', 'LoRA'], ['full', 'Full FT']].map(([value, label]) => <label className={`choice ${method === value ? 'active' : ''}`} key={value}><input type="radio" name="model" value={value} checked={method === value} onChange={() => setMethod(value)} />{label}</label>)}</fieldset><button className="submit" disabled={busy || !text.trim()} type="submit">{busy ? '分析しています…' : '感情を分析する'}<span aria-hidden="true">↗</span></button></div>
      <p className="input-note">最大512トークンまで分析します。初回はモデルの読み込みに時間がかかります。</p>
    </form>
    <section className="results" aria-busy={busy}>
      <div className="section-heading"><h2>分析結果</h2><span role="status">{busy ? 'モデルで推論中…' : submitted ? '分析が完了しました' : '入力をお待ちしています'}</span></div>
      {submitted && <p className="submitted">「{submitted.length > 100 ? submitted.slice(0, 100) + '…' : submitted}」</p>}
      <div className="result-grid">{visibleMethods.map(selected => <Result key={selected} method={selected} result={results[selected]} error={errors[selected]} />)}</div>
      <p className="footnote">数値はクラスごとの予測確率です。予測の正しさを保証するものではありません。</p>
    </section>
    <footer><span>WRIME Ver.2 · writer.sentiment</span><span>研究用デモ / 入力文はアプリのログに保存しません</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
