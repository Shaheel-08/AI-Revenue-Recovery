/**
 * TopFailureCauses — Horizontal bar chart of failure cause distribution.
 * Data from GET /dashboard/summary → top_failure_causes[]:
 *   { cause, count, amount }
 */

const CAUSE_COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#3b82f6', '#14b8a6',
  '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#f97316',
];

const CAUSE_LABELS = {
  BANK_DOWNTIME: 'Bank Downtime',
  INSUFFICIENT_FUNDS: 'Low Balance',
  EXPIRED_CARD: 'Expired Card',
  AUTH_OTP_FAILURE: 'OTP Failure',
  INVALID_DETAILS: 'Invalid Details',
  USER_ABANDONED: 'Abandoned',
  MERCHANT_INTEGRATION_ERROR: 'Integration Error',
  SUBSCRIPTION_MANDATE_FAILURE: 'Mandate Failure',
  SUSPECTED_FRAUD: 'Fraud Suspect',
  UNKNOWN: 'Unknown',
};

function formatINR(value) {
  if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
  if (value >= 1000) return `₹${(value / 1000).toFixed(1)}K`;
  return `₹${value.toFixed(0)}`;
}

export default function TopFailureCauses({ causes }) {
  if (!causes || causes.length === 0) {
    return (
      <div className="glass-card chart-card">
        <h3>Top Failure Causes</h3>
        <div className="empty-state">
          <div className="icon">🔍</div>
          <p>No failure data available</p>
        </div>
      </div>
    );
  }

  const maxCount = Math.max(...causes.map(c => c.count));

  return (
    <div className="glass-card chart-card animate-in" style={{ animationDelay: '400ms' }}>
      <h3>Top Failure Causes</h3>
      <div className="cause-list">
        {causes.slice(0, 9).map((cause, i) => (
          <div key={cause.cause} className="cause-item">
            <span className="cause-name" title={cause.cause}>
              {CAUSE_LABELS[cause.cause] || cause.cause}
            </span>
            <div className="cause-bar-track">
              <div
                className="cause-bar-fill"
                style={{
                  width: `${(cause.count / maxCount) * 100}%`,
                  background: `${CAUSE_COLORS[i % CAUSE_COLORS.length]}30`,
                  borderLeft: `3px solid ${CAUSE_COLORS[i % CAUSE_COLORS.length]}`,
                }}
              >
                <span>{cause.count}</span>
              </div>
            </div>
            <span className="cause-amount">{formatINR(cause.amount)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
