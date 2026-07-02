from abc import ABC, abstractmethod

# Base class for LLM implementation
class LLMBase(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def generate(self, prompt, system):
        pass

# Anthropic llm model class
class AnthropicLLM(LLMBase):

    def __init__(self, config):
        import anthropic
        self.model = config['model']
        self.max_tokens = config.get('max_tokens', 2048)
        self.client = anthropic.Anthropic()

    def generate(self, prompt, system=None):
        """Generate output text using user prompt and system message"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class LLMClientFactory():

    def __init__(self, config):
        self.client_map = {
            "anthropic": AnthropicLLM
        }
        llm_config = config.get("LLM_CONFIG", {})
        default_provider = llm_config.get("DEFAULT_PROVIDER")
        provider_class = self.client_map.get(default_provider)
        if not provider_class:
            raise ValueError("DEFAULT_PROVIDER not present in config")
        provider_config = llm_config.get("PROVIDERS", {}).get(default_provider)
        self.client = provider_class(provider_config)
