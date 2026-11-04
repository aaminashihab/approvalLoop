import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, isAuthError } from '../api/client';
import {
  ActionRecord, AgentRegistration, AutonomyMetrics, ExpenseReport, PendingAction, WorkflowMemoryRecord,
} from '../types/approval';

const POLL_MS = 5000;

/**
 * One API read. `data` is null until the first success (the view shows a loading state).
 * When a later read fails, the last good `data` is kept but `error` is set, so the view must
 * label it as possibly out of date instead of presenting it as current.
 */
export interface Source<T> {
  data: T | null;
  error: ApiError | null;
  updatedAt: number | null;
}

export interface ConsoleData {
  pending: Source<PendingAction[]>;
  workflows: Source<WorkflowMemoryRecord[]>;
  metrics: Source<AutonomyMetrics>;
  agents: Source<AgentRegistration[]>;
  reports: Source<ExpenseReport[]>;
  actions: Source<ActionRecord[]>;
}

export const SOURCE_LABEL: Record<keyof ConsoleData, string> = {
  pending: 'approval queue',
  workflows: 'workflow history',
  metrics: 'reminder counters',
  agents: 'agent registry',
  reports: 'expense reports',
  actions: 'reminder log',
};

const blank = <T,>(): Source<T> => ({ data: null, error: null, updatedAt: null });

const INITIAL: ConsoleData = {
  pending: blank(), workflows: blank(), metrics: blank(), agents: blank(), reports: blank(), actions: blank(),
};

function settle<T>(prev: Source<T>, r: PromiseSettledResult<T>, now: number): Source<T> {
  if (r.status === 'fulfilled') return { data: r.value, error: null, updatedAt: now };
  const error = r.reason instanceof ApiError ? r.reason : new ApiError(0, 'The response could not be read.');
  return { ...prev, error };
}

export function useConsoleData() {
  const [data, setData] = useState<ConsoleData>(INITIAL);
  const [authFailed, setAuthFailed] = useState(false);
  const seq = useRef(0);
  const applied = useRef(0);

  const refresh = useCallback(async () => {
    const mine = ++seq.current;
    // Each source fails independently: one broken endpoint never blanks the others.
    const r = await Promise.allSettled([
      api.getPendingActions(), api.getWorkflows(), api.getMetrics(),
      api.getAgents(), api.getReports(), api.getActions(),
    ] as const);
    // A slower, older poll must never overwrite a newer result.
    if (mine < applied.current) return;
    applied.current = mine;
    const now = Date.now();
    setData((p) => ({
      pending: settle(p.pending, r[0], now),
      workflows: settle(p.workflows, r[1], now),
      metrics: settle(p.metrics, r[2], now),
      agents: settle(p.agents, r[3], now),
      reports: settle(p.reports, r[4], now),
      actions: settle(p.actions, r[5], now),
    }));
    setAuthFailed(r.some((x) => x.status === 'rejected' && isAuthError(x.reason)));
  }, []);

  // Poll every 5 s while the tab is visible; pause while hidden and catch up as soon as it is shown.
  useEffect(() => {
    let timer: number | undefined;
    let running = false;
    let stopped = false;

    const tick = async () => {
      timer = undefined;
      if (stopped || document.hidden) return;
      running = true;
      await refresh();
      running = false;
      if (!stopped && !document.hidden) timer = window.setTimeout(tick, POLL_MS);
    };
    const onVisibility = () => {
      if (!document.hidden && !running && timer === undefined) void tick();
    };

    void tick();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [refresh]);

  return { data, authFailed, refresh };
}
