import { useState, useEffect } from 'react';
import { getPolicy, updatePolicy } from '../api/client';
import '../styles/pages.css';

export default function Settings() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await getPolicy();
        setConfig(data.config);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleChange = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }));
    setSuccess(false);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      await updatePolicy(config);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="page-container"><div className="skeleton" style={{height: '400px'}}></div></div>;
  }

  if (error && !config) {
    return (
      <div className="page-container">
        <div className="glass-card detail-section" style={{ borderColor: 'var(--color-danger)' }}>
          <h3 style={{ color: 'var(--color-danger)' }}>Error Loading Policy</h3>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Merchant Policy Center</h1>
          <div className="page-subtitle">Configure AI safety guardrails and autonomous behavior limits</div>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {success && <span style={{ color: 'var(--color-success)', fontWeight: '500' }}>✓ Saved successfully</span>}
          <button 
            className="btn btn-primary" 
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Policy Changes'}
          </button>
        </div>
      </div>

      <div className="settings-layout">
        <div className="settings-nav">
          <div className="settings-nav-item active">Guardrails & Limits</div>
          <div className="settings-nav-item">Channels & Communication</div>
          <div className="settings-nav-item">Fraud & Risk</div>
        </div>

        <div className="settings-section">
          <div className="glass-card detail-section">
            <h3>🛡 Auto-Recovery Guardrails</h3>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginTop: 'var(--space-4)' }}>
              <div className="form-group">
                <label className="form-label">Max Retries</label>
                <div className="form-desc">Maximum number of automated payment retries allowed per transaction</div>
                <input 
                  type="number" 
                  className="form-input" 
                  value={config.max_retries} 
                  onChange={(e) => handleChange('max_retries', parseInt(e.target.value) || 0)} 
                  min="0" max="10"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Approval Threshold (₹)</label>
                <div className="form-desc">Transactions above this amount require human approval</div>
                <input 
                  type="number" 
                  className="form-input" 
                  value={config.approval_threshold_amount} 
                  onChange={(e) => handleChange('approval_threshold_amount', parseFloat(e.target.value) || 0)} 
                />
              </div>

              <div className="form-group">
                <label className="form-label">Max Discount Percentage</label>
                <div className="form-desc">Maximum discount the AI can autonomously offer (0 to disable)</div>
                <div style={{ position: 'relative' }}>
                  <input 
                    type="number" 
                    className="form-input" 
                    style={{ width: '100%' }}
                    value={config.max_discount_percent} 
                    onChange={(e) => handleChange('max_discount_percent', parseFloat(e.target.value) || 0)} 
                    min="0" max="100"
                  />
                  <span style={{ position: 'absolute', right: '15px', top: '10px', color: 'var(--text-muted)' }}>%</span>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-card detail-section">
            <h3>💬 Communication Limits (Circuit Breaker)</h3>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginTop: 'var(--space-4)' }}>
              <div className="form-group">
                <label className="form-label">Max Touchpoints (72h)</label>
                <div className="form-desc">Maximum number of communications to a single customer within 72 hours</div>
                <input 
                  type="number" 
                  className="form-input" 
                  value={config.max_touchpoints_72h} 
                  onChange={(e) => handleChange('max_touchpoints_72h', parseInt(e.target.value) || 0)} 
                  min="1" max="20"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Quiet Hours Start</label>
                <div className="form-desc">24h clock (e.g. 22 for 10 PM)</div>
                <input 
                  type="number" 
                  className="form-input" 
                  value={config.quiet_hour_start} 
                  onChange={(e) => handleChange('quiet_hour_start', parseInt(e.target.value) || 0)} 
                  min="0" max="23"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Quiet Hours End</label>
                <div className="form-desc">24h clock (e.g. 8 for 8 AM)</div>
                <input 
                  type="number" 
                  className="form-input" 
                  value={config.quiet_hour_end} 
                  onChange={(e) => handleChange('quiet_hour_end', parseInt(e.target.value) || 0)} 
                  min="0" max="23"
                />
              </div>
            </div>
          </div>
          
          <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: 'var(--radius-md)', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
            <h4 style={{ color: 'var(--color-danger)', marginBottom: '0.5rem' }}>Suspicious Transactions</h4>
            <p className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>
              Transactions identified as SUSPECTED_FRAUD by the ML failure classifier are strictly blocked from automated recovery at the framework level. This safety policy cannot be overridden by merchant settings.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
