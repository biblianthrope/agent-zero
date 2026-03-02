from python.helpers.api import ApiHandler, Input, Output, Request, Response
from agent import AgentContext
from python.helpers import persist_chat
from python.helpers.task_scheduler import TaskScheduler


def _clear_monitor_state(ctxid: str):
    """Remove a context_id from matrix_monitor_state.json if present.
    This prevents deleted chats from being recreated as zombies when
    the Matrix monitor sends the next message for that room."""
    import json, os
    state_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "usr", "workdir", "matrix_monitor_state.json")
    if not os.path.exists(state_path):
        return
    try:
        with open(state_path, "r") as f:
            state = json.load(f)
        user_contexts = state.get("user_contexts", {})
        keys_to_remove = [k for k, v in user_contexts.items() if v.get("context_id") == ctxid]
        if not keys_to_remove:
            return
        for key in keys_to_remove:
            del user_contexts[key]
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[chat_remove] Warning: failed to clear monitor state for {ctxid}: {e}")


class RemoveChat(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        ctxid = input.get("context", "")

        scheduler = TaskScheduler.get()
        scheduler.cancel_tasks_by_context(ctxid, terminate_thread=True)

        context = AgentContext.use(ctxid)
        if context:
            # stop processing any tasks
            context.reset()

        AgentContext.remove(ctxid)
        persist_chat.remove_chat(ctxid)

        # Clear from matrix monitor state to prevent zombie recreation
        _clear_monitor_state(ctxid)

        await scheduler.reload()

        tasks = scheduler.get_tasks_by_context_id(ctxid)
        for task in tasks:
            await scheduler.remove_task_by_uuid(task.uuid)

        # Context removal affects global chat/task lists in all tabs.
        from python.helpers.state_monitor_integration import mark_dirty_all
        mark_dirty_all(reason="api.chat_remove.RemoveChat")

        return {
            "message": "Context removed.",
        }
