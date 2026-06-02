"""
services/llm.py — LLM service ผ่าน Ollama (local, no internet)

FIX-F: เพิ่ม summarize() method ที่ไม่ inject system prompt assistant persona
       เพื่อให้ memory._maybe_summarize() เรียกใช้ได้ถูกต้อง
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
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm = ChatOllama(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            num_predict=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )
        log.info("llm_ready", model=settings.llm_model, base_url=settings.llm_base_url)

    # ── Health ────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self._settings.llm_base_url}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            base = self._settings.llm_model.split(":")[0]
            ok = any(base in m for m in models)
            if not ok:
                log.warning("llm_model_not_found", model=self._settings.llm_model,
                            available=models)
            return ok
        except Exception as exc:
            log.error("llm_health_check_failed", error=str(exc))
            return False

    # ── Chat (with assistant persona + system prompt) ─────────────────────

    def chat(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        context: list[str] | None = None,
    ) -> str:
        """ตอบโต้ปกติ — inject system prompt assistant persona เสมอ"""
        messages: list = []

        system_text = get_system_prompt(
            name=self._settings.assistant_name,
            language=self._settings.language,
        )
        if context:
            system_text += "\n\nข้อมูลจากความทรงจำที่อาจเกี่ยวข้อง:\n"
            system_text += "\n".join(f"- {c}" for c in context[:3])

        messages.append(SystemMessage(content=system_text))

        for msg in (history or []):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            # role == "system" → skip (already in system_text)

        messages.append(HumanMessage(content=user_message))

        try:
            response = self._llm.invoke(messages)
            reply = str(response.content).strip()
            log.debug("llm_response", input_chars=len(user_message), output_chars=len(reply))
            return reply
        except Exception as exc:
            log.error("llm_invoke_failed", error=str(exc))
            return "ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่อีกครั้ง"

    # ── Summarize (FIX-F: neutral — no assistant persona) ─────────────────

    def summarize(self, text: str) -> str:
        """
        เรียกใช้ LLM แบบ neutral ไม่ inject system prompt assistant persona
        ใช้สำหรับ: memory summarization, document processing
        Returns: summarized text หรือ fallback string
        """
        messages = [
            SystemMessage(content=(
                "คุณเป็น summarizer ที่เป็นกลาง "
                "สรุปข้อความที่รับมาให้กระชับ ตรงประเด็น "
                "ห้ามแต่งเนื้อหาเพิ่ม ห้ามตอบในฐานะ assistant"
            )),
            HumanMessage(content=text),
        ]
        try:
            response = self._llm.invoke(messages)
            result = str(response.content).strip()
            log.debug("llm_summarize", input_chars=len(text), output_chars=len(result))
            return result
        except Exception as exc:
            log.error("llm_summarize_failed", error=str(exc))
            return ""

    # ── Chat with tools (LangChain agent) ────────────────────────────────

    def chat_with_tools(
        self,
        user_message: str,
        tools: list["BaseTool"],
        history: list[dict[str, str]] | None = None,
    ) -> str:
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

        chat_history: list = []
        for msg in (history or []):
            role = msg.get("role", "")
            if role == "user":
                chat_history.append(HumanMessage(content=msg["content"]))
            elif role == "assistant":
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
