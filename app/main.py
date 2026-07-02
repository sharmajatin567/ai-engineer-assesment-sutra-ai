import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.base.read_config import read_config
from app.base.agent_runtime import AgentRuntimeClientFactory
from app.utils import format_trace, final_text, write_run_log, record_feedback


def main():
    config = read_config()

    # Initialize runtime client
    runtime = AgentRuntimeClientFactory(config).client

    provider = config["AGENT_RUNTIME_CONFIG"]["DEFAULT_PROVIDER"]
    print(f"ACME Assistant ready (runtime: {provider}):")

    context = [] # Temperory context window for session memory
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
        
        # Extract final answer for displaying on terminal
        answer = final_text(events)

        # OPTIONAL - format_trace function - uncomment to check agent trace
        # print(format_trace(events))

        print(f"\nAnswer:\n{answer}")

        # Append conversation to context
        context.append({"role": "user", "content": query})
        context.append({"role": "assistant", "content": answer})

        # Record feedback - Helpful/Not Helpful
        feedback = record_feedback()

        # Write run log json with all events and feedback
        write_run_log(query, events, feedback)

if __name__ == "__main__":
    main()
