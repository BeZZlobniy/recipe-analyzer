import { formatCompatibilityLevel } from "../utils/labels";

export function BarList({ items }: { items: { label: string; value: number }[] }) {
  const max = Math.max(...items.map((item) => item.value), 1);

  return (
    <div className="card">
      <h3>Частые проблемы</h3>
      <div className="barList">
        {items.length === 0 ? <div className="muted">Пока нет данных</div> : null}
        {items.map((item) => (
          <div key={item.label} className="barRow">
            <span>{item.label}</span>
            <div className="barTrack">
              <div className="barFill" style={{ width: `${(item.value / max) * 100}%` }} />
            </div>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DonutGroup({
  values,
  title = "Распределение",
}: {
  values: Record<string, number>;
  title?: string;
}) {
  const total = Object.values(values).reduce((sum, value) => sum + value, 0) || 1;
  const high = Math.round(((values.high ?? 0) / total) * 100);
  const medium = Math.round(((values.medium ?? 0) / total) * 100);
  const low = Math.round(((values.low ?? 0) / total) * 100);

  return (
    <div>
      <h3>{title}</h3>
      <div className="donutWrap">
        <div
          className="donut"
          style={{
            background: `conic-gradient(var(--good) 0 ${high}%, var(--warn) ${high}% ${high + medium}%, var(--bad) ${high + medium}% 100%)`,
          }}
        />
        <div className="legend">
          <div>{formatCompatibilityLevel("high")}: {values.high ?? 0}</div>
          <div>{formatCompatibilityLevel("medium")}: {values.medium ?? 0}</div>
          <div>{formatCompatibilityLevel("low")}: {values.low ?? 0}</div>
        </div>
      </div>
    </div>
  );
}
