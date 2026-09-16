import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx
from google import genai
from google.genai import types
import anthropic

import config
from config import (
    AI_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    HERMES_API_KEY,
    HERMES_MODEL,
    HERMES_BASE_URL,
    MAX_MESSAGES_PER_CHUNK,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Anda adalah asisten AI Telegram profesional bernama "Chat Summarizer".
Tugas Anda adalah membaca histori percakapan grup Telegram dan menyusun ringkasan yang terstruktur, padat, bernilai tinggi, dan mudah dibaca di layar HP (Telegram Mobile).

Format output WAJIB mengikuti struktur berikut (gunakan emoji dan bold Markdown):

📌 *TOPIK UTAMA*
- [Ringkasan topik atau pembahasan yang terjadi]

✅ *KEPUTUSAN & KESEPAKATAN*
- [Keputusan final, kesimpulan rapat/diskusi, atau konsensus yang disepakati (tulis 'Tidak ada keputusan khusus' jika hanya obrolan santai)]

📋 *ACTION ITEMS & TINDAK LANJUT*
- [Tugas/Follow-up] — PIC/Disebut oleh: @username atau Nama (tulis 'Tidak ada action item' jika tidak ada)

🔗 *LINK & REFERENSI PENTING*
- [Keterangan singkat]: url_lengkap (tulis 'Tidak ada tautan dibagikan' jika tidak ada)

Pedoman penulisan:
1. Gunakan Bahasa Indonesia yang ringkas, profesional, dan to-the-point.
2. Abaikan obrolan basa-basi (small talk/greeting) yang tidak memiliki nilai informasi penting.
3. Sebutkan nama/username pengirim saat relevan dengan keputusan atau penugasan tugas.
4. Jangan halusinasi; rangkum hanya fakta yang tertulis dalam transkrip chat.
"""

def format_messages_transcript(messages: List[Dict[str, Any]]) -> str:
    """Format daftar pesan dari DB menjadi teks transkrip terstruktur."""
    lines = []
    for msg in messages:
        sender = msg.get("full_name") or msg.get("username") or f"User_{msg.get('user_id')}"
        username_tag = f" (@{msg['username']})" if msg.get("username") else ""
        
        try:
            ts = datetime.fromisoformat(msg["timestamp"])
            time_str = ts.strftime("%d/%m %H:%M")
        except Exception:
            time_str = str(msg.get("timestamp", ""))
            
        text = msg.get("text", "").replace("\n", " ")
        lines.append(f"[{time_str}] {sender}{username_tag}: {text}")
        
    return "\n".join(lines)

def chunk_messages(messages: List[Dict[str, Any]], chunk_size: int = MAX_MESSAGES_PER_CHUNK) -> List[List[Dict[str, Any]]]:
    """Membagi pesan menjadi beberapa batch jika jumlah pesan sangat banyak."""
    return [messages[i:i + chunk_size] for i in range(0, len(messages), chunk_size)]

class ChatSummarizer:
    def __init__(self):
        self.provider = config.AI_PROVIDER
        self.gemini_client: Optional[genai.Client] = None
        self.anthropic_client: Optional[anthropic.AsyncAnthropic] = None

        if self.provider == "gemini":
            if config.GEMINI_API_KEY:
                self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
            self.model = config.GEMINI_MODEL
        elif self.provider == "anthropic":
            if config.ANTHROPIC_API_KEY:
                self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
            self.model = config.ANTHROPIC_MODEL
        else:
            self.provider = "hermes"
            self.model = config.HERMES_MODEL

    async def _call_gemini(self, prompt: str) -> str:
        """Panggil Google Gemini API (Gratis) dengan retry otomatis & fallback jika server busy 503."""
        if not self.gemini_client:
            self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

        models_to_try = [self.model, "gemini-flash-latest", "gemini-pro-latest", "gemini-3.5-flash"]
        last_exception = None

        for target_model in models_to_try:
            for attempt in range(2):
                try:
                    response = await self.gemini_client.aio.models.generate_content(
                        model=target_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            max_output_tokens=2048,
                            temperature=0.3,
                        )
                    )
                    if response and response.text:
                        return response.text
                except Exception as e:
                    last_exception = e
                    err_str = str(e).lower()
                    if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                        logger.warning("Gemini model %s quota exceeded (429), trying fallback model %s...", target_model, models_to_try[min(models_to_try.index(target_model)+1, len(models_to_try)-1)])
                        break  # Langsung coba model cadangan berikutnya!
                    elif "404" in err_str or "not_found" in err_str:
                        break
                    elif "503" in err_str or "unavailable" in err_str:
                        logger.warning("Gemini API (%s) busy (attempt %d/2): %s. Retrying...", target_model, attempt+1, e)
                        await asyncio.sleep(2)
                    else:
                        break

        if last_exception:
            raise last_exception
        return ""

    async def _call_anthropic(self, prompt: str) -> str:
        """Panggil Claude Anthropic API."""
        if not self.anthropic_client:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

        response = await self.anthropic_client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text

    async def _call_hermes(self, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
        """Panggil Hermes AI API via OpenRouter / Ollama (OpenAI-compatible endpoint)."""
        headers = {"Content-Type": "application/json"}
        if config.HERMES_API_KEY:
            headers["Authorization"] = f"Bearer {config.HERMES_API_KEY}"
        if "openrouter" in config.HERMES_BASE_URL.lower():
            headers["HTTP-Referer"] = "https://github.com/ai-agent/telegram-bot"
            headers["X-Title"] = "Telegram Chat Assistant"

        url = f"{config.HERMES_BASE_URL.rstrip('/')}/chat/completions"
        models_to_try = [
            self.model,
            "openrouter/auto",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "google/gemma-2-9b-it:free"
        ]

        last_err = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for model_name in models_to_try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.5,
                    "max_tokens": 2048
                }
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = msg.get("content")
                    if not content and msg.get("reasoning"):
                        content = msg.get("reasoning")
                    if content and str(content).strip():
                        return str(content)
                    logger.warning("OpenRouter model %s returned empty/null content: %s", model_name, data)
                else:
                    logger.warning("OpenRouter model %s returned status %d: %s", model_name, resp.status_code, resp.text)
                    last_err = f"OpenRouter Error ({resp.status_code}): {resp.text}"

        raise RuntimeError(last_err or "OpenRouter call failed")

    async def summarize_chunk(self, transcript: str, is_intermediate: bool = False) -> str:
        """Panggil LLM untuk meringkas transkrip chat dengan fallback otomatis antar provider."""
        prompt = (
            f"Berikut adalah transkrip obrolan grup Telegram:\n\n"
            f"================ TRANSKRIP ================\n"
            f"{transcript}\n"
            f"===========================================\n\n"
        )
        if is_intermediate:
            prompt += (
                "Tolong rangkum semua poin utama, topik yang dibicarakan, keputusan, penugasan/action items, "
                "dan link yang terdapat pada transkrip obrolan di atas. Catat fakta-fakta obrolan secara langsung dan padat."
            )
        else:
            prompt += "Tolong buat ringkasan lengkap sesuai format standar yang telah ditentukan."

        # Coba provider utama, jika gagal coba provider cadangan
        primary = self.provider
        fallback = "hermes" if primary == "gemini" else "gemini"

        try:
            if primary == "gemini":
                return await self._call_gemini(prompt)
            elif primary == "anthropic":
                return await self._call_anthropic(prompt)
            else:
                return await self._call_hermes(prompt)
        except Exception as primary_err:
            logger.warning("Provider utama %s gagal: %s. Mencoba provider cadangan %s...", primary, primary_err, fallback)
            try:
                if fallback == "gemini" and config.GEMINI_API_KEY:
                    return await self._call_gemini(prompt)
                elif fallback == "hermes" and config.HERMES_API_KEY:
                    return await self._call_hermes(prompt)
            except Exception as fallback_err:
                logger.error("Provider cadangan %s juga gagal: %s", fallback, fallback_err)
            
            raise primary_err

    async def chat_reply(self, user_message: str, history_context: str = "") -> str:
        """Memproses pesan percakapan langsung pengguna (Chat Interaktif)."""
        chat_system_prompt = (
            "Anda adalah asisten AI Telegram bernama Chat Assistant yang ramah, sopan, cerdas, dan sigap. "
            "Tugas Anda adalah membalas obrolan atau menjawab pertanyaan pengguna dengan Bahasa Indonesia yang jelas, "
            "akurat, dan bermanfaat. Gunakan format Markdown yang rapi jika diperlukan."
        )
        
        prompt = user_message
        if history_context:
            prompt = f"Konteks obrolan sebelumnya:\n{history_context}\n\nPesan pengguna saat ini: {user_message}"

        try:
            if self.provider == "gemini":
                if not self.gemini_client:
                    self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=chat_system_prompt,
                        max_output_tokens=2048,
                        temperature=0.7,
                    )
                )
                return response.text or ""
            elif self.provider == "anthropic":
                if not self.anthropic_client:
                    self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
                response = await self.anthropic_client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=chat_system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
            else:
                return await self._call_hermes(prompt, system_instruction=chat_system_prompt)
        except Exception as e:
            logger.exception("Error standard chat response: %s", e)
            return f"❌ *Maaf, terjadi kesalahan saat memproses jawaban:* {str(e)}"

    async def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        timeframe_info: str = ""
    ) -> str:
        """
        Meringkas daftar pesan. Jika jumlah pesan sangat banyak, 
        menggunakan pendekatan Hierarchical / Map-Reduce chunking.
        """
        if not messages:
            return "⚠️ Tidak ada pesan baru untuk diringkas."

        total_msgs = len(messages)
        chunks = chunk_messages(messages, MAX_MESSAGES_PER_CHUNK)

        logger.info("Processing summary for %d messages across %d chunk(s) using %s (%s)", 
                    total_msgs, len(chunks), self.provider, self.model)

        try:
            if len(chunks) == 1:
                transcript = format_messages_transcript(chunks[0])
                summary_content = await self.summarize_chunk(transcript, is_intermediate=False)
            else:
                intermediate_summaries = []
                for idx, chunk in enumerate(chunks, 1):
                    logger.info("Summarizing chunk %d/%d...", idx, len(chunks))
                    chunk_transcript = format_messages_transcript(chunk)
                    chunk_summary = await self.summarize_chunk(chunk_transcript, is_intermediate=True)
                    intermediate_summaries.append(f"### Bagian {idx}:\n{chunk_summary}")

                combined_intermediates = "\n\n".join(intermediate_summaries)
                consolidation_prompt = (
                    f"Berikut adalah ringkasan parsial dari percakapan grup bervolume tinggi ({total_msgs} pesan):\n\n"
                    f"{combined_intermediates}\n\n"
                    f"Tolong gabungkan semua informasi parsial di atas menjadi SATU ringkasan komprehensif tanpa duplikasi. "
                    f"WAJIB ikuti struktur format standar berikut:\n\n"
                    f"📌 *TOPIK UTAMA*\n"
                    f"- [Daftar topik/pembahasan utama]\n\n"
                    f"✅ *KEPUTUSAN & KESEPAKATAN*\n"
                    f"- [Hasil keputusan atau tulis 'Tidak ada keputusan khusus']\n\n"
                    f"📋 *ACTION ITEMS & TINDAK LANJUT*\n"
                    f"- [Daftar penugasan/follow up atau tulis 'Tidak ada action item']\n\n"
                    f"🔗 *LINK & REFERENSI PENTING*\n"
                    f"- [Tautan/referensi dibagikan atau tulis 'Tidak ada tautan dibagikan']"
                )

                summary_content = await self.summarize_chunk(consolidation_prompt, is_intermediate=False)

            if self.provider == "gemini":
                ai_label = "Google Gemini AI (Gratis)"
            elif self.provider == "anthropic":
                ai_label = f"Claude ({self.model})"
            else:
                ai_label = f"Nous-Hermes ({self.model})"

            header = f"📊 *RINGKASAN CHAT GRUP*\n"
            if timeframe_info:
                header += f"🕒 Periode: _{timeframe_info}_\n"
            header += f"💬 Total Pesan: *{total_msgs} pesan*\n\n"
            
            footer = f"\n\n_— Diringkas otomatis dengan {ai_label}_"
            return f"{header}{summary_content}{footer}"

        except Exception as e:
            logger.exception("Error during summarization: %s", e)
            err_str = str(e)
            if "API_KEY" in err_str.upper() or "API KEY" in err_str.upper() or "INVALID" in err_str.upper():
                return f"❌ *Error API Key:* API Key {self.provider.upper()} tidak valid atau belum diisi. Periksa file `.env`."
            elif "RESOURCE_EXHAUSTED" in err_str or "RATE_LIMIT" in err_str.upper():
                return f"⏳ *Error Rate Limit:* Terkena kuota limit {self.provider.upper()}. Silakan coba lagi sebentar lagi."
            return f"❌ *Terjadi kesalahan saat memproses ringkasan:* {err_str}"
