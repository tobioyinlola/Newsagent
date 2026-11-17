from app.integrations.broadcast.base import BroadcastProvider


class MockBroadcast(BroadcastProvider):
    """Records what would go to the provider; broadcasts count as sent straight away."""

    def __init__(self) -> None:
        self.segments: dict[str, set[str]] = {}
        self.names: dict[str, str] = {}
        self.contacts: dict[str, str] = {}  # email -> first name
        self.broadcasts: list[dict] = []
        self.fail_add: set[str] = set()
        self.status_value = "sent"

    async def ensure_segment(self, name: str) -> str:
        for sid, n in self.names.items():
            if n == name:
                return sid
        sid = f"seg_{len(self.names) + 1}"
        self.names[sid], self.segments[sid] = name, set()
        return sid

    async def add_contact(self, email: str, first_name: str, segment_id: str) -> None:
        if email in self.fail_add:
            raise RuntimeError("provider refused the contact")
        self.contacts.setdefault(email, first_name)
        self.segments[segment_id].add(email)

    async def remove_contact(self, email: str, segment_id: str) -> None:
        self.segments[segment_id].discard(email)

    async def send(self, segment_id: str, name: str, subject: str, html: str, text: str) -> str:
        bid = f"bc_{len(self.broadcasts) + 1}"
        self.broadcasts.append(
            {
                "id": bid,
                "segment_id": segment_id,
                "to": sorted(self.segments[segment_id]),
                "name": name,
                "subject": subject,
                "html": html,
                "text": text,
            }
        )
        return bid

    async def status(self, broadcast_id: str) -> str:
        return self.status_value
