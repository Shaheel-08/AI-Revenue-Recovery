import { useState, useEffect } from 'react';
import { getPendingApprovals, decideApproval } from '../api/client';
import '../styles/pages.css';

export default function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const formatCurrency = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      setLoading(true);
      const data = await getPendingApprovals();
      setApprovals(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleDecision = async (id, approved) => {
    try {
      await decideApproval(id, { approved, reason: approved ? 'Approved by admin' : 'Rejected by admin' });
      // Remove from list
      setApprovals(approvals.filter(a => a.id !== id));
    } catch (err) {
      alert("Failed to process approval: " + err.message);
    }
  };

  return (
    <div className="page-container animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Human Approval Center</h1>
          <div className="page-subtitle">Review high-value and high-risk recovery actions</div>
        </div>
      </div>

      {error && (
        <div className="glass-card detail-section" style={{ borderColor: 'var(--color-danger)', marginBottom: 'var(--space-6)' }}>
          <h3 style={{ color: 'var(--color-danger)' }}>Error Loading Approvals</h3>
          <p>{error}</p>
        </div>
      )}

      {loading ? (
        <div className="approvals-grid">
          {[1, 2, 3].map(i => (
            <div key={i} className="glass-card approval-card skeleton" style={{ height: '250px' }}></div>
          ))}
        </div>
      ) : approvals.length === 0 ? (
        <div className="glass-card detail-section" style={{ textAlign: 'center', padding: 'var(--space-10)' }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>✅</div>
          <h3>No Pending Approvals</h3>
          <p className="text-muted">All recovery actions have been processed.</p>
        </div>
      ) : (
        <div className="approvals-grid">
          {approvals.map(approval => (
            <div key={approval.id} className="glass-card approval-card">
              <div className="approval-card-header">
                <div>
                  <h3 style={{ fontSize: 'var(--font-size-lg)', marginBottom: '4px' }}>
                    {formatCurrency(approval.transaction?.amount || 0)}
                  </h3>
                  <div className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>
                    {approval.transaction?.external_id}
                  </div>
                </div>
                <span className="badge status-pending">Pending</span>
              </div>

              <div className="kv-list">
                <div className="kv-item"><span className="label">Customer</span><span className="value">{approval.customer?.name}</span></div>
                <div className="kv-item"><span className="label">Root Cause</span><span className="value" style={{ textTransform: 'capitalize' }}>{approval.transaction?.root_cause?.replace(/_/g, ' ')}</span></div>
                <div className="kv-item"><span className="label">Proposed Action</span><span className="value" style={{ color: 'var(--accent-primary)', fontWeight: '600', textTransform: 'capitalize' }}>{approval.proposed_action?.replace(/_/g, ' ')}</span></div>
                <div className="kv-item"><span className="label">Recovery Prob.</span><span className="value">{(approval.recovery_probability * 100).toFixed(1)}%</span></div>
                <div className="kv-item"><span className="label">Exp. Net Revenue</span><span className="value">{formatCurrency(approval.expected_net_revenue)}</span></div>
                <div className="kv-item"><span className="label">Risk Reason</span><span className="value" style={{ color: 'var(--color-warning)', fontSize: 'var(--font-size-xs)' }}>{approval.reason_for_approval}</span></div>
              </div>

              <div className="approval-card-actions">
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => handleDecision(approval.id, false)}>
                  Reject
                </button>
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => handleDecision(approval.id, true)}>
                  Approve Action
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
