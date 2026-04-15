import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { analysisApi } from "../api";
import type { HistoryItem } from "../types/api";

export function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    void analysisApi.history().then(setItems);
  }, []);

  const filtered = useMemo(
    () => items.filter((item) => item.title.toLowerCase().includes(query.toLowerCase()) || (item.summary ?? "").toLowerCase().includes(query.toLowerCase())),
    [items, query]
  );

  return (
    <div className="page">
      <div className="pageHeader">
        <div>
          <h1>История</h1>
          <p className="muted">Сохраненные результаты анализа.</p>
        </div>
        <input placeholder="Поиск по названию или summary" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      <div className="list">
        {filtered.map((item) => (
          <Link key={item.id} className="listCard linkCard" to={`/history/${item.id}`}>
            <strong>{item.title}</strong>
            <div className="muted">{new Date(item.created_at).toLocaleString()}</div>
            <p>{item.summary ?? "Нет summary"}</p>
          </Link>
        ))}
        {filtered.length === 0 ? <div className="card muted">Анализы не найдены</div> : null}
      </div>
    </div>
  );
}
