import sys
from abc import ABC, abstractmethod

from app.system_prompt import SYSTEM_PROMPT


def _stringify(content):
    """Return typecasted string version of the content"""
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
    """Builds initial prompt for agent runtime"""
    if not context:
        return query
    transcript = "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in context)
    return f"{transcript}\nUSER: {query}"


# Base class for Agent Runtime
class AgentRuntimeBase(ABC):

    def __init__(self):
        pass

    @abstractmethod
    async def run(self, query, context):
        pass

# Inherited class - uses claude_agent_sdk library with Claude Code's engine
class ClaudeAgentSDKRuntime(AgentRuntimeBase):

    def __init__(self, config):
        self.model = config["model"]
        self.max_turns = config.get("max_turns", 8)
        self.allowed_tools = config.get("allowed_tools", [])
        self.server_args = config["mcp_server"]["args"]

    async def run(self, query, context):
        """Agent loop : runs the agent with tools"""
        from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions, ResultMessage

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            tools=[], # LLM tried reading CSV from files. This disables inbuilt tools. 
            mcp_servers={"local": {"type": "stdio", "command": sys.executable, "args": self.server_args}},
            allowed_tools=self.allowed_tools,
            env={"ENABLE_TOOL_SEARCH": "false"},       # load MCP tools eagerly
            permission_mode="bypassPermissions", 
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
                    if name == "ThinkingBlock": # internal thought block from claude
                        events.append({"type": "thought", "text": block.thinking})
                    elif name == "ToolUseBlock": # block depicting tool use by agent
                        events.append({"type": "tool_call", "name": block.name, "input": block.input})
                    elif name == "ToolResultBlock": # tool result passed to the agent after tool use
                        events.append({"type": "tool_result", "output": _stringify(block.content)})
                    elif name == "TextBlock": # response block from the agent
                        final_parts.append(block.text)
        except Exception as error:
            events.append({"type": "final", "text": f"[runtime error] {error}"})

        if not any(event["type"] == "final" for event in events):
            events.append({"type": "final", "text": "".join(final_parts)})
        return events


class DeepAgentsRuntime(AgentRuntimeBase):

    def __init__(self, config):
        self.model = config["model"]
        self.max_tokens = config.get("max_tokens", 2048)
        self.server_args = config["mcp_server"]["args"]

    async def run(self, query, context):
        from langchain_anthropic import ChatAnthropic
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from deepagents import create_deep_agent

        client = MultiServerMCPClient({
            "local": {"command": sys.executable, "args": self.server_args, "transport": "stdio"}
        })
        tools = await client.get_tools()
        model = ChatAnthropic(model=self.model, max_tokens=self.max_tokens)
        agent = create_deep_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT) # Out of the box agent capability by deepagents

        messages = [{"role": turn["role"], "content": turn["content"]} for turn in context]
        messages.append({"role": "user", "content": query})

        events = []
        final_parts = []
        async for update in agent.astream({"messages": messages}, stream_mode="updates"):
            for payload in update.values():
                if not isinstance(payload, dict): # Can yield updates where payload is None
                    continue

                for message in payload.get("messages", []):
                    name = type(message).__name__
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls: # Process tool calls
                        for call in tool_calls:
                            events.append({"type": "tool_call", "name": call["name"], "input": call.get("args", {})})
                    if name == "ToolMessage": # Process tool results
                        events.append({"type": "tool_result", "output": _stringify(message.content)})
                    elif name == "AIMessage": # Process final response
                        text = _stringify(message.content)
                        if text.strip() and tool_calls: # This condition satisfies for a thought response
                            events.append({"type": "thought", "text": text})
                        elif text.strip():
                            final_parts.append(text)

        events.append({"type": "final", "text": final_parts[-1] if final_parts else ""})
        return events


class AgentRuntimeClientFactory():

    def __init__(self, config):
        # Map all available clients for selection
        self.client_map = {
            "claude_agent_sdk": ClaudeAgentSDKRuntime,
            "deepagents": DeepAgentsRuntime
        }
        runtime_config = config.get("AGENT_RUNTIME_CONFIG", {})
        default_provider = runtime_config.get("DEFAULT_PROVIDER")

        # Get default provider and initialize correct provider class
        provider_class = self.client_map.get(default_provider)
        if not provider_class:
            raise ValueError("DEFAULT_PROVIDER not present in config")
        
        provider_config = runtime_config.get("PROVIDERS", {}).get(default_provider)
        self.client = provider_class(provider_config) # default provider client initialized
