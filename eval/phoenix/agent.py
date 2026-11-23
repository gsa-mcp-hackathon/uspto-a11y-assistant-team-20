"""AltTextAgent — a LangChain agent wired to the alt-text-mcp server for Phoenix evals.

Owns three things:
  1. Phoenix/OpenTelemetry instrumentation (so every tool call and LLM turn is traced).
  2. The MCP client, which launches alt-text-mcp's `main.py` over stdio.
  3. The LangChain agent itself, built from the MCP-exposed tools + a versioned
     system prompt.

Run standalone for a smoke test:
    uv run python agent.py
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.client import MultiServerMCPClient
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

# Repo root, so the stdio launch command resolves regardless of invocation cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# This file's directory, so prompt files resolve regardless of invocation cwd.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_PROJECT_NAME = "alt-text-mcp-eval"


class AltTextAgent:
    """LangChain agent that can only see the world through alt-text-mcp's tools."""

    def __init__(
        self,
        system_prompt_version: str = "v1",
        project_name: str = DEFAULT_PROJECT_NAME,
    ) -> None:
        self.system_prompt_version = system_prompt_version
        self.project_name = project_name
        self.client: MultiServerMCPClient | None = None
        self.agent = None

    async def initialize(self) -> None:
        """Wire up Phoenix tracing, launch the MCP server, and build the agent."""
        load_dotenv()

        # 1. Phoenix/OpenTelemetry instrumentation — do this before building the
        #    agent so the MCP tool calls and LLM turns below are traced.
        endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317")
        tracer_provider = register(project_name=self.project_name, endpoint=endpoint)
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

        # 2. Launch alt-text-mcp over stdio. Its real entrypoint is main.py at the
        #    repo root (not src/alt_text_mcp/app.py), so cwd + args point there.
        #    UV_SYSTEM_CERTS=1 is required on this network: `uv run` otherwise
        #    fails its own resolve/build check against a TLS-inspecting proxy
        #    (see memory: netskope-proxy-tls-fix) before the server ever starts.
        self.client = MultiServerMCPClient(
            {
                "alt_text_server": {
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", "main.py"],
                    "cwd": REPO_ROOT,
                    "env": {**os.environ, "UV_SYSTEM_CERTS": "1"},
                },
            }
        )
        tools = await self.client.get_tools()

        # 3. Build the LangChain agent against AWS Bedrock. AGENT_MODEL is a
        #    Bedrock model id or application-inference-profile ARN; standard
        #    boto3 credential resolution picks up AWS_PROFILE/AWS_REGION (or
        #    an explicit credentials_profile_name below) — no API key needed.
        model = ChatBedrockConverse(
            model_id=os.getenv("AGENT_MODEL"),
            # Required when model_id is an application-inference-profile ARN
            # (unlike a plain model id, the provider can't be inferred from it).
            provider="anthropic",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            credentials_profile_name=os.getenv("AWS_PROFILE"),
            temperature=0,
        )
        self.agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=self._load_system_prompt(self.system_prompt_version),
        )

    def _load_system_prompt(self, version: str = "v1") -> str:
        prompt_path = os.path.join(_THIS_DIR, "prompts", f"system_prompt_{version}.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    async def run(self, query: str) -> str:
        """Invoke the agent with a single query and return its final text answer."""
        if self.agent is None:
            raise RuntimeError(
                "AltTextAgent.initialize() must be awaited before run()."
            )

        result = await self.agent.ainvoke({"messages": [("user", query)]})
        messages = result["messages"]
        final_message = messages[-1]
        content = getattr(final_message, "content", final_message)

        # Some chat models return a list of content blocks instead of a plain
        # string; flatten to text defensively.
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(block.get("text", ""))
                else:
                    parts.append(str(block))
            return "".join(parts)
        return content

    def create_experiment_task(self):
        """Return a sync `task(example)` closure for Phoenix's run_experiment.

        Phoenix experiments expect synchronous task functions, so this wraps the
        async `run()` with `asyncio.run(...)`.
        """

        def task(example):
            return asyncio.run(self.run(example.input["query"]))

        return task


async def main() -> None:
    """Standalone smoke test: initialize the agent and run one sample question."""
    agent = AltTextAgent()
    await agent.initialize()

    # The lang-attribute question from datasets/alt-text-eval-0/evaluation.xml.
    sample_query = (
        "Check the root language attribute of both "
        "https://www.w3.org/WAI/demos/bad/before/home.html and "
        "https://www.w3.org/WAI/demos/bad/after/home.html. One of the two pages "
        "declares a lang value that is completely absent on the other page. "
        "What is that lang value?"
    )
    answer = await agent.run(sample_query)
    print(f"Query: {sample_query}\n")
    print(f"Answer: {answer}")


if __name__ == "__main__":
    asyncio.run(main())
