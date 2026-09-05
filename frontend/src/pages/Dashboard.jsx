import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDashboardSummary, getOpportunities, getAuditTrail, runFlagshipDemo, generateApprovals } from '../api/client';
import HeroMetrics from '../components/HeroMetrics';
import TrendChart from '../components/TrendChart';
import TopFailureCauses from '../components/TopFailureCauses';
import RecentActionsFeed from '../components/RecentActionsFeed';
import '../styles/dashboard.css';

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [demoRunning, setDemoRunning] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [summary, opps, logs] = await Promise.all([
        getDashboardSummary(),
        getOpportunities(),
        getAuditTrail(1, 10)
      ]);
      setData(summary);
      setOpportunities(opps);
      setAuditLogs(logs);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleRunDemo = async () => {
    setDemoRunning(true);
    try {
      await generateApprovals();
      const result = await runFlagshipDemo();
      await loadData();
      navigate(`/transactions/${result.transaction_id}`);
    } catch (err) {
      alert("Demo failed: " + err.message);
    } finally {
      setDemoRunning(false);
    }
  };

  const formatCurrency = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);

  if (error) {
    return (
      <div className="dashboard-layout animate-in">
        <div className="glass-card" style={{ padding: '2rem', borderColor: 'var(--color-danger)' }}>
          <h2 style={{ color: 'var(--color-danger)' }}>Failed to load dashboard</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="dashboard-layout animate-in">
        <div className="hero-metrics">
          <div className="skeleton" style={{ height: '140px' }} />
          <div className="skeleton" style={{ height: '140px' }} />
          <div className="skeleton" style={{ height: '140px' }} />
          <div className="skeleton" style={{ height: '140px' }} />
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-layout animate-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h1 style={{ fontSize: 'var(--font-size-2xl)', fontWeight: '700', background: 'var(--accent-gradient)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Revenue Radar</h1>
          <p className="text-muted">Real-time recovery intelligence</p>
        </div>
        <button 
          className="btn btn-primary"
          onClick={handleRunDemo}
          disabled={demoRunning}
          style={{ background: 'linear-gradient(135deg, #ec4899, #f43f5e)', boxShadow: '0 0 15px rgba(236, 72, 153, 0.4)' }}
        >
          {demoRunning ? 'Running Demo...' : '🚀 RUN FLAGSHIP DEMO'}
        </button>
      </div>
      
      <HeroMetrics data={data} />

      <div className="dashboard-grid main-charts">
        <div className="glass-card chart-container">
          <TrendChart data={data.daily_trends} />
        </div>
        <div className="glass-card chart-container">
          <TopFailureCauses data={data.top_failure_causes} />
        </div>
      </div>
      
      <div className="dashboard-grid bottom-section" style={{ gridTemplateColumns: '2fr 1fr' }}>
        <div className="glass-card" style={{ padding: 'var(--space-6)' }}>
          <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>🎯</span> Top Recovery Opportunities
          </h3>
          
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Amount</th>
                  <th>Root Cause</th>
                  <th>Action</th>
                  <th>Net Expected</th>
                </tr>
              </thead>
              <tbody>
                {opportunities.length === 0 ? (
                  <tr><td colSpan="5" className="text-muted" style={{textAlign: 'center'}}>No opportunities found</td></tr>
                ) : opportunities.slice(0, 5).map(opp => (
                  <tr key={opp.transaction_id} className="clickable" onClick={() => navigate(`/transactions/${opp.transaction_id}`)}>
                    <td>
                      <div>{opp.customer_name}</div>
                      <div className="text-muted" style={{fontSize: '10px'}}>{opp.customer_segment}</div>
                    </td>
                    <td>{formatCurrency(opp.amount)}</td>
                    <td style={{ textTransform: 'capitalize' }}>{opp.root_cause?.replace(/_/g, ' ')}</td>
                    <td style={{ textTransform: 'capitalize' }}>{opp.recommended_action?.replace(/_/g, ' ')}</td>
                    <td style={{ color: 'var(--color-success)', fontWeight: '600' }}>{formatCurrency(opp.expected_net_recovery)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ textAlign: 'right', marginTop: '1rem' }}>
            <button className="btn btn-secondary" onClick={() => navigate('/transactions')}>View All Transactions →</button>
          </div>
        </div>

        <div className="glass-card chart-container">
          <RecentActionsFeed logs={auditLogs} />
        </div>
      </div>
    </div>
  );
}
