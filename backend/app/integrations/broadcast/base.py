from abc import ABC, abstractmethod


class BroadcastProvider(ABC):
    """Sends one campaign to a whole segment of contacts held by the mail provider (Resend Contacts, Segments and Broadcasts).
    The provider owns the unsubscribe link and the list of people who unsubscribed."""

    @abstractmethod
    async def ensure_segment(self, name: str) -> str:
        """The id of the segment campaigns are sent to; created when it does not exist yet."""

    @abstractmethod
    async def add_contact(self, email: str, first_name: str, segment_id: str) -> None:
        """Put one person in the provider's contacts (if new) and in the segment. Never clears an unsubscribe the provider recorded."""

    @abstractmethod
    async def remove_contact(self, email: str, segment_id: str) -> None:
        """Take one person out of the segment (they stay a contact)."""

    @abstractmethod
    async def send(self, segment_id: str, name: str, subject: str, html: str, text: str) -> str:
        """Create the broadcast and send it now. Returns the provider's id for it."""

    @abstractmethod
    async def status(self, broadcast_id: str) -> str:
        """draft | queued | sent (the provider's word for it)."""
