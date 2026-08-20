import { ExpenseReport, ActionRecord, AutonomyMetrics } from '../types/approval';

const API_BASE = '/api';

export const api = {
  async getReports(): Promise<ExpenseReport[]> {
    const res = await fetch(`${API_BASE}/reports`);
    if (!res.ok) throw new Error('Failed to fetch reports');
    return res.json();
  },

  async getActions(): Promise<ActionRecord[]> {
    const res = await fetch(`${API_BASE}/actions`);
    if (!res.ok) throw new Error('Failed to fetch actions');
    return res.json();
  },

  async getMetrics(): Promise<AutonomyMetrics> {
    const res = await fetch(`${API_BASE}/metrics`);
    if (!res.ok) throw new Error('Failed to fetch autonomy metrics');
    return res.json();
  },

  async triggerTick(): Promise<{ processed_count: number; actions: ActionRecord[] }> {
    const res = await fetch(`${API_BASE}/tick`, {
      method: 'POST',
      headers: { 'X-API-Key': 'dev-scheduler-secret-key' }
    });
    if (!res.ok) throw new Error('Failed to trigger tick');
    return res.json();
  },

  async seedData(): Promise<{ message: string; count: number }> {
    const res = await fetch(`${API_BASE}/seed`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to seed data');
    return res.json();
  },

  async advanceTime(seconds: number = 35): Promise<void> {
    const res = await fetch(`${API_BASE}/demo/advance-time`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds })
    });
    if (!res.ok) throw new Error('Failed to advance time');
  },

  async simulateRace(): Promise<any> {
    const res = await fetch(`${API_BASE}/simulate-race`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to simulate race condition');
    return res.json();
  },

  async simulateAdversarial(): Promise<any> {
    const res = await fetch(`${API_BASE}/simulate-adversarial`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to simulate adversarial proposal');
    return res.json();
  },

  async simulateNotificationFailure(): Promise<any> {
    const res = await fetch(`${API_BASE}/simulate-notification-failure`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to simulate notification failure');
    return res.json();
  },

  async resetDemo(): Promise<any> {
    const res = await fetch(`${API_BASE}/demo/reset`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to reset demo state');
    return res.json();
  },

  async resolveReport(reportId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/reports/${encodeURIComponent(reportId)}/resolve`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to resolve report');
  }
};

