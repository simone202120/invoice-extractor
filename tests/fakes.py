"""Fake chat model answering with scripted tool calls, to drive the real extraction chain."""

import json
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from pydantic import Field

from invoice_extractor.core.models import Invoice

SAMPLES = Path(__file__).parent.parent / "samples"


class FakeToolCallingModel(GenericFakeChatModel):
    received: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeToolCallingModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received.append(messages)
        return super()._generate(messages, stop, run_manager, **kwargs)


def invoice_call(args: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "Invoice", "args": args, "id": "call"}])


def expected_invoice(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SAMPLES / "expected" / f"{name}.json").read_text())
    return data


def fake_extractor(*responses: AIMessage) -> tuple[Runnable[Any, Any], FakeToolCallingModel]:
    model = FakeToolCallingModel(messages=iter(responses))
    return model.with_structured_output(Invoice, include_raw=True), model
