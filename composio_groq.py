# composio_groq.py — Local adapter/compatibility layer for Groq integration
# Since the official composio SDK formats tool calling for OpenAI (which includes 'strict' flags),
# we override wrap_tools to strip the 'strict' field so that Groq does not throw 400 validation errors.

from composio_openai import OpenAIProvider

class GroqProvider(OpenAIProvider, name="groq"):
    def wrap_tools(self, tools):
        wrapped = super().wrap_tools(tools)
        if isinstance(wrapped, list):
            for tool in wrapped:
                if isinstance(tool, dict) and "function" in tool:
                    tool["function"].pop("strict", None)
        return wrapped

__all__ = ["GroqProvider"]
