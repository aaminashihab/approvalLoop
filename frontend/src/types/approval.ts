export interface ExpenseReport {
  report_id: string;
  status: 'Pending' | 'Nudged' | 'Escalated' | 'Resolved';
  submitter_name: string;
  submitter_email: string;
  approver_email: string;
  backup_approver_email?: string | null;
  amount: string;
  currency: string;
  description: string;
  submitted_at: string;
  last_nudged_at?: string | null;
  escalated_at?: string | null;
  resolved_at?: string | null;
}

export interface NotificationEnvelope {
  report_id: string;
  amount: string;
  currency: string;
  recipient: string;
  submitter_name: string;
  subject: string;
  body_text: string;
}

export interface ValidatorChecks {
  recipient_verified: boolean;
  report_id_verified: boolean;
  amount_verified: boolean;
  state_verified: boolean;
}

export interface ActionRecord {
  action_id: string;
  report_id: string;
  action_type: 'nudge' | 'escalate';
  source_state: 'Pending' | 'Nudged' | 'Escalated' | 'Resolved';
  target_state: 'Pending' | 'Nudged' | 'Escalated' | 'Resolved';
  tick_id: string;
  idempotency_key: string;
  recipient: string;
  amount: string;
  status: 'claimed' | 'processing' | 'sent' | 'completed' | 'failed' | 'blocked';
  created_at: string;
  claimed_at?: string | null;
  attempt_count: number;
  max_attempts: number;
  last_error?: string | null;
  message?: string | null;
  validator_result?: 'pass' | 'blocked' | null;
  validator_reason?: string | null;
  validator_checks?: ValidatorChecks | null;
  sent_at?: string | null;
  notification_id?: string | null;
  state_transition?: 'applied' | 'skipped' | null;
  skip_reason?: string | null;
  completed_at?: string | null;
  envelope?: NotificationEnvelope | null;
}

export interface AutonomyMetrics {
  last_wake_up?: string | null;
  reports_observed: number;
  eligible_reports: number;
  actions_claimed: number;
  notifications_sent: number;
  escalations_count: number;
  blocked_actions_count: number;
  duplicate_actions_prevented: number;
  unsafe_transitions_prevented: number;
  human_prompts_required: number;
}
