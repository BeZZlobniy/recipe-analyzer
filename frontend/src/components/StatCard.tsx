export function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="card statCard">
      <div className="muted">{label}</div>
      <div className="statValue">{value}</div>
      {hint ? <div className="muted small">{hint}</div> : null}
    </div>
  );
}
