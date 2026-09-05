import React from 'react';

export default function RecentActionsFeed({ logs = [] }) {
  if (logs.length === 0) {
    return (
      <div style={{ padding: 'var(--space-6)', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ marginBottom: 'var(--space-4)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span>⚡</span> Audit Trail
        </h3>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
          <p>No recent actions</p>
        </div>
      </div>
    );
  }

  const getStatusColor = (passed) => passed ? 'var(--color-success)' : 'var(--color-danger)';
  const getStatusIcon = (passed) => passed ? '✓' : '⚠';

  return (
    <div style={{ padding: 'var(--space-6)', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <h3 style={{ marginBottom: 'var(--space-4)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <span>⚡</span> Audit Trail
      </h3>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
        {logs.map((log) => (
          <div key={log.id} style={{ 
            padding: '1rem', 
            background: 'rgba(255,255,255,0.03)', 
            borderRadius: 'var(--radius-md)',
            borderLeft: `3px solid ${getStatusColor(log.compliance_passed)}`
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <span style={{ fontWeight: '600', textTransform: 'capitalize', color: 'var(--text-primary)' }}>
                {log.action_type.replace(/_/g, ' ')}
              </span>
              <span style={{ color: getStatusColor(log.compliance_passed), fontWeight: 'bold' }}>
                {getStatusIcon(log.compliance_passed)}
              </span>
            </div>
            
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
              <div><span style={{color: 'var(--text-muted)'}}>Payment ID:</span> {log.payment_id}</div>
              {log.reason_blocked && (
                <div style={{ color: 'var(--color-warning)', marginTop: '4px' }}>
                  Block Reason: {log.reason_blocked}
                </div>
              )}
              <div style={{ marginTop: '4px', textAlign: 'right', fontSize: '10px' }}>
                {new Date(log.created_at).toLocaleString()}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
