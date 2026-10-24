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
import { money, setCurrency } from "./format";

const API = "http://localhost:8000";

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
  const [spendSign, setSpendSign] = useState("auto");
  const [dateOrder, setDateOrder] = useState("auto");

  const loadAll = useCallback(async () => {
    try {
      const [config, overview, monthly, categories, subs, merchants, spikes] =
        await Promise.all([
          get("/config"),
          get("/analytics/overview"),
          get("/analytics/monthly"),
          get("/categories/summary"),
          get("/subscriptions"),
          get("/analytics/top-merchants"),
          get("/analytics/spikes"),
        ]);
      setCurrency(config.currency_symbol);
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
      setBusy("Reading file...");
      const form = new FormData();
      form.append("file", file);
      form.append("spend_sign", spendSign);
      form.append("date_order", dateOrder);
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
      const d = result.detected;
      setNotice(
        `Imported ${result.imported} new transactions (${result.skipped_duplicates} duplicates skipped, ` +
          `${result.skipped_invalid} non-spending rows ignored). ` +
          `Read: date "${d.date_column}", description "${d.description_column}", ` +
          `dates ${d.date_order}; ${d.amount_mode}.`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
      input.value = "";
    }
  }

  async function clearData() {
    const ok = window.confirm(
      "Delete all transactions, subscriptions and insights? This cannot be undone."
    );
    if (!ok) return;
    setError("");
    setNotice("");
    try {
      setBusy("Clearing...");
      const res = await fetch(`${API}/data`, { method: "DELETE" });
      if (!res.ok) throw new Error("Could not clear the data");
      setVersion((v) => v + 1);
      await loadAll();
      setNotice("All data cleared. Upload a statement to start again.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  const empty = data && data.overview.transactions === 0;
  const billCount = data
    ? data.subs.subscriptions.filter((s) => s.kind === "bill").length
    : 0;
  const subCount = data ? data.subs.subscriptions.length - billCount : 0;
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

        <div className="actions">
          <details className="options">
            <summary>Options</summary>
            <div className="options-body">
              <label>
                Spending in the file is
                <select
                  value={spendSign}
                  onChange={(e) => setSpendSign(e.target.value)}
                >
                  <option value="auto">Auto-detect</option>
                  <option value="negative">Negative numbers</option>
                  <option value="positive">Positive numbers</option>
                </select>
              </label>
              <label>
                Dates are written
                <select
                  value={dateOrder}
                  onChange={(e) => setDateOrder(e.target.value)}
                >
                  <option value="auto">Auto-detect</option>
                  <option value="dayfirst">Day first (31/12/2026)</option>
                  <option value="monthfirst">Month first (12/31/2026)</option>
                </select>
              </label>
              <div className="muted small">
                Only change these if the results look wrong.
              </div>
            </div>
          </details>

          <button
            className="btn-secondary"
            onClick={clearData}
            disabled={!!busy || !data}
          >
            Clear data
          </button>

          <label className={`btn ${busy ? "disabled" : ""}`}>
            {busy || "Upload statement"}
            <input
              type="file"
              accept=".csv,.txt,.xlsx,.xlsm"
              onChange={handleUpload}
            />
          </label>
        </div>
      </div>

      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner ok">{notice}</div>}

      {!data && !error && <p className="muted">Loading...</p>}

      {empty && (
        <div className="card empty" style={{ marginTop: 16 }}>
          <h2>No transactions yet</h2>
          <p className="muted">
            Click <b>Upload statement</b> and choose a bank or credit-card
            statement (CSV or Excel). The app finds the date, description and
            amount columns by itself.
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
              hint={
                `${subCount} subscriptions` +
                (billCount > 0
                  ? `, plus ${billCount} recurring bills (${money(
                      data.subs.bills_monthly_cost
                    )}/month)`
                  : "")
              }
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
            <h2>Subscriptions and recurring bills</h2>
            {data.subs.subscriptions.length === 0 ? (
              <p className="muted">
                No recurring charges found. A subscription needs at least 3
                monthly charges (or 4 weekly, or 2 yearly) with a similar
                amount, so a short statement may not show any.
              </p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Merchant</th>
                      <th>Type</th>
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
                        <td>{s.kind === "bill" ? "Bill" : "Subscription"}</td>
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
                          {s.extra_charges > 0 && (
                            <span className="badge bad">
                              {s.extra_charges} extra charge
                              {s.extra_charges > 1 ? "s" : ""} (
                              {money(s.extra_amount)})
                            </span>
                          )}
                          {s.status === "possibly_cancelled" && (
                            <span className="badge bad">Maybe cancelled</span>
                          )}
                          {s.status === "active" &&
                            !s.price_change &&
                            !s.extra_charges && (
                            <span className="badge good">Active</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
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
