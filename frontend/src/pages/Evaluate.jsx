import { useState } from 'react';
import { runBatchEvaluation } from '../api/client';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import '../styles/pages.css';

export default function Evaluate() {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState('');
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const formatCurrency = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);

  const handleRunEvaluation = async () => {
    setRunning(true);
    setReport(null);
    setError(null);
    
    setProgress('Preparing dataset (100 synthetic transactions)...');
    await new Promise(r => setTimeout(r, 600));
    
    setProgress('Running Baseline Strategy (Fixed Retry 24h)...');
    await new Promise(r => setTimeout(r, 600));
    
    setProgress('Running RecoverOS Adaptive Policy...');
    await new Promise(r => setTimeout(r, 600));
    
    setProgress('Calculating incremental metrics...');
    
    try {
      const data = await runBatchEvaluation({ transactionCount: 100 });
      setReport(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
      setProgress('');
    }
  };

  return (
    <div className="page-container animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Recovery Evaluation Lab</h1>
          <div className="page-subtitle">Benchmark RecoverOS adaptive policy vs traditional fixed-retry baseline</div>
        </div>
        
        <button 
          className="btn btn-primary" 
          onClick={handleRunEvaluation}
          disabled={running}
        >
          {running ? 'Running Benchmark...' : '▶ RUN SYNTHETIC BENCHMARK'}
        </button>
      </div>

      {running && (
        <div className="glass-card detail-section" style={{ textAlign: 'center', padding: 'var(--space-10)' }}>
          <div className="pulse" style={{ fontSize: '3rem', marginBottom: '1rem' }}>⚙️</div>
          <h3>Running Simulation</h3>
          <p className="text-muted" style={{ marginTop: '0.5rem', fontFamily: 'var(--font-mono)' }}>{progress}</p>
          <div style={{ width: '100%', maxWidth: '400px', height: '4px', background: 'rgba(255,255,255,0.1)', margin: '2rem auto 0', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ width: '50%', height: '100%', background: 'var(--accent-primary)', animation: 'shimmer 1s infinite linear', backgroundSize: '200% 100%' }}></div>
          </div>
        </div>
      )}

      {error && (
        <div className="glass-card detail-section" style={{ borderColor: 'var(--color-danger)' }}>
          <h3 style={{ color: 'var(--color-danger)' }}>Evaluation Failed</h3>
          <p>{error}</p>
        </div>
      )}

      {report && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          
          {/* Top Line Results */}
          <div className="glass-card detail-section" style={{ background: 'rgba(99, 102, 241, 0.05)', borderColor: 'var(--accent-primary)' }}>
            <h3 style={{ color: 'var(--accent-primary)', borderBottom: '1px solid rgba(99,102,241,0.2)' }}>
              🏆 Simulation Results ({report.transaction_count} transactions)
            </h3>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-6)', marginTop: 'var(--space-4)' }}>
              <div>
                <div className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Net Revenue Improvement</div>
                <div style={{ fontSize: 'var(--font-size-3xl)', fontWeight: '700', color: 'var(--color-success)' }}>
                  +{formatCurrency(report.net_revenue_improvement)}
                </div>
              </div>
              <div>
                <div className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Recovery Rate Lift</div>
                <div style={{ fontSize: 'var(--font-size-3xl)', fontWeight: '700', color: 'var(--color-success)' }}>
                  +{report.recovery_rate_improvement}%
                </div>
              </div>
              <div>
                <div className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>Message Reduction</div>
                <div style={{ fontSize: 'var(--font-size-3xl)', fontWeight: '700', color: 'var(--color-success)' }}>
                  {report.message_reduction}%
                </div>
              </div>
            </div>
          </div>

          {/* Comparison Grid */}
          <div className="intel-grid">
            <div className="glass-card detail-section">
              <h3>🤖 RecoverOS Adaptive</h3>
              <div className="kv-list">
                <div className="kv-item"><span className="label">Recovery Rate</span><span className="value" style={{ color: 'var(--color-success)'}}>{report.ros_recovery_rate}%</span></div>
                <div className="kv-item"><span className="label">Net Revenue</span><span className="value" style={{ color: 'var(--color-success)'}}>{formatCurrency(report.ros_net_revenue)}</span></div>
                <div className="kv-item"><span className="label">Avg Attempts / Recovery</span><span className="value">{report.ros_avg_attempts}</span></div>
                <div className="kv-item"><span className="label">Total Messages Sent</span><span className="value">{report.ros_message_count}</span></div>
                <div className="kv-item"><span className="label">Duplicate Charges</span><span className="value" style={{ color: report.ros_duplicate_charges > 0 ? 'var(--color-danger)' : 'var(--color-success)'}}>{report.ros_duplicate_charges}</span></div>
              </div>
            </div>

            <div className="glass-card detail-section">
              <h3>📉 Fixed-Retry Baseline (24h)</h3>
              <div className="kv-list">
                <div className="kv-item"><span className="label">Recovery Rate</span><span className="value">{report.baseline_recovery_rate}%</span></div>
                <div className="kv-item"><span className="label">Net Revenue</span><span className="value">{formatCurrency(report.baseline_net_revenue)}</span></div>
                <div className="kv-item"><span className="label">Avg Attempts / Recovery</span><span className="value">{report.baseline_avg_attempts}</span></div>
                <div className="kv-item"><span className="label">Total Messages Sent</span><span className="value">{report.baseline_message_count}</span></div>
                <div className="kv-item"><span className="label">Duplicate Charges</span><span className="value" style={{ color: report.baseline_duplicate_charges > 0 ? 'var(--color-danger)' : 'var(--text-primary)'}}>{report.baseline_duplicate_charges}</span></div>
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="glass-card detail-section">
            <h3>📊 Per-Cause Recovery Rate Comparison</h3>
            <div style={{ height: '400px', width: '100%', marginTop: '1rem' }}>
              <ResponsiveContainer>
                <BarChart data={report.per_cause_comparison} layout="vertical" margin={{ top: 20, right: 30, left: 100, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" horizontal={false} />
                  <XAxis type="number" unit="%" stroke="var(--text-muted)" />
                  <YAxis type="category" dataKey="cause" stroke="var(--text-muted)" width={150} tick={{ fontSize: 10 }} />
                  <Tooltip 
                    contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)' }}
                    itemStyle={{ color: 'var(--text-primary)' }}
                  />
                  <Legend />
                  <Bar dataKey="ros_recovery_rate" name="RecoverOS" fill="var(--chart-1)" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="baseline_recovery_rate" name="Baseline" fill="var(--chart-6)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
