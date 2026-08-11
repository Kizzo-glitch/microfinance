"""
Fedha-Grow — pending messaging adapter
======================================
Honest placeholder for messaging channels (SMS, WhatsApp) before a real gateway
is configured. A pending messaging adapter reports the channel is not connected
and never claims a message was sent.
"""

_PENDING_MSG = (
    "{label} channel is provisioned but not yet connected. "
    "Awaiting provider credentials."
)


class PendingMessagingAdapter:
    provider_name = "pending-messaging"

    def __init__(self, provider_name: str, label: str):
        self.provider_name = provider_name
        self.label = label

    def send(self, destination_number: str, message_content: str) -> dict:
        return {"success": False,
                "error": _PENDING_MSG.format(label=self.label),
                "pending": True}