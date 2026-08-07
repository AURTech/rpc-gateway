import asyncio
from contextlib import AbstractContextManager
from weakref import WeakKeyDictionary

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.trace import TASK_TRACE_LABEL, generate_trace_id, get_current_trace_id, trace_context


class TraceMiddleware(TaskiqMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._task_trace_contexts: WeakKeyDictionary[asyncio.Task[object], AbstractContextManager[str]] = WeakKeyDictionary()

    def _get_message_trace_id(self, message: TaskiqMessage, fallback: str) -> str:
        trace_id = message.labels.get(TASK_TRACE_LABEL)
        if isinstance(trace_id, str):
            trace_id = trace_id.strip()
        elif trace_id is not None:
            trace_id = str(trace_id).strip()
        else:
            trace_id = ''
        return trace_id or fallback

    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        trace_id = self._get_message_trace_id(message, get_current_trace_id() or generate_trace_id())
        message.labels[TASK_TRACE_LABEL] = trace_id
        return message

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        current_task = asyncio.current_task()
        if current_task is None:
            return message

        self._reset_trace_context(current_task)
        trace_id = self._get_message_trace_id(message, f'{message.task_name}:{message.task_id}')
        message.labels[TASK_TRACE_LABEL] = trace_id
        context = trace_context(trace_id)
        context.__enter__()
        self._task_trace_contexts[current_task] = context
        return message

    def post_execute(self, message: TaskiqMessage, result: TaskiqResult[object]) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._reset_trace_context(current_task)

    def on_error(self, message: TaskiqMessage, result: TaskiqResult[object], exception: BaseException) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._reset_trace_context(current_task)

    def _reset_trace_context(self, current_task: asyncio.Task[object]) -> None:
        if context := self._task_trace_contexts.pop(current_task, None):
            context.__exit__(None, None, None)
