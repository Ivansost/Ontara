"""Engine path: exactly one platform-native checkpointer and SDK-wrapped I/O."""
from __future__ import annotations

import json
from agent_engine_sdk_langgraph import App
from .clients import BackendClient, BrowserClient
from .mapping import MappingError, StructuredMapper, build_model
from .workflow import ExecutionWorkflow, build_graph

app = App(app_name="Ontara execution", app_version="0.1.0")


@app.tool(is_local=True, redact_fields=["request"], timeout=120)
async def ontara_browser(action: str, request: dict) -> dict:
    """Run an authenticated, origin-restricted browser action for an approved case."""
    client = BrowserClient.from_env()
    try:
        return await client.call(action, request)
    finally:
        await client.close()


@app.prepare_agent_input
def prepare(input, ctx):
    payload = input.payload or {}
    if "jobId" not in payload and "caseId" not in payload and payload.get("message"):
        try:
            payload = json.loads(payload["message"])
        except (ValueError, TypeError):
            raise ValueError("Invoke Ontara with an approved jobId or caseId") from None
    if not payload.get("jobId") and not payload.get("caseId"):
        raise ValueError("An approved jobId or caseId is required")
    return {"job_id": payload.get("jobId"), "case_id": payload.get("caseId")}


@app.entrypoint
def build_agent():
    try:
        mapper = StructuredMapper(app.llm(build_model(), llm_id="changed_form_mapper"))
    except MappingError:
        mapper = None
    tool = next(t for t in app.get_tools() if t.name == "ontara_browser")
    async def browser(action, request):
        result = await tool.ainvoke({"action": action, "request": request})
        return json.loads(result) if isinstance(result, str) else result
    workflow = ExecutionWorkflow(BackendClient.from_env(), browser, mapper)
    return build_graph(workflow, checkpointer=app.checkpointer(), finish=app.finish_session)


if __name__ == "__main__":
    app.run()
