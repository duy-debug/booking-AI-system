from contextvars import ContextVar, Token
from typing import Callable

TokenEmitter = Callable[[str], None]

_token_emitter: ContextVar[TokenEmitter | None] = ContextVar(
    "chat_token_emitter",
    default=None,
)


def get_token_emitter() -> TokenEmitter | None:
    return _token_emitter.get()


def set_token_emitter(emitter: TokenEmitter) -> Token[TokenEmitter | None]:
    return _token_emitter.set(emitter)


def reset_token_emitter(token: Token[TokenEmitter | None]) -> None:
    _token_emitter.reset(token)
