import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getTransactions } from '../api/client';
import '../styles/pages.css';

export default function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await getTransactions({ limit: 50 });
        setTransactions(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const formatCurrency = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);
  
  const getStatusBadge = (status) => {
    return <span className={`badge status-${status.toLowerCase()}`}>{status.replace('_', ' ')}</span>;
  };
  
  const getCauseBadge = (cause) => {
    if (!cause) return <span className="text-muted">Unknown</span>;
    const clean = cause.replace(/_/g, ' ').toLowerCase();
    
    let colorClass = '';
    if (cause.includes('FUNDS')) colorClass = 'cause-insufficient';
    else if (cause.includes('FRAUD')) colorClass = 'cause-fraud';
    else if (cause.includes('DOWNTIME')) colorClass = 'cause-downtime';
    else if (cause.includes('ABANDONED')) colorClass = 'cause-abandoned';
    else if (cause.includes('EXPIRED')) colorClass = 'cause-expired';
    
    return <span className={`badge ${colorClass}`}>{clean}</span>;
  };

  return (
    <div className="page-container animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Transactions</h1>
          <div className="page-subtitle">View and manage failed payment recoveries</div>
        </div>
      </div>

      {error ? (
        <div className="glass-card detail-section" style={{ borderColor: 'var(--color-danger)' }}>
          <h3 style={{ color: 'var(--color-danger)' }}>Error Loading Transactions</h3>
          <p>{error}</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Payment ID</th>
                <th>Customer</th>
                <th>Amount</th>
                <th>Method</th>
                <th>Status</th>
                <th>Root Cause</th>
                <th>Recovery Prob</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array(5).fill(0).map((_, i) => (
                  <tr key={i}>
                    <td colSpan="7"><div className="skeleton" style={{ height: '20px' }}></div></td>
                  </tr>
                ))
              ) : transactions.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: 'var(--space-8)' }}>
                    No transactions found.
                  </td>
                </tr>
              ) : (
                transactions.map((txn) => (
                  <tr key={txn.id} className="clickable" onClick={() => navigate(`/transactions/${txn.id}`)}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{txn.external_id}</td>
                    <td>{txn.customer?.name || 'Unknown'}</td>
                    <td>{formatCurrency(txn.amount)}</td>
                    <td style={{ textTransform: 'capitalize' }}>{txn.payment_method}</td>
                    <td>{getStatusBadge(txn.status)}</td>
                    <td>{getCauseBadge(txn.root_cause || txn.failure_reason)}</td>
                    <td>
                      {txn.recovery_probability ? 
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span>{(txn.recovery_probability * 100).toFixed(1)}%</span>
                          <div style={{ width: '40px', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px' }}>
                            <div style={{ 
                              width: `${txn.recovery_probability * 100}%`, 
                              height: '100%', 
                              background: txn.recovery_probability > 0.6 ? 'var(--color-success)' : txn.recovery_probability > 0.3 ? 'var(--color-warning)' : 'var(--color-danger)',
                              borderRadius: '2px'
                            }}></div>
                          </div>
                        </div>
                      : <span className="text-muted">-</span>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
