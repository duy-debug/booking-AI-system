"""Assemble and own the application's runtime dependency graph."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx

from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.collect_customer_handler import CollectCustomerHandler
from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_service_handler import SearchServiceHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.application.ports.booking_gateway import BookingGateway
from app.core.config import Settings
from app.dialog.dialog_controller import DialogController
from app.dialog.entity_resolution import EntityResolutionCoordinator
from app.dialog.flow_loader import FlowDefinition, FlowLoader
from app.dialog.instruction_builder import InstructionBuilder
from app.dialog.nlu import (
    DeterministicNLU,
    StateIntentPolicy,
    build_state_intent_policy,
)
from app.dialog.state_machine import StateMachine
from app.dialog.tool_bridge import ToolBridge
from app.domain.booking_context import BookingContext
from app.infrastructure.booking_api.http_booking_gateway import HTTPBookingGateway
from app.infrastructure.cache.memory_cache import MemoryCache

_MAX_CONVERSATION_ID_LENGTH = 128
_RAW_PHONE_PATTERN = re.compile(r"\+?\d{9,15}")


class ConversationContextError(Exception):
    """Base error for conversation context lifecycle failures."""


class InvalidConversationIdError(ConversationContextError):
    """Raised when a conversation identifier is unsafe or malformed."""


class InvalidCachedContextError(ConversationContextError):
    """Raised when cached data violates the booking-context contract."""


class InvalidConversationContextError(ConversationContextError):
    """Raised when a context cannot be saved under the supplied identifier."""


class ConversationContextStore:
    """Coordinates booking-context persistence in the in-process cache."""

    def __init__(self, *, cache: MemoryCache) -> None:
        self._cache = cache

    async def get_or_create(self, conversation_id: str) -> BookingContext:
        """Load a context or create and store an idle context on a cache miss."""
        normalized_id = _validate_conversation_id(conversation_id)
        context = await self._cache.get(normalized_id)
        if context is None:
            context = BookingContext(conversation_id=normalized_id)
            await self._cache.save(context)
            return context
        if not isinstance(context, BookingContext):
            raise InvalidCachedContextError(
                "Cached conversation data must be a BookingContext."
            )
        if context.conversation_id != normalized_id:
            raise InvalidCachedContextError(
                "Cached BookingContext does not match its conversation key."
            )
        return context

    async def save(
        self,
        conversation_id: str,
        context: BookingContext,
    ) -> None:
        """Save the supplied context by reference under its conversation key."""
        normalized_id = _validate_conversation_id(conversation_id)
        if not isinstance(context, BookingContext):
            raise InvalidConversationContextError(
                "Conversation context must be a BookingContext."
            )
        if context.conversation_id != normalized_id:
            raise InvalidConversationContextError(
                "BookingContext does not match the supplied conversation ID."
            )
        await self._cache.save(context)

    async def reset(self, conversation_id: str) -> BookingContext:
        """Replace cached state with a new idle context for the conversation."""
        normalized_id = _validate_conversation_id(conversation_id)
        context = BookingContext(conversation_id=normalized_id)
        await self._cache.save(context)
        return context


@dataclass(slots=True)
class ApplicationContainer:
    """Own the assembled application dependencies and their resource lifecycle."""

    http_client: httpx.AsyncClient
    booking_gateway: BookingGateway
    dialog_controller: DialogController
    tool_bridge: ToolBridge
    state_machine: StateMachine
    flow_definition: FlowDefinition
    memory_cache: MemoryCache
    conversation_context_store: ConversationContextStore
    instruction_builder: InstructionBuilder
    deterministic_nlu: DeterministicNLU
    state_intent_policy: StateIntentPolicy
    entity_resolution_coordinator: EntityResolutionCoordinator
    _handlers: tuple[object, ...] = field(repr=False)
    _owns_http_client: bool = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    async def close(self) -> None:
        """Close only resources created and owned by this container."""
        if self._closed:
            return
        self._closed = True
        if self._owns_http_client:
            await self.http_client.aclose()


async def create_application_container(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> ApplicationContainer:
    """Build an isolated application object graph from validated runtime settings."""
    _validate_settings(settings)
    owns_http_client = http_client is None
    client = http_client or httpx.AsyncClient(
        base_url=settings.pos_base_url.strip(),
        timeout=settings.pos_timeout_seconds,
    )

    try:
        flow_definition = FlowLoader.load(settings.booking_flow_path)
        state_intent_policy = build_state_intent_policy(flow_definition)
        booking_gateway: BookingGateway = HTTPBookingGateway(
            client=client,
            base_url=settings.pos_base_url,
            timeout_seconds=settings.pos_timeout_seconds,
        )
        search_shop_handler = SearchShopHandler(booking_gateway)
        search_service_handler = SearchServiceHandler(booking_gateway)
        check_availability_handler = CheckAvailabilityHandler(booking_gateway)
        collect_customer_handler = CollectCustomerHandler(booking_gateway)
        confirm_phone_handler = ConfirmPhoneHandler()
        create_booking_handler = CreateBookingHandler(booking_gateway)
        entity_resolution_coordinator = EntityResolutionCoordinator(
            search_shop_handler=search_shop_handler,
            search_service_handler=search_service_handler,
        )
        handlers: tuple[object, ...] = (
            search_shop_handler,
            search_service_handler,
            check_availability_handler,
            collect_customer_handler,
            confirm_phone_handler,
            create_booking_handler,
        )
        tool_bridge = ToolBridge(
            check_availability_handler=check_availability_handler,
            collect_customer_handler=collect_customer_handler,
            confirm_phone_handler=confirm_phone_handler,
            create_booking_handler=create_booking_handler,
        )
        state_machine = StateMachine(flow_definition)
        dialog_controller = DialogController(
            flow=flow_definition,
            state_machine=state_machine,
            tool_bridge=tool_bridge,
            max_auto_transitions=settings.max_auto_transitions,
        )
        memory_cache = MemoryCache()
        return ApplicationContainer(
            http_client=client,
            booking_gateway=booking_gateway,
            dialog_controller=dialog_controller,
            tool_bridge=tool_bridge,
            state_machine=state_machine,
            flow_definition=flow_definition,
            memory_cache=memory_cache,
            conversation_context_store=ConversationContextStore(cache=memory_cache),
            instruction_builder=InstructionBuilder(),
            deterministic_nlu=DeterministicNLU(
                intent_policy=state_intent_policy,
            ),
            state_intent_policy=state_intent_policy,
            entity_resolution_coordinator=entity_resolution_coordinator,
            _handlers=handlers,
            _owns_http_client=owns_http_client,
        )
    except BaseException:
        if owns_http_client:
            await client.aclose()
        raise


@asynccontextmanager
async def application_container_lifespan(
    settings: Settings,
) -> AsyncIterator[ApplicationContainer]:
    """Yield one container and reliably release its owned resources."""
    container = await create_application_container(settings)
    try:
        yield container
    finally:
        await container.close()


def get_dialog_controller(container: ApplicationContainer) -> DialogController:
    """Return the container's dialog controller."""
    return container.dialog_controller


def get_memory_cache(container: ApplicationContainer) -> MemoryCache:
    """Return the container's conversation context cache."""
    return container.memory_cache


def _validate_conversation_id(conversation_id: str) -> str:
    if not isinstance(conversation_id, str):
        raise InvalidConversationIdError("Conversation ID must be a string.")
    normalized_id = conversation_id.strip()
    if not normalized_id:
        raise InvalidConversationIdError("Conversation ID must not be empty.")
    if len(normalized_id) > _MAX_CONVERSATION_ID_LENGTH:
        raise InvalidConversationIdError(
            f"Conversation ID must not exceed {_MAX_CONVERSATION_ID_LENGTH} characters."
        )
    phone_candidate = normalized_id.replace(" ", "").replace("-", "")
    if _RAW_PHONE_PATTERN.fullmatch(phone_candidate):
        raise InvalidConversationIdError(
            "A raw phone number must not be used as a conversation ID."
        )
    return normalized_id


def _validate_settings(settings: Settings) -> None:
    if not settings.pos_base_url.strip():
        raise ValueError("POS base URL must not be empty.")
    if settings.pos_timeout_seconds <= 0:
        raise ValueError("POS timeout must be positive.")
    if not settings.booking_flow_path.is_file():
        raise ValueError("Booking flow path must reference an existing file.")
    if type(settings.max_auto_transitions) is not int or settings.max_auto_transitions < 1:
        raise ValueError("Maximum auto transitions must be at least one.")
