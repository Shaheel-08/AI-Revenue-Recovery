/**
 * RecoverOS API Client
 *
 * Thin fetch wrapper for all backend endpoints.
 * Field names match docs/api_contract.md exactly.
 */

const API_BASE = 'http://localhost:8000';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Dashboard ──────────────────────────────────────────────────────────

export function getDashboardSummary(merchantId = 1) {
  return request(`/dashboard/summary?merchant_id=${merchantId}`);
}

export function getTransactions({ merchantId = 1, status, rootCause, limit = 50, offset = 0 } = {}) {
  let url = `/dashboard/transactions?merchant_id=${merchantId}&limit=${limit}&offset=${offset}`;
  if (status) url += `&status=${status}`;
  if (rootCause) url += `&root_cause=${rootCause}`;
  return request(url);
}

// ── Recovery / Transaction Detail ──────────────────────────────────────

export function getTransactionDetail(transactionId) {
  return request(`/transactions/${transactionId}`);
}

export function getWhatIfAnalysis(transactionId) {
  return request(`/transactions/${transactionId}/whatif`);
}

export function executeAction(transactionId, actionType = null, force = false) {
  return request(`/transactions/${transactionId}/execute`, {
    method: 'POST',
    body: JSON.stringify({ action_type: actionType, force }),
  });
}

export function recordOutcome(transactionId, { recovered, revenueRecovered = 0, cost = 0, timeToRecoveryHours = null }) {
  let url = `/transactions/${transactionId}/outcome?recovered=${recovered}&revenue_recovered=${revenueRecovered}&cost=${cost}`;
  if (timeToRecoveryHours !== null) url += `&time_to_recovery_hours=${timeToRecoveryHours}`;
  return request(url, { method: 'POST' });
}

// ── Approvals ──────────────────────────────────────────────────────────

export function getPendingApprovals(merchantId = 1) {
  return request(`/approvals/pending?merchant_id=${merchantId}`);
}

export function decideApproval(approvalId, { approved, decidedBy = 'merchant_admin', reason = '' }) {
  return request(`/approvals/${approvalId}/decision`, {
    method: 'POST',
    body: JSON.stringify({ approved, decided_by: decidedBy, reason }),
  });
}

// ── Policy ─────────────────────────────────────────────────────────────

export function getPolicy(merchantId = 1) {
  return request(`/policy?merchant_id=${merchantId}`);
}

export function updatePolicy(config, merchantId = 1) {
  return request(`/policy?merchant_id=${merchantId}`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

// ── Simulation / Batch Evaluation ──────────────────────────────────────

export function runBatchEvaluation({ transactionCount = 2000, seed = 42 } = {}) {
  return request('/simulate/batch', {
    method: 'POST',
    body: JSON.stringify({ transaction_count: transactionCount, seed }),
  });
}

// ── Webhooks (for testing) ─────────────────────────────────────────────

export function sendPaymentFailed(payload) {
  return request('/webhooks/payment-failed', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ── New Dashboard Endpoints ────────────────────────────────────────────

export function getOpportunities(merchantId = 1, limit = 10) {
  return request(`/dashboard/opportunities?merchant_id=${merchantId}&limit=${limit}`);
}

export function getAuditTrail(merchantId = 1, limit = 30) {
  return request(`/dashboard/audit?merchant_id=${merchantId}&limit=${limit}`);
}

// ── Customers ──────────────────────────────────────────────────────────

export function getCustomerIntelligence(customerId) {
  return request(`/customers/${customerId}`);
}

// ── Demo ───────────────────────────────────────────────────────────────

export function runFlagshipDemo() {
  return request('/demo/flagship', { method: 'POST' });
}

export function generateApprovals() {
  return request('/demo/generate-approvals', { method: 'POST' });
}
