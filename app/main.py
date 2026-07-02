import asyncio

from base.read_config import read_config
from base.agent_runtime import AgentRuntimeClientFactory
from utils import format_trace, final_text, write_run_log, record_feedback


def main():
    config = read_config()
    runtime = AgentRuntimeClientFactory(config).client
    provider = config["AGENT_RUNTIME_CONFIG"]["DEFAULT_PROVIDER"]
    print(f"ACME Assistant ready (runtime: {provider}):")

    context = []
    while True:
        try:
            query = input("\n> ")
        except Exception:
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break
        try:
            events = asyncio.run(runtime.run(query, context))
        except Exception as error:
            events = [{"type": "final", "text": f"[runtime error] {error}"}]
        answer = final_text(events)
        # print(format_trace(events))
        print(f"\nAnswer:\n{answer}")
        context.append({"role": "user", "content": query})
        context.append({"role": "assistant", "content": answer})
        feedback = record_feedback()
        write_run_log(query, events, feedback)

if __name__ == "__main__":
    main()
