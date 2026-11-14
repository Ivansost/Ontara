"""Cloud fallback child. The HTTP supervisor never runs this graph in-process."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from .clients import BackendClient, BrowserClient
from .mapping import MappingError, StructuredMapper, build_model
from .workflow import ExecutionWorkflow, build_graph


async def run(args):
    if os.environ.get("ONTARA_RUNTIME_MODE") != "fallback":
        raise RuntimeError("Direct Atlas checkpointer is reserved for the explicit cloud fallback")
    from langgraph.checkpoint.mongodb import MongoDBSaver
    backend = BackendClient.from_env()
    browser = BrowserClient.from_env()
    try:
        try:
            mapper = StructuredMapper(build_model())
        except MappingError:
            mapper = None
        with MongoDBSaver.from_conn_string(os.environ["MONGODB_URI"], db_name=os.environ.get("CHECKPOINT_DB_NAME", "ontara"), checkpoint_collection_name="execution_checkpoints", writes_collection_name="execution_checkpoint_writes") as saver:
            graph = build_graph(ExecutionWorkflow(backend, browser, mapper), saver)
            result = await graph.ainvoke({"job_id": args.job_id, "case_id": args.case_id}, {"configurable": {"thread_id": args.job_id or args.case_id}, "recursion_limit": 5})
            print(json.dumps({k: v for k, v in result.items() if k in {"status", "operation_id", "attempt_id", "process_id"}}), flush=True)
    finally:
        await backend.close()
        await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id")
    parser.add_argument("--case-id")
    args = parser.parse_args()
    if not args.job_id and not args.case_id:
        parser.error("job-id or case-id is required")
    try:
        asyncio.run(run(args))
    except Exception as error:
        print(json.dumps({"status": "failed", "errorType": type(error).__name__, "process_id": os.getpid()}), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
