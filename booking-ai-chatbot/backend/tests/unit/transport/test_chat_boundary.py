"""Architecture checks for the intentionally thin HTTP chat boundary."""

import ast
from pathlib import Path


def test_chat_transport_has_no_business_or_state_mutation() -> None:
    source = Path("app/transport/chat_api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert (
        not {
            "CheckAvailabilityHandler",
            "SearchCourseHandler",
            "SearchShopHandler",
            "PosApiClient",
        }
        & imported_names
    )
    assert not any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute) and target.attr == "state" for target in node.targets
        )
        for node in ast.walk(tree)
    )


def test_dialog_controller_has_no_http_or_sse_dependency() -> None:
    source = Path("app/dialog/dialog_controller.py").read_text(encoding="utf-8")

    assert "fastapi" not in source
    assert "StreamingResponse" not in source
    assert "encode_sse_event" not in source
    assert "app.transport" not in source


def test_removed_orchestration_module_has_no_caller_or_file() -> None:
    legacy_name = "message_" + "processor"
    assert not Path("app/dialog", f"{legacy_name}.py").exists()
    for root in (Path("app"), Path("tests")):
        for path in root.rglob("*.py"):
            assert legacy_name not in path.read_text(encoding="utf-8")
