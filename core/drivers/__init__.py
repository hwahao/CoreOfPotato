from .gemini import GeminiDriver
from .chatgpt import ChatGPTDriver
from .grok import GrokDriver

DRIVERS = {
    'gemini': GeminiDriver,
    'chatgpt': ChatGPTDriver,
    'grok': GrokDriver
}

def get_driver(name: str):
    """Retrieve driver class by name."""
    return DRIVERS.get(name.lower())
