import { useEffect, useState } from 'react';
import { credentials, isAuthError } from './api/client';
import { NAV, Shell, ViewId } from './components/Shell';
import { clockTime } from './lib/format';
import { ConsoleData, SOURCE_LABEL, useConsoleData } from './lib/useConsoleData';
import { ApprovalsView } from './views/ApprovalsView';
import { ActivityView } from './views/ActivityView';
import { AgentsView } from './views/AgentsView';
import { ExpensesView } from './views/ExpensesView';
import { SandboxView } from './views/SandboxView';

const viewFromHash = (): ViewId => {
  const h = window.location.hash.replace(/^#/, '');
  return NAV.some((n) => n.id === h) ? (h as ViewId) : 'approvals';
};

/** Describes failed reads (other than auth, which the key prompt covers) without hiding anything. */
function connectionProblem(data: ConsoleData): { title: string; detail: string } | null {
  const keys = Object.keys(data) as (keyof ConsoleData)[];
  const failing = keys.filter((k) => data[k].error && !isAuthError(data[k].error));
  if (failing.length === 0) return null;
  const confirmed = keys.map((k) => data[k].updatedAt).filter((t): t is number => t !== null);
  const since = confirmed.length ? ` Data on screen was last confirmed at ${clockTime(Math.min(...confirmed))} and may be out of date.` : '';
  const reason = data[failing[0]].error?.message ?? '';
  if (failing.every((k) => data[k].error?.status === 0)) {
    return { title: 'Cannot reach the ApprovalLoop server.', detail: `${since} Retrying every 5 seconds.`.trim() };
  }
  return failing.length === keys.length
    ? { title: 'Nothing could be refreshed from the server.', detail: `${reason}${since} Retrying every 5 seconds.` }
    : {
        title: `Could not refresh the ${failing.map((k) => SOURCE_LABEL[k]).join(', ')}.`,
        detail: `${reason}${since} Retrying every 5 seconds.`,
      };
}

export default function App() {
  const [view, setView] = useState<ViewId>(viewFromHash);
  const [hasKey, setHasKey] = useState(() => credentials.get() !== null);
  const [keyFormRequested, setKeyFormRequested] = useState(false);
  const { data, authFailed, refresh } = useConsoleData();

  useEffect(() => {
    const onHash = () => {
      setView(viewFromHash());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    const label = NAV.find((n) => n.id === view)?.label ?? '';
    const n = data.pending.data?.length ?? 0;
    document.title = `${n > 0 ? `(${n}) ` : ''}${label} · ApprovalLoop`;
  }, [view, data.pending.data]);

  const saveKey = (key: string) => {
    credentials.set(key);
    setHasKey(true);
    setKeyFormRequested(false);
    void refresh();
  };
  const forgetKey = () => {
    credentials.clear();
    setHasKey(false);
    void refresh();
  };

  return (
    <Shell
      view={view}
      pendingCount={data.pending.data ? data.pending.data.length : null}
      hasKey={hasKey}
      keyRejected={authFailed}
      showKeyForm={authFailed || keyFormRequested}
      onOpenKeyForm={() => setKeyFormRequested(true)}
      onSaveKey={saveKey}
      onForgetKey={forgetKey}
      connection={connectionProblem(data)}
    >
      {view === 'approvals' && <ApprovalsView pending={data.pending} agents={data.agents} refresh={refresh} />}
      {view === 'activity' && <ActivityView workflows={data.workflows} metrics={data.metrics} />}
      {view === 'agents' && <AgentsView agents={data.agents} />}
      {view === 'expenses' && <ExpensesView reports={data.reports} actions={data.actions} refresh={refresh} />}
      {view === 'sandbox' && <SandboxView refresh={refresh} />}
    </Shell>
  );
}
