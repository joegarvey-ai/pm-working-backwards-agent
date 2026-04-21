"""Verify the LLM selector picks up the correct provider from .env."""
from dotenv import load_dotenv

load_dotenv()

from pm_agent_system.crew import _LLM_PROVIDER, _MODEL, _llm

print(f"Provider: {_LLM_PROVIDER}")
print(f"Model (tracked): {_MODEL}")
llm = _llm()
print(f"LLM instance type: {type(llm).__name__}")
print(f"LLM model: {getattr(llm, 'model', '?')}")
