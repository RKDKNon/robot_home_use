import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

class ReasoningClient:
    """Client for mimo-v2.5-pro reasoning model via Anthropic-compatible API.

    Used for complex health questions that need deep analysis beyond
    what Gemini Live API can handle in real-time conversation.
    """

    def __init__(self):
        self.api_url = os.getenv("REASONING_API_URL", "https://token-plan-sgp.xiaomimimo.com/anthropic")
        self.api_key = os.getenv("REASONING_API_KEY", "")
        self.model = os.getenv("REASONING_MODEL", "mimo-v2.5-pro")
        self._client = None

    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(
                    api_key=self.api_key,
                    base_url=self.api_url
                )
            except ImportError:
                print("❌ anthropic package not installed. pip install anthropic")
                return None
        return self._client

    async def ask(self, question: str, context: str = "") -> str:
        """Send a complex question to mimo-v2.5-pro for deep reasoning.

        Args:
            question: The patient's question or health concern
            context: Optional conversation/vital context

        Returns:
            The model's reasoning response as text
        """
        client = self._get_client()
        if not client:
            return "ขออภัยครับ ระบบคิดเชิงลึกยังไม่พร้อมใช้งาน"

        system_prompt = (
            "คุณเป็นผู้ช่วยสุขภาพ AI ที่เชี่ยวชาญ ตอบคำถามสุขภาพด้วยภาษาไทยที่เข้าใจง่าย "
            "สำหรับผู้สูงอายุ ให้คำแนะนำที่ปลอดภัย ไม่วินิจฉัยโรค ไม่สั่งยา "
            "ตอบสั้นกระชับ ไม่เกิน 3-4 ประโยค เน้นความชัดเจนและปลอดภัย"
        )

        if context:
            system_prompt += f"\n\nบริบทเพิ่มเติม:\n{context}"

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": question}
                ]
            )
            # Extract text from response
            if response.content and len(response.content) > 0:
                return response.content[0].text
            return "ไม่สามารถวิเคราะห์ได้ครับ"
        except Exception as e:
            print(f"❌ Reasoning API error: {e}")
            return f"ขออภัยครับ เกิดข้อผิดพลาดในการวิเคราะห์: {str(e)}"

    async def health_check(self) -> bool:
        """Check if the reasoning API is accessible."""
        try:
            result = await self.ask("สวัสดี")
            return len(result) > 0
        except Exception:
            return False


if __name__ == "__main__":
    async def test():
        client = ReasoningClient()
        print(f"API URL: {client.api_url}")
        print(f"Model: {client.model}")
        result = await client.ask("พาราเซตามอลกินกับยาความดันได้ไหม")
        print(f"Response: {result}")

    asyncio.run(test())
