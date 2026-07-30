"""In-process storage adapter for booking conversation contexts."""

from app.domain.booking_context import BookingContext


class MemoryCache:
    """Stores booking contexts in memory by conversation identifier."""

    def __init__(self) -> None:
        self._contexts: dict[str, BookingContext] = {}

    async def get(self, conversation_id: str) -> BookingContext | None:
        """Return a stored context without creating one."""
        return self._contexts.get(conversation_id)

    async def save(self, context: BookingContext) -> None:
        """Store or replace a context using its conversation identifier."""
        self._contexts[context.conversation_id] = context

    async def delete(self, conversation_id: str) -> None:
        """Delete a context when it exists."""
        self._contexts.pop(conversation_id, None)

    async def get_or_create(self, conversation_id: str) -> BookingContext:
        """Return a stored context or create and store a new one."""
        context = self._contexts.get(conversation_id)
        if context is None:
            context = BookingContext(conversation_id=conversation_id)
            self._contexts[conversation_id] = context
        return context

    def __len__(self) -> int:
        """Return the number of stored contexts."""
        return len(self._contexts)
