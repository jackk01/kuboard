from django.test import TestCase

from apps.audit.models import AuditEvent


class AuditEventTests(TestCase):
    def test_audit_event_defaults(self):
        event = AuditEvent.objects.create(event_type="system.health")
        self.assertEqual(event.status, "success")

