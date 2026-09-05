/**
 * TrendChart — Recharts area chart: daily failed vs recovered amounts.
 * Data from GET /dashboard/summary → daily_trends[]:
 *   { date, failed_amount, recovered_amount, recovery_rate }
 */
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

function formatAxisINR(value) {
  if (value >= 100000) return `₹${(value / 100000).toFixed(0)}L`;
  if (value >= 1000) return `₹${(value / 1000).toFixed(0)}K`;
  return `₹${value}`;
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'rgba(17, 24, 39, 0.95)',
      backdropFilter: 'blur(12px)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '10px',
      padding: '12px 16px',
      fontSize: '12px',
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', background: p.color, display: 'inline-block'
          }} />
          <span style={{ color: '#cbd5e1' }}>{p.name}:</span>
          <span style={{ color: '#f1f5f9', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
            {formatAxisINR(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function TrendChart({ trends }) {
  if (!trends || trends.length === 0) {
    return (
      <div className="glass-card chart-card">
        <h3>Daily Trend</h3>
        <div className="empty-state">
          <div className="icon">📈</div>
          <p>No trend data available yet</p>
        </div>
      </div>
    );
  }

  // Format dates for x-axis (show "Jul 5" style)
  const chartData = trends.map(t => ({
    ...t,
    label: new Date(t.date + 'T00:00:00').toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
  }));

  return (
    <div className="glass-card chart-card animate-in" style={{ animationDelay: '300ms' }}>
      <h3>Daily Failed vs Recovered Revenue</h3>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <defs>
            <linearGradient id="gradFailed" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradRecovered" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={formatAxisINR}
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: '#94a3b8' }}
            iconType="circle"
            iconSize={8}
          />
          <Area
            type="monotone"
            dataKey="failed_amount"
            name="Failed"
            stroke="#ef4444"
            strokeWidth={2}
            fill="url(#gradFailed)"
          />
          <Area
            type="monotone"
            dataKey="recovered_amount"
            name="Recovered"
            stroke="#10b981"
            strokeWidth={2}
            fill="url(#gradRecovered)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
