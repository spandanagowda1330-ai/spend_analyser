import { useEffect, useState } from "react";
import { money } from "./format";

const API = "http://localhost:8000";

const LABELS = {
  duplicate: { text: "Extra charge", cls: "bad" },
  overlap: { text: "Overlap", cls: "warn" },
  forgotten: { text: "Forgotten?", cls: "warn" },
  price_hike: { text: "Price increase", cls: "warn" },
  review: { text: "Review", cls: "good" },
  spike: { text: "Spike", cls: "bad" },
  check: { text: "Check", cls: "bad" },
  info: { text: "Insight", cls: "good" },
};

async function getInsights() {
  const res = await fetch(`${API}/insights`);
  if (!res.ok) throw new Error("load failed");
  return res.json();
}

async function generateInsights() {
  const res = await fetch(`${API}/insights/generate`, { method: "POST" });
  if (!res.ok) throw new Error("generate failed");
  return res.json();
}

export default function Insights() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        let result = await getInsights();
        if (result.insights.length === 0) {
          await generateInsights();
          result = await getInsights();
        }
        if (!cancelled) setData(result);
      } catch {
        if (!cancelled) setError("Could not load insights.");
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      await generateInsights();
      setData(await getInsights());
    } catch {
      setError("Could not refresh insights.");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return error ? <div className="banner error">{error}</div> : null;
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="insights-head">
        <div>
          <h2 style={{ marginBottom: 4 }}>Ways to save</h2>
          {data.total_potential_savings > 0 && (
            <div className="muted">
              Potential savings: up to{" "}
              <b>{money(data.total_potential_savings)}</b> a year
            </div>
          )}
        </div>
        <button className="btn-small" onClick={refresh} disabled={busy}>
          {busy ? "Refreshing..." : "Refresh insights"}
        </button>
      </div>

      {error && <div className="banner error">{error}</div>}

      <ul className="list insights">
        {data.insights.map((i) => {
          const label = LABELS[i.type] || LABELS.info;
          return (
            <li key={i.id}>
              <span className={`badge ${label.cls}`}>{label.text}</span>
              <span className="insight-text">{i.message}</span>
              {i.estimated_savings > 0 && (
                <b className="save">Save {money(i.estimated_savings)}/yr</b>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
