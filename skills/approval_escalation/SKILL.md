---
name: approval_escalation
description: Reusable procedural guidance for identifying stalled human approvals, resolving hierarchy contacts, and safely escalating without breaching authorization boundaries.
trigger_conditions:
  - An expense report or access request exceeds its initial nudge SLA threshold.
  - The primary approver is inactive, out of office, or unresponsive.
  - An automated escalation notice needs to be drafted with contextual precision.
when_not_to_trigger:
  - The expense report is still within its initial review SLA window (fresh).
  - The expense report has already been resolved or signed off.
  - An active escalation action is already in flight (idempotency claim active).
---

# Approval Escalation Skill

## Overview
This skill provides procedural know-how for handling stalled approvals in human workflows.

> **CRITICAL BOUNDARY**: This skill supplies language drafting and procedural sequence guidance. It **NEVER** overrides deterministic code for eligibility, recipient selection, amount calculation, or state machine transitions.

---

## Procedural Workflow

```
1. Observe Approval State & Elapsed Time
       ↓
2. Determine Stale Threshold Violation (Code)
       ↓
3. Transactional Claim before Drafting (Outbox)
       ↓
4. Retrieve Designated Backup from Approver Registry (Code)
       ↓
5. Draft Contextual Escalation Language (Gemini 3.5 Flash)
       ↓
6. Deterministic 4-Point Safety Validation (Code)
       ↓
7. Corporate Governance Policy Check (Code)
       ↓
8. Dispatch Escalation Notification (Worker)
       ↓
9. Conditional State Transition Guard (Code)
```

---

## Detailed Policy References
For corporate escalation SLAs, high-value financial thresholds, and admin fallback rules, see [references/escalation_policy.md](file:///d:/hackathon/skills/approval_escalation/references/escalation_policy.md).
