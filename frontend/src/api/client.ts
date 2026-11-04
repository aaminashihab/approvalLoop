import {
  ActionProposal, ActionRecord, AgentRegistration, AutonomyMetrics, ExpenseReport,
  GatewayDecision, HumanDecisionResponse, PendingAction, WorkflowMemoryRecord,
} from '../types/approval';

const API_BASE = '/api';
const KEY_STORAGE = 'approvalloop.operatorKey';

/** An HTTP failure carrying the server's own `detail` message. Status 0 means the server was unreachable. */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export const isAuthError = (e: unknown): boolean =>
  e instanceof ApiError && (e.status === 401 || e.status === 403);

export const errorMessage = (e: unknown): string =>
  e instanceof ApiError ? e.message : 'Something went wrong in the browser. Nothing was sent.';

/**
 * The operator key lives in sessionStorage only: it is cleared when the tab closes and is never
 * written to source, the bundle, or localStorage.
 */
export const credentials = {
  get(): string | null {
    try { return sessionStorage.getItem(KEY_STORAGE); } catch { return null; }
  },
  set(key: string): void {
    try { sessionStorage.setItem(KEY_STORAGE, key); } catch { /* storage unavailable: key is not kept */ }
  },
  clear(): void {
    try { sessionStorage.removeItem(KEY_STORAGE); } catch { /* storage unavailable */ }
  },
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  const key = credentials.get();
  if (key) headers.set('X-API-Key', key);
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, 'The server could not be reached.');
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body: unknown = await res.json();
      if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') detail = body.detail;
    } catch { /* error body was not JSON */ }
    throw new ApiError(res.status, detail || `The server answered ${res.status} ${res.statusText}`.trim() + '.');
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

const id = (s: string) => encodeURIComponent(s);

export interface ScenarioResult {
  scenario: string;
  expected_outcome: string;
  proposal: ActionProposal;
  decision: GatewayDecision;
}

export const api = {
  getPendingActions: () => request<PendingAction[]>('/gateway/actions/pending'),
  getWorkflows: () => request<WorkflowMemoryRecord[]>('/memory/workflows'),
  getMetrics: () => request<AutonomyMetrics>('/metrics'),
  getAgents: () => request<AgentRegistration[]>('/registry/agents'),
  getReports: () => request<ExpenseReport[]>('/reports'),
  getActions: () => request<ActionRecord[]>('/actions'),

  // The body carries notes only. The server derives the approver's identity from the credential.
  approveAction: (actionId: string, notes: string) =>
    post<HumanDecisionResponse>(`/gateway/actions/${id(actionId)}/approve`, { notes }),
  rejectAction: (actionId: string, notes: string) =>
    post<HumanDecisionResponse>(`/gateway/actions/${id(actionId)}/reject`, { notes }),

  resolveReport: (reportId: string) => post<{ message: string }>(`/reports/${id(reportId)}/resolve`),
  runTick: () => post<{ processed_count: number }>('/tick'),

  // Sandbox only: the server answers 404 for all of these in production.
  runScenario: (kind: 'a' | 'b' | 'c') => post<ScenarioResult>(`/demo/scenario-${kind}`),
  seed: () => post<{ message: string }>('/seed'),
  advanceTime: (seconds: number) => post<{ message: string }>('/demo/advance-time', { seconds }),
  reset: () => post<{ message: string }>('/demo/reset'),
  simulateRace: () => post<{ scenario: string }>('/simulate-race'),
  simulateAdversarial: () => post<{ scenario: string }>('/simulate-adversarial'),
  simulateNotificationFailure: () => post<{ scenario: string }>('/simulate-notification-failure'),
};
