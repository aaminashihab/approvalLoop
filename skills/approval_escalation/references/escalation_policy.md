# Corporate Approval Escalation Policy Reference

## 1. Escalation Hierarchy & SLA Tiers

| State | Default SLA Threshold | Target Recipient | Action Taken |
| :--- | :--- | :--- | :--- |
| **Pending** | 24 hours (30s in demo) | Primary Approver | Autonomous Nudge Notice |
| **Nudged** | 72 hours (90s in demo) | Backup Approver / Director | Autonomous Escalation Notice |
| **Escalated** | Final Escalation | Corporate Admin / Finance Operations | Fail-Closed Admin Notice |
| **Resolved** | Terminal State | None | Inert (Zero Action) |

---

## 2. Backup Approver Resolution Protocol

1. **Explicit Report Override:** If the expense submission explicitly designates an approved backup approver email, use that contact.
2. **Hierarchy Registry Lookup:** If no explicit backup exists, query the corporate `ApproverRegistry` for the primary approver's registered supervisor.
3. **Fail-Closed Admin Fallback:** If neither explicit backup nor supervisor exists, route the escalation to `ADMIN_FALLBACK_EMAIL` (`escalations-owner@company.internal`). Never drop an escalation unhandled.

---

## 3. High-Value Financial Restrictions

- For reports $\ge \$5,000.00$, escalations must target Director-level or Admin authority.
- The Deterministic Policy Engine enforces this rule prior to dispatch (`POL-VAL-02`).

---

## 4. Communication Guidelines for Language Drafter

- **Tone:** Professional, respectful, clear, and unambiguous.
- **Content:** Explicitly state the Report ID, Submitter Name, Amount, Currency, and Reason for escalation (primary approver unresponsiveness).
- **Prohibitions:** Do not include fabricated financial amounts or unauthorized external recipients.
