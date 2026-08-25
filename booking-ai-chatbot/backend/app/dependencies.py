"""Lắp ghép và quản lý toàn bộ dependency runtime của ứng dụng chatbot."""

import asyncio
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from math import isfinite
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from qdrant_client import QdrantClient

from app.application.action_registry import ActionRegistry
from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.check_customer_handler import CheckCustomerHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.application.handlers.select_booking_info_handler import SelectBookingInfoHandler
from app.application.handlers.select_schedule_handler import SelectScheduleHandler
from app.dialog.dialog_controller import DialogController
from app.dialog.flow_loader import ChangeRule, FlowDefinition, FlowLoader
from app.dialog.instruction_builder import InstructionBuilder
from app.dialog.nlu import (
    LLMNLU,
    SUPPORTED_NLU_INTENTS,
    EntityResolutionCoordinator,
    StateIntentPolicy,
    build_state_intent_policy,
)
from app.dialog.response_generator import ResponseGenerator
from app.dialog.state_machine import StateMachine
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    BookingGateway,
    TherapistAvailabilityGateway,
    TherapistCatalogGateway,
)
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import ContextStore, Settings
from app.infrastructure.gemini_client import GeminiClient, LLMGateway
from app.infrastructure.pos_api_client import PosApiClient
from app.rag_v1 import (
    KnowledgeGateway,
)
from app.rag_v1.config import RAGConfig
from app.rag_v1.embedding import EmbeddingModel
from app.rag_v1.faq_manager import FAQManager
from app.rag_v1.keyword_search import BM25KeywordSearch
from app.rag_v1.prompt import PromptBuilder
from app.rag_v1.reranker import Reranker
from app.rag_v1.retriever import Retriever
from app.rag_v1.service import RAGService
from app.rag_v1.vector_store import VectorStore

_MAX_CONVERSATION_ID_LENGTH = 128
_RAW_PHONE_PATTERN = re.compile(r"\+?\d{9,15}")


class ConversationContextError(Exception):
    """Lỗi cơ sở cho các vấn đề ở vòng đời lưu và tải conversation context."""


class InvalidConversationIdError(ConversationContextError):
    """Phát sinh khi conversation identifier không an toàn hoặc sai định dạng."""


class InvalidCachedContextError(ConversationContextError):
    """Phát sinh khi dữ liệu cache không còn đúng contract của BookingContext."""


class InvalidConversationContextError(ConversationContextError):
    """Phát sinh khi context không thể được lưu dưới conversation identifier đã cho."""


class RuntimeFlowValidationError(ValueError):
    """Phát sinh khi dependency đã compose không thể phục vụ runtime flow đang được nạp."""


@dataclass(slots=True)
class _ConversationLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class ConversationContextStore:
    """Điều phối việc lưu, tải và khóa BookingContext trong in-process cache."""

    # Khởi tạo lock theo conversation để nhiều request cùng session không ghi đè context.
    def __init__(self, *, cache: ContextStore) -> None:
        self._cache = cache
        self._lock_registry_guard = asyncio.Lock()
        self._conversation_locks: dict[str, _ConversationLockEntry] = {}

    @asynccontextmanager
    # Cấp lock cho một conversation_id và tự dọn lock khi context đã bị xóa khỏi store.
    async def conversation_lock(
        self,
        conversation_id: str,
    ) -> AsyncIterator[None]:
        """Khóa theo conversation để các request cùng phiên không ghi đè context của nhau."""
        normalized_id = _validate_conversation_id(conversation_id)
        async with self._lock_registry_guard:
            entry = self._conversation_locks.get(normalized_id)
            if entry is None:
                entry = _ConversationLockEntry()
                self._conversation_locks[normalized_id] = entry
            entry.users += 1
        await entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            async with self._lock_registry_guard:
                entry.users -= 1
                if entry.users == 0:
                    self._conversation_locks.pop(normalized_id, None)

    # Lấy bản sao BookingContext để controller xử lý trên working copy có thể rollback.
    async def get_copy(self, conversation_id: str) -> BookingContext:
        """Lấy working copy tách biệt của BookingContext hoặc tạo mới nếu cache chưa có."""
        normalized_id = _validate_conversation_id(conversation_id)
        context = await self._cache.get(normalized_id)
        if context is None:
            context = BookingContext(conversation_id=normalized_id)
            await self._cache.save(context)
            return context
        if not isinstance(context, BookingContext):
            raise InvalidCachedContextError("Cached conversation data must be a BookingContext.")
        if context.conversation_id != normalized_id:
            raise InvalidCachedContextError(
                "Cached BookingContext does not match its conversation key."
            )
        return context

    # Lưu BookingContext sau khi một lượt chat đã qua hết business pipeline thành công.
    async def save(
        self,
        conversation_id: str,
        context: BookingContext,
    ) -> None:
        """Lưu snapshot đã kiểm tra của BookingContext dưới đúng conversation key."""
        normalized_id = _validate_conversation_id(conversation_id)
        if not isinstance(context, BookingContext):
            raise InvalidConversationContextError("Conversation context must be a BookingContext.")
        if context.conversation_id != normalized_id:
            raise InvalidConversationContextError(
                "BookingContext does not match the supplied conversation ID."
            )
        await self._cache.save(context)

    # Reset một conversation về context mới nhưng vẫn giữ conversation_id ổn định.
    async def reset(self, conversation_id: str) -> BookingContext:
        """Reset conversation về một idle context mới nhưng vẫn giữ nguyên conversation_id."""
        normalized_id = _validate_conversation_id(conversation_id)
        context = BookingContext(conversation_id=normalized_id)
        await self._cache.save(context)
        return context


@dataclass(slots=True)
class ApplicationContainer:
    """Chứa toàn bộ dependency đã được wire và quản lý tài nguyên sống theo app lifespan."""

    http_client: httpx.AsyncClient
    booking_gateway: BookingGateway
    dialog_controller: DialogController
    action_registry: ActionRegistry
    state_machine: StateMachine
    flow_definition: FlowDefinition
    memory_cache: ContextStore
    conversation_context_store: ConversationContextStore
    instruction_builder: InstructionBuilder
    response_generator: ResponseGenerator
    check_customer_handler: CheckCustomerHandler
    select_booking_info_handler: SelectBookingInfoHandler
    select_schedule_handler: SelectScheduleHandler
    state_intent_policy: StateIntentPolicy
    entity_resolution_coordinator: EntityResolutionCoordinator
    llm_gateway: LLMGateway
    llm_nlu: LLMNLU
    llm_nlg_required: bool
    faq_manager: FAQManager
    knowledge_gateway: KnowledgeGateway | None
    _handlers: tuple[object, ...] = field(repr=False)
    _owns_http_client: bool = field(repr=False)
    _qdrant_client: QdrantClient | None = field(default=None, repr=False)
    _rag_service: RAGService | None = field(default=None, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    # Trả về handler đã wire sẵn để các fallback path không tự tạo dependency mới.
    def handler(self, handler_type: type[object]) -> object:
        """Trả về handler đã được compose sẵn theo đúng concrete type của application layer."""
        for configured in self._handlers:
            if isinstance(configured, handler_type):
                return configured
        raise RuntimeError(f"Handler {handler_type.__name__} is unavailable.")

    # Đóng các tài nguyên async dùng chung như HTTP client khi app shutdown.
    async def close(self) -> None:
        """Đóng các tài nguyên async do chính container tạo và sở hữu."""
        if self._closed:
            return
        self._closed = True
        if self._owns_http_client:
            await self.http_client.aclose()
        if self._qdrant_client is not None:
            self._qdrant_client.close()
        if self._rag_service is not None:
            await self._rag_service.close()


# Wire toàn bộ dependency production: POS, Qdrant, LLM, StateMachine,
# ActionRegistry và DialogController.
async def create_application_container(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
    llm_gateway: LLMGateway | None = None,
    knowledge_gateway: KnowledgeGateway | None = None,
) -> ApplicationContainer:
    """Tạo toàn bộ object graph production từ runtime settings đã qua kiểm tra."""
    _validate_settings(settings)
    owns_http_client = http_client is None
    client = http_client or httpx.AsyncClient(
        base_url=settings.pos_base_url.strip(),
        timeout=settings.pos_timeout_seconds,
    )
    qdrant_client: QdrantClient | None = None

    try:
        flow_definition = FlowLoader.load(settings.booking_flow_path)
        change_rules = FlowLoader.load_change_handlers(settings.change_handlers_path)
        state_intent_policy = build_state_intent_policy(
            flow_definition,
            enable_faq=True,
            enable_discovery=True,
        )
        booking_gateway: BookingGateway = PosApiClient(
            client=client,
            base_url=settings.pos_base_url,
            timeout_seconds=settings.pos_timeout_seconds,
        )
        search_shop_handler = SearchShopHandler(
            booking_gateway,
            therapist_catalog_gateway=cast(TherapistCatalogGateway, booking_gateway),
            therapist_availability_gateway=cast(TherapistAvailabilityGateway, booking_gateway),
        )
        search_course_handler = SearchCourseHandler(booking_gateway)
        check_availability_handler = CheckAvailabilityHandler(booking_gateway)
        check_customer_handler = CheckCustomerHandler(booking_gateway)
        select_booking_info_handler = SelectBookingInfoHandler()
        select_schedule_handler = SelectScheduleHandler()
        create_booking_handler = CreateBookingHandler(booking_gateway)
        entity_resolution_coordinator = EntityResolutionCoordinator(
            search_shop_handler=search_shop_handler,
            search_course_handler=search_course_handler,
            booking_gateway=cast(TherapistAvailabilityGateway, booking_gateway),
        )
        configured_llm_gateway = llm_gateway or GeminiClient(
            client=client,
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model=settings.gemini_model,
            fallback_model=settings.gemini_fallback_model,
            max_retries=settings.llm_max_retries,
        )
        handlers: tuple[object, ...] = (
            search_shop_handler,
            search_course_handler,
            check_availability_handler,
            check_customer_handler,
            select_booking_info_handler,
            select_schedule_handler,
            create_booking_handler,
        )
        action_registry = ActionRegistry(
            search_shop_handler=search_shop_handler,
            check_availability_handler=check_availability_handler,
            create_booking_handler=create_booking_handler,
            select_booking_info_handler=select_booking_info_handler,
            select_schedule_handler=select_schedule_handler,
            check_customer_handler=check_customer_handler,
            booking_gateway=booking_gateway,
            therapist_availability_gateway=cast(TherapistAvailabilityGateway, booking_gateway),
        )
        instruction_builder = InstructionBuilder()
        validate_runtime_flow(
            flow_definition,
            action_registry,
            instruction_builder,
            change_rules=change_rules,
        )
        state_machine = StateMachine(flow_definition)
        dialog_controller = DialogController(
            flow=flow_definition,
            state_machine=state_machine,
            action_registry=action_registry,
            change_rules=change_rules,
            max_auto_transitions=settings.max_auto_transitions,
        )
        memory_cache = ContextStore()
        response_generator = ResponseGenerator(
            configured_llm_gateway,
            instruction_builder,
        )
        configured_knowledge_gateway = knowledge_gateway
        faq_rag_service: RAGService | None = None
        rag_config = RAGConfig(
            embedding_model_name=settings.embedding_model_name,
        )
        if configured_knowledge_gateway is None and settings.knowledge_qdrant_enabled:
            rag_config = RAGConfig(
                embedding_model_name=settings.embedding_model_name,
                collection_name=settings.qdrant_collection,
            )
            qdrant_client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key,
            )
            vector_store = VectorStore(
                client=qdrant_client,
                collection_name=rag_config.collection_name,
                vector_size=rag_config.vector_size,
            )
            embedding = EmbeddingModel(
                model_name=rag_config.embedding_model_name,
                normalize_embeddings=rag_config.normalize_embeddings,
            )
            keyword_search = BM25KeywordSearch(
                vector_store=vector_store,
            )
            faq_retriever = Retriever(
                embedder=embedding,
                vector_store=vector_store,
                keyword_search=keyword_search,
            )
            faq_reranker = Reranker(
                model_name=rag_config.reranker_model_name,
            )
            faq_rag_service = RAGService(
                retriever=faq_retriever,
                reranker=faq_reranker,
                prompt_builder=PromptBuilder(),
                api_key=settings.gemini_api_key or "",
                base_url=settings.gemini_base_url,
                model=settings.gemini_model,
                fallback_model=settings.gemini_fallback_model,
                max_retries=settings.llm_max_retries,
            )
        container = ApplicationContainer(
            http_client=client,
            booking_gateway=booking_gateway,
            dialog_controller=dialog_controller,
            action_registry=action_registry,
            state_machine=state_machine,
            flow_definition=flow_definition,
            memory_cache=memory_cache,
            conversation_context_store=ConversationContextStore(cache=memory_cache),
            instruction_builder=instruction_builder,
            response_generator=response_generator,
            check_customer_handler=check_customer_handler,
            select_booking_info_handler=select_booking_info_handler,
            select_schedule_handler=select_schedule_handler,
            state_intent_policy=state_intent_policy,
            entity_resolution_coordinator=entity_resolution_coordinator,
            llm_gateway=configured_llm_gateway,
            llm_nlu=LLMNLU(
                llm_gateway=configured_llm_gateway,
                intent_policy=state_intent_policy,
                min_confidence=settings.llm_nlu_min_confidence,
                business_timezone=settings.business_timezone,
            ),
            llm_nlg_required=settings.llm_nlg_required,
            faq_manager=FAQManager(
                instruction_builder=instruction_builder,
                rag_service=faq_rag_service,
            ),
            knowledge_gateway=configured_knowledge_gateway,
            _handlers=handlers,
            _owns_http_client=owns_http_client,
            _qdrant_client=qdrant_client,
            _rag_service=faq_rag_service,
        )
        dialog_controller.bind_runtime(container)
        return container
    except BaseException:
        if qdrant_client is not None:
            qdrant_client.close()
        if owns_http_client:
            await client.aclose()
        raise


@asynccontextmanager
# Quản lý vòng đời ApplicationContainer trong FastAPI lifespan.
async def application_container_lifespan(
    settings: Settings,
) -> AsyncIterator[ApplicationContainer]:
    """Cấp ra một ApplicationContainer và đảm bảo đóng tài nguyên khi lifespan kết thúc."""
    container = await create_application_container(settings)
    try:
        yield container
    finally:
        await container.close()


# Kiểm tra flow JSON có đầy đủ action, failure code và template trước khi chạy runtime.
def validate_runtime_flow(
    flow: FlowDefinition,
    action_registry: ActionRegistry,
    instruction_builder: InstructionBuilder,
    *,
    change_rules: Mapping[str, ChangeRule] | None = None,
) -> None:
    """Kiểm tra sớm flow khai báo có thể được phục vụ đầy đủ bởi runtime hiện tại hay không."""
    declared_actions: list[str] = []
    declared_templates: list[str] = []
    declared_intents: set[str] = set()
    reachable_edges: dict[BookingState, set[BookingState]] = {state: set() for state in flow.states}

    # Gom failure code từ flow để đối chiếu với registry và response renderer.
    def include_failure(failure: object) -> None:
        actions = getattr(failure, "actions", ())
        template = getattr(failure, "instruction_template", None)
        target = getattr(failure, "target", None)
        declared_actions.extend(actions)
        if isinstance(template, str):
            declared_templates.append(template)
        if isinstance(target, BookingState):
            reachable_edges[current_state].add(target)

    for current_state, definition in flow.states.items():
        declared_actions.extend(definition.on_enter.actions)
        if definition.on_enter.instruction_template is not None:
            declared_templates.append(definition.on_enter.instruction_template)
        for failure in definition.on_enter.on_fail:
            include_failure(failure)
        seen_transitions: list[object] = []
        for transition in definition.transitions:
            if transition in seen_transitions:
                raise RuntimeFlowValidationError(
                    f"State '{current_state.value}' contains a duplicate transition."
                )
            seen_transitions.append(transition)
            declared_intents.add(transition.intent)
            declared_actions.extend(transition.actions)
            reachable_edges[current_state].add(transition.target)
            for failure in transition.on_fail:
                include_failure(failure)
        for auto_transition in definition.auto_transitions:
            declared_actions.extend(auto_transition.actions)
            reachable_edges[current_state].add(auto_transition.target)
            for failure in auto_transition.on_fail:
                include_failure(failure)

    for rule in (change_rules or {}).values():
        reset_action = getattr(rule, "reset_action", None)
        prompt_template = getattr(rule, "prompt_template", None)
        if isinstance(reset_action, str):
            declared_actions.append(reset_action)
        if isinstance(prompt_template, str):
            declared_templates.append(prompt_template)

    missing_actions = action_registry.find_unregistered_actions(declared_actions)
    if missing_actions:
        raise RuntimeFlowValidationError("Unregistered flow actions: " + ", ".join(missing_actions))
    unknown_intents = (
        declared_intents
        - SUPPORTED_NLU_INTENTS
        - {
            "*",
            "booking_failed",
            "booking_succeeded",
        }
    )
    if unknown_intents:
        raise RuntimeFlowValidationError(
            "Unsupported flow intents: " + ", ".join(sorted(unknown_intents))
        )
    missing_templates = instruction_builder.find_missing_templates(declared_templates)
    if missing_templates:
        raise RuntimeFlowValidationError(
            "Unregistered instruction templates: " + ", ".join(missing_templates)
        )

    reachable = {flow.initial_state}
    pending = [flow.initial_state]
    while pending:
        source = pending.pop()
        for target in reachable_edges[source] - reachable:
            reachable.add(target)
            pending.append(target)
    unreachable = set(flow.states) - reachable
    if unreachable:
        raise RuntimeFlowValidationError(
            "Unreachable flow states: " + ", ".join(sorted(state.value for state in unreachable))
        )


# Validate conversation_id để tránh lưu context với key rỗng hoặc quá dài.
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


# Fail fast khi cấu hình runtime không đủ để khởi tạo provider đang được bật.
def _validate_settings(settings: Settings) -> None:
    if not settings.pos_base_url.strip():
        raise ValueError("POS base URL must not be empty.")
    if settings.pos_timeout_seconds <= 0:
        raise ValueError("POS timeout must be positive.")
    if not settings.booking_flow_path.is_file():
        raise ValueError("Booking flow path must reference an existing file.")
    if not settings.change_handlers_path.is_file():
        raise ValueError("Change handlers path must reference an existing file.")
    if type(settings.max_auto_transitions) is not int or settings.max_auto_transitions < 1:
        raise ValueError("Maximum auto transitions must be at least one.")
    if type(settings.llm_nlg_required) is not bool:
        raise ValueError("LLM NLG required flag must be boolean.")
    if (
        isinstance(settings.llm_nlu_min_confidence, bool)
        or not isinstance(settings.llm_nlu_min_confidence, int | float)
        or not isfinite(settings.llm_nlu_min_confidence)
        or not 0.0 <= settings.llm_nlu_min_confidence <= 1.0
    ):
        raise ValueError("LLM NLU confidence threshold must be between zero and one.")
    if settings.llm_provider.strip().casefold() != "gemini":
        raise ValueError("LLM_PROVIDER must be 'gemini'.")
    if not settings.gemini_model.strip():
        raise ValueError("GEMINI_MODEL must not be empty.")
    if settings.gemini_fallback_model is not None and not settings.gemini_fallback_model.strip():
        raise ValueError("GEMINI_FALLBACK_MODEL must not be empty when configured.")
    if (
        settings.gemini_fallback_model is not None
        and settings.gemini_fallback_model.strip() == settings.gemini_model.strip()
    ):
        raise ValueError("GEMINI_FALLBACK_MODEL must differ from GEMINI_MODEL.")
    if settings.gemini_base_url.strip().rstrip("/") != (
        "https://generativelanguage.googleapis.com/v1beta/openai"
    ):
        raise ValueError("GEMINI_BASE_URL must be the official Gemini OpenAI endpoint.")
    if type(settings.llm_max_retries) is not int or not 0 <= settings.llm_max_retries <= 1:
        raise ValueError("LLM_MAX_RETRIES must be 0 or 1.")
    if settings.llm_max_retries == 1 and settings.gemini_fallback_model is None:
        raise ValueError("GEMINI_FALLBACK_MODEL is required when LLM_MAX_RETRIES is 1.")
    if type(settings.dialog_intent_tool_enabled) is not bool:
        raise ValueError("DIALOG_INTENT_TOOL_ENABLED must be boolean.")
    if not settings.dialog_intent_tool_enabled:
        raise ValueError("DIALOG_INTENT_TOOL_ENABLED must be true for Gemini NLU.")
    try:
        ZoneInfo(settings.business_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("BUSINESS_TIMEZONE must be a valid IANA timezone.") from error
    if not settings.embedding_model_name.strip():
        raise ValueError("Embedding model name must not be empty.")
    if type(settings.knowledge_qdrant_enabled) is not bool:
        raise ValueError("Knowledge Qdrant enabled flag must be boolean.")
    if (
        isinstance(settings.rag_score_threshold, bool)
        or not isinstance(settings.rag_score_threshold, int | float)
        or not isfinite(settings.rag_score_threshold)
        or not 0.0 <= settings.rag_score_threshold <= 1.0
    ):
        raise ValueError("RAG score threshold must be between zero and one.")
    if settings.knowledge_qdrant_enabled:
        host = settings.qdrant_host.strip()
        if (
            not host
            or "://" in host
            or "/" in host
            or "@" in host
            or any(character.isspace() for character in host)
        ):
            raise ValueError("Qdrant host must be a hostname or IP address.")
        if type(settings.qdrant_port) is not int or not 1 <= settings.qdrant_port <= 65535:
            raise ValueError("Qdrant port must be between 1 and 65535.")
        if not settings.qdrant_collection.strip():
            raise ValueError("Qdrant collection name must not be empty.")
