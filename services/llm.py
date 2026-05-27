"""
services/llm.py
───────────────
LLM service ผ่าน Ollama (local, no internet)
- รองรับ tool calling ผ่าน LangChain agent
- inject memory history ใน context window
- retry + timeout ป้องกัน hang
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from config.prompts import get_system_prompt
from config.settings import Settings
from core.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

log = get_logger(__name__)


class LLMService:
    """Wrapper รอบ Ollama LLM"""

    def __init__(self, settings: Settings) -> None:
        self._cfg = settings.llm
        self._settings = settings
        self._llm = ChatOllama(
            model=self._cfg.model,
            base_url=self._cfg.base_url,
            temperature=self._cfg.temperature,
            num_predict=self._cfg.max_tokens,
            num_ctx=self._cfg.context_window,
            timeout=self._cfg.timeout,
        )
        log.info("llm_ready", model=self._cfg.model, base_url=self._cfg.base_url)

    # ── Connectivity Check ────────────────────────────────────────────────

    def health_check(self) -> bool:
        """เช็คว่า Ollama รันอยู่และ model พร้อมใช้"""
        try:
            import httpx
            r = httpx.get(f"{self._cfg.base_url}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            base = self._cfg.model.split(":")[0]
            ok = any(base in m for m in models)
            if not ok:
                log.warning(
                    "llm_model_not_found",
                    model=self._cfg.model,
                    available=models,
                )
            return ok
        except Exception as exc:
            log.error("llm_health_check_failed", error=str(exc))
            return False

    # ── Chat ──────────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        context: list[str] | None = None,
    ) -> str:
        """
        ส่งข้อความและรับการตอบกลับ
        history : list ของ {"role": "user"|"assistant", "content": "..."}
        context : relevant memories จาก long-term store
        """
        messages = []

        # System prompt
        system_text = get_system_prompt(
            name=self._settings.assistant_name,
            language=self._settings.language,
        )
        # ถ้ามี context จาก long-term memory ให้เพิ่มเข้าไป
        if context:
            context_block = "\n\nข้อมูลจากความทรงจำที่อาจเกี่ยวข้อง:\n"
            context_block += "\n".join(f"- {c}" for c in context[:3])
            system_text += context_block

        messages.append(SystemMessage(content=system_text))

        # History
        for msg in (history or []):
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        # Current message
        messages.append(HumanMessage(content=user_message))

        try:
            response = self._llm.invoke(messages)
            reply = str(response.content).strip()
            log.debug(
                "llm_response",
                input_chars=len(user_message),
                output_chars=len(reply),
            )
            return reply
        except Exception as exc:
            log.error("llm_invoke_failed", error=str(exc))
            return "ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้ง"

    # ── With Tools ────────────────────────────────────────────────────────

    def chat_with_tools(
        self,
        user_message: str,
        tools: list["BaseTool"],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """ใช้ LangChain agent เมื่อต้องการ tool calling"""
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        system_text = get_system_prompt(
            name=self._settings.assistant_name,
            language=self._settings.language,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        llm_with_tools = self._llm.bind_tools(tools)
        agent = create_tool_calling_agent(llm_with_tools, tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            max_iterations=5,
            verbose=self._settings.debug,
            handle_parsing_errors=True,
        )

        chat_history = []
        for msg in (history or []):
            if msg["role"] == "user":
                chat_history.append(HumanMessage(content=msg["content"]))
            else:
                chat_history.append(AIMessage(content=msg["content"]))

        try:
            result = executor.invoke({
                "input": user_message,
                "chat_history": chat_history,
            })
            return str(result.get("output", "")).strip()
        except Exception as exc:
            log.error("llm_agent_failed", error=str(exc))
            return self.chat(user_message, history)  # fallback ไม่ใช้ tools
