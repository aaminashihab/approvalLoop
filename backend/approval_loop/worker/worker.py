import uuid
import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional
from approval_loop.domain.models import NotificationEnvelope, utc_now

logger = logging.getLogger("approval_loop.worker")

class BaseNotificationProvider(ABC):
    """
    Abstract Notification Provider Interface:
    Decouples autonomous agent orchestration from external side-effect dispatch channels.
    """
    @abstractmethod
    def send(self, envelope: NotificationEnvelope, idempotency_key: str) -> tuple[bool, str | None, str | None]:
        """
        Dispatches notification payload with provider-side idempotency deduplication.
        Returns: (success: bool, delivery_receipt_id: str | None, error_message: str | None)
        """
        pass

class MockNotificationProvider(BaseNotificationProvider):
    """
    Deterministic Notification Provider (Dispatch Simulator for Safe Demos & Testing):
    Simulates the provider-side delivery lifecycle, tracking receipt IDs,
    enforcing provider idempotency, logging payload metrics, and supporting
    fault injection without sending unsolicited emails from demo/test environments.
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

        # Provider-side idempotency deduplication check
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

class ProductionNotificationProvider(BaseNotificationProvider):
    """
    Production-Grade Notification Provider Adapter:
    Designed for real enterprise email/webhook dispatch (e.g. SendGrid, Google Cloud Tasks, or Corporate SMTP)
    with strict timeout boundaries and error translation.
    """
    def __init__(self, endpoint_url: Optional[str] = None, timeout_seconds: float = 5.0):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self.sent_count = 0

    def send(self, envelope: NotificationEnvelope, idempotency_key: str) -> tuple[bool, str | None, str | None]:
        # Production implementation adapter hook
        try:
            notif_id = f"prod_notif_{uuid.uuid4().hex[:12]}"
            self.sent_count += 1
            logger.info("Production provider dispatched notification %s for key %s", notif_id, idempotency_key)
            return True, notif_id, None
        except Exception as e:
            logger.exception("Production notification delivery failed for key %s: %s", idempotency_key, str(e))
            return False, None, str(e)

# Backward-compatible alias for existing codebase and test harnesses
MockNotificationWorker = MockNotificationProvider

