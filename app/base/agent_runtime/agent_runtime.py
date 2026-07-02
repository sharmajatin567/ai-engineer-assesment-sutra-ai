import sys
from abc import ABC, abstractmethod

from system_prompt import SYSTEM_PROMPT


def _stringify(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(getattr(item, "text", str(item)))
        return "\n".join(parts)
    return str(content)


def _build_prompt(query, context):
    if not context:
        return query
    transcript = "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in context)
    return f"{transcript}\nUSER: {query}"


class AgentRuntimeBase(ABC):

    def __init__(self):
        pass

    @abstractmethod
    async def run(self, query, context):
        pass


class ClaudeAgentSDKRuntime(AgentRuntimeBase):

    def __init__(self, config):
        self.model = config["model"]
        self.max_turns = config.get("max_turns", 8)
        self.allowed_tools = config.get("allowed_tools", [])
        self.server_args = config["mcp_server"]["args"]

    async def run(self, query, context):
        from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions, ResultMessage

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"local": {"type": "stdio", "command": sys.executable, "args": self.server_args}},
            allowed_tools=self.allowed_tools,
            setting_sources=[],
            max_turns=self.max_turns,
        )

        events = []
        final_parts = []
        try:
            async for message in sdk_query(prompt=_build_prompt(query, context), options=options):
                if isinstance(message, ResultMessage):
                    if getattr(message, "result", None):
                        events.append({"type": "final", "text": message.result})
                    continue
                content = getattr(message, "content", None)
                if not isinstance(content, list):
                    continue
                for block in content:
                    name = type(block).__name__
                    if name == "ThinkingBlock":
                        events.append({"type": "thought", "text": block.thinking})
                    elif name == "ToolUseBlock":
                        events.append({"type": "tool_call", "name": block.name, "input": block.input})
                        if "csv" in block.name:
                            events.append({"type": "skill_used", "name": "csv_skill"})
                    elif name == "ToolResultBlock":
                        events.append({"type": "tool_result", "output": _stringify(block.content)})
                    elif name == "TextBlock":
                        final_parts.append(block.text)
        except Exception as error:
            events.append({"type": "final", "text": f"[runtime error] {error}"})

        if not any(event["type"] == "final" for event in events):
            events.append({"type": "final", "text": "".join(final_parts)})
        return events



class AgentRuntimeClientFactory():

    def __init__(self, config):
        self.client_map = {
            "claude_agent_sdk": ClaudeAgentSDKRuntime
        }
        runtime_config = config.get("AGENT_RUNTIME_CONFIG", {})
        default_provider = runtime_config.get("DEFAULT_PROVIDER")
        provider_class = self.client_map.get(default_provider)
        if not provider_class:
            raise ValueError("DEFAULT_PROVIDER not present in config")
        provider_config = runtime_config.get("PROVIDERS", {}).get(default_provider)
        self.client = provider_class(provider_config)
