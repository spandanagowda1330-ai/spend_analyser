import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Insights from "./Insights";

const API = "http://localhost:8000";

const money = (n) =>
  n == null
    ? "-"
    : "$" +
      Number(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });

async function get(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

function Stat({ label, value, hint }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);

  const loadAll = useCallback(async () => {
    try {
      const [overview, monthly, categories, subs, merchants, spikes] =
        await Promise.all([
          get("/analytics/overview"),
          get("/analytics/monthly"),
          get("/categories/summary"),
          get("/subscriptions"),
          get("/analytics/top-merchants"),
          get("/analytics/spikes"),
        ]);
      setData({ overview, monthly, categories, subs, merchants, spikes });
      setError("");
    } catch {
      setError(
        "Could not reach the backend. Is uvicorn running on port 8000?"
      );
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleUpload(e) {
    const input = e.target;
    const file = input.files[0];
    if (!file) return;

    setError("");
    setNotice("");
    try {
      setBusy("Uploading...");
      const form = new FormData();
      form.append("file", file);
      const up = await fetch(`${API}/upload`, { method: "POST", body: form });
      if (!up.ok) {
        const err = await up.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }
      const result = await up.json();

      setBusy("Detecting subscriptions...");
      await fetch(`${API}/process`, { method: "POST" });

      setBusy("Categorizing...");
      await fetch(`${API}/categorize`, { method: "POST" });

      setBusy("Finding savings...");
      await fetch(`${API}/insights/generate`, { method: "POST" });
      setVersion((v) => v + 1);

      await loadAll();
      setNotice(
        `Imported ${result.imported} new transactions (${result.skipped_duplicates} duplicates skipped).`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
      input.value = "";
    }
  }

  const empty = data && data.overview.transactions === 0;
  const subShare =
    data && data.overview.average_per_month
      ? Math.round(
          (data.subs.total_monthly_cost / data.overview.average_per_month) * 100
        )
      : 0;

  return (
    <div className="app">
      <div className="header">
        <div>
          <h1>Spend Analyzer</h1>
          <p>Find your subscriptions, understand your spending, save money.</p>
        </div>
        <label className={`btn ${busy ? "disabled" : ""}`}>
          {busy || "Upload CSV"}
          <input type="file" accept=".csv" onChange={handleUpload} />
        </label>
      </div>

      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner ok">{notice}</div>}

      {!data && !error && <p className="muted">Loading...</p>}

      {empty && (
        <div className="card empty" style={{ marginTop: 16 }}>
          <h2>No transactions yet</h2>
          <p className="muted">
            Click <b>Upload CSV</b> and choose a file with the columns date,
            description and amount.
          </p>
        </div>
      )}

      {data && !empty && (
        <>
          <Insights key={version} />

          <div className="grid stats">
            <Stat
              label="Total spent"
              value={money(data.overview.total_spent)}
              hint={`${data.overview.transactions} transactions, ${data.overview.months} months`}
            />
            <Stat
              label="Average per month"
              value={money(data.overview.average_per_month)}
            />
            <Stat
              label="Subscriptions per month"
              value={money(data.subs.total_monthly_cost)}
              hint={`${subShare}% of your monthly spending`}
            />
            <Stat
              label="Subscriptions per year"
              value={money(data.subs.total_annual_cost)}
              hint={`${data.subs.subscriptions.length} active or recent`}
            />
          </div>

          <div className="grid two">
            <div className="card">
              <h2>Monthly spending</h2>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={data.monthly}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => money(v)} />
                  <Legend />
                  <Bar
                    dataKey="subscriptions"
                    name="Subscriptions"
                    stackId="a"
                    fill="#4f46e5"
                  />
                  <Bar
                    dataKey="other"
                    name="Everything else"
                    stackId="a"
                    fill="#94a3b8"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h2>Spending by category</h2>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={data.categories} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis
                    type="category"
                    dataKey="category"
                    width={110}
                    tick={{ fontSize: 11 }}
                  />
                  <Tooltip formatter={(v) => money(v)} />
                  <Bar dataKey="total" name="Total" fill="#0ea5e9" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <h2>Subscriptions</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Merchant</th>
                    <th>Frequency</th>
                    <th className="num">Amount</th>
                    <th className="num">Per year</th>
                    <th>Last charged</th>
                    <th>Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {data.subs.subscriptions.map((s) => (
                    <tr key={s.id}>
                      <td>{s.merchant}</td>
                      <td>{s.frequency}</td>
                      <td className="num">{money(s.amount)}</td>
                      <td className="num">{money(s.annual_cost)}</td>
                      <td>{s.last_charged}</td>
                      <td>
                        {s.price_change > 0 && (
                          <span className="badge warn">
                            Price up {money(s.price_change)}
                          </span>
                        )}
                        {s.price_change < 0 && (
                          <span className="badge good">
                            Price down {money(Math.abs(s.price_change))}
                          </span>
                        )}
                        {s.status === "possibly_cancelled" && (
                          <span className="badge bad">Maybe cancelled</span>
                        )}
                        {s.status === "active" && !s.price_change && (
                          <span className="badge good">Active</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid two">
            <div className="card">
              <h2>Top merchants</h2>
              <ul className="list">
                {data.merchants.map((m) => (
                  <li key={m.merchant}>
                    <span>
                      {m.merchant}{" "}
                      <span className="muted">({m.category})</span>
                    </span>
                    <b>
                      {money(m.total)}{" "}
                      <span className="muted">{m.percent}%</span>
                    </b>
                  </li>
                ))}
              </ul>
            </div>

            <div className="card">
              <h2>Unusual spending</h2>
              {data.spikes.length === 0 ? (
                <p className="muted">
                  No unusual spikes found. Your spending is steady.
                </p>
              ) : (
                <ul className="list">
                  {data.spikes.slice(0, 6).map((s) => (
                    <li key={s.category + s.month}>
                      <span>
                        {s.category} in {s.month}
                      </span>
                      <b>
                        {money(s.amount)}{" "}
                        <span className="muted">vs usual {money(s.usual)}</span>
                      </b>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}