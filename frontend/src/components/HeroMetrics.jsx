/**
 * HeroMetrics — 4 top-level KPI cards.
 * Fields from GET /dashboard/summary:
 *   total_at_risk, total_recoverable, total_recovered, recovery_rate,
 *   total_transactions, failed_transactions, recovered_transactions, in_progress_transactions
 */

function formatINR(value) {
  if (value >= 10000000) return `₹${(value / 10000000).toFixed(2)}Cr`;
  if (value >= 100000) return `₹${(value / 100000).toFixed(2)}L`;
  if (value >= 1000) return `₹${(value / 1000).toFixed(1)}K`;
  return `₹${value.toFixed(0)}`;
}

export default function HeroMetrics({ data }) {
  const metrics = [
    {
      label: 'Revenue at Risk',
      value: formatINR(data.total_at_risk),
      sub: `${data.failed_transactions + data.in_progress_transactions} transactions`,
      className: 'at-risk',
    },
    {
      label: 'Recoverable',
      value: formatINR(data.total_recoverable),
      sub: `${data.failed_transactions} failed + ${data.in_progress_transactions} in progress`,
      className: 'recoverable',
    },
    {
      label: 'Recovered',
      value: formatINR(data.total_recovered),
      sub: `${data.recovered_transactions} transactions`,
      className: 'recovered',
    },
    {
      label: 'Recovery Rate',
      value: `${data.recovery_rate.toFixed(1)}%`,
      sub: `${data.recovered_transactions} of ${data.total_transactions} total`,
      className: 'rate',
    },
  ];

  return (
    <div className="hero-metrics">
      {metrics.map((m, i) => (
        <div
          key={m.label}
          className={`glass-card metric-card ${m.className} animate-in`}
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <div className="metric-label">{m.label}</div>
          <div className="metric-value">{m.value}</div>
          <div className="metric-sub">{m.sub}</div>
        </div>
      ))}
    </div>
  );
}
