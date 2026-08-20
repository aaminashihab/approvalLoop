import uuid
import logging
from typing import Callable, Optional
from approval_loop.domain.models import NotificationEnvelope, utc_now

logger = logging.getLogger("approval_loop.worker")

class MockNotificationWorker:
    """
    Deterministic Notification Worker (Dispatch Simulator):
    Simulates the provider-side delivery lifecycle, tracking receipt IDs,
    enforcing provider idempotency, logging payload metrics, and supporting
    test fault injection without sending unsolicited emails from test environments.
    """
    def __init__(self):
        self.sent_notifications: list[dict] = []
        self.seen_idempotency_keys: set[str] = set()
        self.simulate_failure = False
        self.on_send_callback: Optional[Callable[[NotificationEnvelope], None]] = None

    def send(self, envelope: NotificationEnvelope, idempotency_key: str) -> tuple[bool, str | None, str | None]:
        if self.simulate_failure:
            logger.warning("Simulated upstream provider timeout for key %s", idempotency_key)
            return False, None, "Simulated upstream provider connection timeout"

        # Provider-side idempotency check
        if idempotency_key in self.seen_idempotency_keys:
            logger.info("Notification key %s already acknowledged by provider (dedup hit)", idempotency_key)
            return True, f"notif_cached_{idempotency_key}", None

        notif_id = f"notif_{uuid.uuid4().hex[:8]}"
        record = {
            "notification_id": notif_id,
            "idempotency_key": idempotency_key,
            "recipient": envelope.recipient,
            "subject": envelope.subject,
            "body": envelope.body_text,
            "amount": str(envelope.amount),
            "report_id": envelope.report_id,
            "sent_at": utc_now().isoformat()
        }
        self.sent_notifications.append(record)
        self.seen_idempotency_keys.add(idempotency_key)
        logger.info("Dispatched notification %s to %s for report %s", notif_id, envelope.recipient, envelope.report_id)

        if self.on_send_callback:
            self.on_send_callback(envelope)

        return True, notif_id, None
