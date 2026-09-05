import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  getTransactionDetail, 
  getWhatIfAnalysis, 
  getCustomerIntelligence, 
  executeAction 
} from '../api/client';
import '../styles/pages.css';

export default function TransactionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  
  const [txn, setTxn] = useState(null);
  const [customer, setCustomer] = useState(null);
  const [whatIf, setWhatIf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Pipeline State
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState(0);
  
  // Execution State
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState(null);

  const formatCurrency = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const txnData = await getTransactionDetail(id);
        setTxn(txnData);
        
        if (txnData.customer?.id) {
          const custData = await getCustomerIntelligence(txnData.customer.id);
          setCustomer(custData);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const runAnalysis = async () => {
    setAnalyzing(true);
    setAnalysisStep(1); // Payment retrieved
    await new Promise(r => setTimeout(r, 600));
    
    setAnalysisStep(2); // Customer history analyzed
    await new Promise(r => setTimeout(r, 600));
    
    setAnalysisStep(3); // Root cause identified
    await new Promise(r => setTimeout(r, 600));
    
    setAnalysisStep(4); // Recovery probability
    await new Promise(r => setTimeout(r, 800));
    
    setAnalysisStep(5); // Strategies evaluated
    try {
      const whatIfData = await getWhatIfAnalysis(id);
      setWhatIf(whatIfData);
    } catch (err) {
      console.error("What-if failed:", err);
    }
    await new Promise(r => setTimeout(r, 600));
    
    setAnalysisStep(6); // Policy checked & Best action selected
    setAnalyzing(false);
  };

  const handleExecute = async (actionType) => {
    setExecuting(true);
    try {
      const result = await executeAction(id, actionType);
      setExecResult(result);
      
      // Reload txn to get updated status
      const txnData = await getTransactionDetail(id);
      setTxn(txnData);
    } catch (err) {
      alert("Execution failed: " + err.message);
    } finally {
      setExecuting(false);
    }
  };

  if (loading) {
    return <div className="page-container"><div className="skeleton" style={{height: '400px'}}></div></div>;
  }

  if (error || !txn) {
    return (
      <div className="page-container">
        <div className="glass-card detail-section" style={{ borderColor: 'var(--color-danger)' }}>
          <h3 style={{ color: 'var(--color-danger)' }}>Error Loading Transaction</h3>
          <p>{error || "Transaction not found"}</p>
          <button className="btn btn-secondary" onClick={() => navigate('/transactions')} style={{marginTop: '1rem'}}>
            Back to Transactions
          </button>
        </div>
      </div>
    );
  }

  const bestAction = whatIf?.candidates ? whatIf.candidates.find(w => w.is_recommended) : null;
  const isFailed = txn.status === 'failed';

  return (
    <div className="page-container animate-in">
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate('/transactions')} style={{marginBottom: '1rem'}}>
            ← Back
          </button>
          <h1 className="page-title">Transaction Intelligence</h1>
          <div className="page-subtitle" style={{ fontFamily: 'var(--font-mono)' }}>{txn.external_id}</div>
        </div>
        
        {isFailed && !analyzing && analysisStep === 0 && (
          <button className="btn btn-primary" onClick={runAnalysis}>
            ⚡ RUN AI ANALYSIS
          </button>
        )}
      </div>

      <div className="intel-grid">
        {/* Left Column: Context */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          
          <div className="glass-card detail-section">
            <h3>💳 Payment Details</h3>
            <div className="kv-list">
              <div className="kv-item"><span className="label">Amount</span><span className="value">{formatCurrency(txn.amount)}</span></div>
              <div className="kv-item"><span className="label">Method</span><span className="value" style={{ textTransform: 'capitalize' }}>{txn.payment_method}</span></div>
              <div className="kv-item"><span className="label">Status</span>
                <span className={`badge status-${txn.status.toLowerCase()}`}>{txn.status.replace('_', ' ')}</span>
              </div>
              <div className="kv-item"><span className="label">Failure Code</span><span className="value">{txn.failure_code}</span></div>
              <div className="kv-item"><span className="label">Reason</span><span className="value">{txn.failure_reason}</span></div>
              <div className="kv-item"><span className="label">Timestamp</span><span className="value">{new Date(txn.timestamp).toLocaleString()}</span></div>
            </div>
          </div>

          {customer && (
            <div className="glass-card detail-section">
              <h3>👤 Customer Context</h3>
              <div className="kv-list">
                <div className="kv-item"><span className="label">Name</span><span className="value">{customer.name}</span></div>
                <div className="kv-item"><span className="label">Segment</span>
                  <span className="badge" style={{ background: 'rgba(255,255,255,0.1)'}}>{customer.segment}</span>
                </div>
                <div className="kv-item"><span className="label">LTV</span><span className="value">{formatCurrency(customer.ltv)}</span></div>
                <div className="kv-item"><span className="label">Prev. Transactions</span><span className="value">{customer.previous_transactions}</span></div>
                <div className="kv-item"><span className="label">Success Rate</span>
                  <span className="value" style={{ color: customer.success_rate > 80 ? 'var(--color-success)' : 'var(--text-primary)'}}>
                    {customer.success_rate}%
                  </span>
                </div>
                <div className="kv-item"><span className="label">Pref. Channel</span><span className="value" style={{ textTransform: 'capitalize' }}>{customer.preferred_channel}</span></div>
              </div>
            </div>
          )}

        </div>

        {/* Right Column: AI Analysis */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          
          {(analyzing || analysisStep > 0) && (
            <div className="glass-card detail-section">
              <h3>🧠 Recovery Intelligence</h3>
              
              <div className="analysis-pipeline">
                <div className={`pipeline-step ${analysisStep >= 1 ? 'completed' : 'pending'}`}>
                  <div className="step-icon">✓</div>
                  <div className="step-content">
                    <div className="step-title">Payment & Customer Retrieved</div>
                  </div>
                </div>
                
                <div className={`pipeline-step ${analysisStep >= 2 ? 'completed' : analysisStep === 1 ? 'active' : 'pending'}`}>
                  <div className="step-icon">{analysisStep >= 2 ? '✓' : '⚙'}</div>
                  <div className="step-content">
                    <div className="step-title">Customer History Analyzed</div>
                    {analysisStep >= 2 && <div className="step-detail">Success rate: {customer?.success_rate}%, LTV: {formatCurrency(customer?.ltv || 0)}</div>}
                  </div>
                </div>

                <div className={`pipeline-step ${analysisStep >= 3 ? 'completed' : analysisStep === 2 ? 'active' : 'pending'}`}>
                  <div className="step-icon">{analysisStep >= 3 ? '✓' : '🔍'}</div>
                  <div className="step-content">
                    <div className="step-title">Root Cause Diagnosed</div>
                    {analysisStep >= 3 && <div className="step-detail" style={{ color: 'var(--text-accent)' }}>{txn.root_cause || "Analyzing error semantics..."}</div>}
                  </div>
                </div>

                <div className={`pipeline-step ${analysisStep >= 4 ? 'completed' : analysisStep === 3 ? 'active' : 'pending'}`}>
                  <div className="step-icon">{analysisStep >= 4 ? '✓' : '📈'}</div>
                  <div className="step-content">
                    <div className="step-title">Recovery Probability Predicted</div>
                  </div>
                </div>

                <div className={`pipeline-step ${analysisStep >= 5 ? 'completed' : analysisStep === 4 ? 'active' : 'pending'}`}>
                  <div className="step-icon">{analysisStep >= 5 ? '✓' : '⚖'}</div>
                  <div className="step-content">
                    <div className="step-title">Candidate Strategies Evaluated</div>
                    {whatIf?.candidates && <div className="step-detail">{whatIf.candidates.length} actions ranked by net expected utility</div>}
                  </div>
                </div>

                <div className={`pipeline-step ${analysisStep >= 6 ? 'completed' : analysisStep === 5 ? 'active' : 'pending'}`}>
                  <div className="step-icon">{analysisStep >= 6 ? '✓' : '🛡'}</div>
                  <div className="step-content">
                    <div className="step-title">Merchant Policy Checked</div>
                    {bestAction && <div className="step-detail">{bestAction.requires_approval ? "Requires human approval" : "Auto-execution permitted"}</div>}
                  </div>
                </div>
              </div>

              {analysisStep === 6 && bestAction && (
                <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(99, 102, 241, 0.1)', borderRadius: 'var(--radius-md)', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                  <h4 style={{ color: 'var(--accent-primary)', marginBottom: '0.5rem' }}>Recommended Action</h4>
                  <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: '700', marginBottom: '1rem', textTransform: 'capitalize' }}>
                    {bestAction.action_type.replace(/_/g, ' ')}
                  </div>
                  
                  <div className="kv-list" style={{ marginBottom: '1rem' }}>
                    <div className="kv-item"><span className="label">Recovery Probability</span><span className="value" style={{ color: 'var(--color-success)'}}>{(bestAction.recovery_probability * 100).toFixed(1)}%</span></div>
                    <div className="kv-item"><span className="label">Expected Net Revenue</span><span className="value">{formatCurrency(bestAction.net_expected_revenue)}</span></div>
                    <div className="kv-item"><span className="label">Cost</span><span className="value" style={{ color: 'var(--color-danger)'}}>{formatCurrency(bestAction.communication_cost)}</span></div>
                  </div>

                  <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginBottom: '1.5rem', fontStyle: 'italic' }}>
                    "{whatIf.decision_explanation || `Highest net expected value. Probability: ${(bestAction.recovery_probability*100).toFixed(0)}%.`}"
                  </div>

                  {!execResult ? (
                    <button 
                      className="btn btn-primary" 
                      style={{ width: '100%', padding: '0.75rem' }}
                      onClick={() => handleExecute(bestAction.action_type)}
                      disabled={executing || !isFailed}
                    >
                      {executing ? "Executing..." : (bestAction.requires_approval ? "Request Approval" : `Execute ${bestAction.action_type.replace(/_/g, ' ')}`)}
                    </button>
                  ) : (
                    <div style={{ padding: '0.75rem', background: 'var(--color-success-bg)', color: 'var(--color-success)', borderRadius: 'var(--radius-md)', textAlign: 'center', fontWeight: '600' }}>
                      {execResult.status === 'executed' ? 'Action Executed Successfully' : `Status: ${execResult.status}`}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {whatIf?.candidates && analysisStep === 6 && (
            <div className="glass-card detail-section">
              <h3>📊 What-If Simulation</h3>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Prob</th>
                      <th>Net Exp.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {whatIf.candidates.map((w, idx) => (
                      <tr key={idx} style={{ background: w.is_recommended ? 'rgba(99, 102, 241, 0.1)' : 'transparent' }}>
                        <td style={{ textTransform: 'capitalize' }}>
                          {w.action_type.replace(/_/g, ' ')}
                          {w.is_recommended && <span style={{ marginLeft: '8px' }}>⭐</span>}
                        </td>
                        <td>{(w.recovery_probability * 100).toFixed(1)}%</td>
                        <td>{formatCurrency(w.net_expected_revenue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
