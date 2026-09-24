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
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_BASE_URL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    HERMES_API_KEY,
    HERMES_MODEL,
    HERMES_BASE_URL,
    MAX_MESSAGES_PER_CHUNK,
    FAST_SUMMARY_MAX_MESSAGES,
)

logger = logging.getLogger(__name__)

import re

SYSTEM_PROMPT = """Anda adalah asisten AI Telegram profesional dan cerdas bernama "Chat Summarizer".
Tugas Anda adalah menganalisis histori obrolan grup Telegram dan menyusun Executive Summary yang CERDAS, KAYA INFORMASI, SPESIFIK, dan TO-THE-POINT.

PRINSIP UTAMA:
- WAJIB MENGGUNAKAN BAHASA INDONESIA YANG BAIK, PADAT, DAN CERDAS.
- JANGAN ASAL MENGURANGI DETAIL PENTING: Tangkap fakta teknis spesifik, nama tools/produk, metode/solusi, angka, harga, tanggal/jam, status, tugas, dan username (@username) yang relevan.
- BACA SELURUH TRANSKRIP SEBELUM MENULIS. Kelompokkan pesan berdasarkan topik/isu, lalu catat siapa melakukan apa, kapan, hasil/statusnya, kendala, dan tindak lanjutnya.
- Pertahankan detail penting meskipun hanya muncul satu kali. Jangan menebak atau mengarang; bedakan keputusan final dari usulan, pertanyaan, dan opini.
- DILARANG KERAS MENAMPILKAN LANGKAH BERPIKIR / REASONING / ANALISIS INTERNAL (seperti '1. Analyze the Request:', '2. Analyze the Transcript:'). LANGSUNG MULAI HASIL DARI '📌 *TOPIK UTAMA*'.
- HINDARI KALIMAT SAMAR/GENERIK: Tuliskan fakta langsung dan jelas.
- BUANG FLUFF & BASA-BASI: Hapus kata pengantar, catatan internal, dan obrolan santai.
- Jangan membatasi ringkasan menjadi hanya 2-3 poin jika ada beberapa topik berbeda. Gunakan sub-poin seperlunya.

FORMAT WAJIB:

📌 *TOPIK UTAMA*
• [Poin pembahasan utama kaya detail teknis & spesifik]

✅ *KEPUTUSAN & KESEPAKATAN*
• [Keputusan/kesepakatan rapat/operasional spesifik atau 'Tidak ada keputusan khusus']

📋 *ACTION ITEMS & TINDAK LANJUT*
• [Tugas/follow-up spesifik beserta @username PIC & konteksnya atau 'Tidak ada action item']

🔗 *LINK & REFERENSI PENTING*
• [Keterangan singkat]: url_lengkap (atau 'Tidak ada tautan dibagikan')
"""

def clean_summary_output(text: str) -> str:
    """Bersihkan output LLM dari reasoning/chain-of-thought dan rapikan format Telegram Markdown."""
    if not text:
        return ""
    
    # 1. Hapus thinking/reasoning di awal (potong teks sebelum 📌 jika ada)
    idx = text.find("📌")
    if idx != -1:
        text = text[idx:]
    else:
        # Jika 📌 tidak ditemukan, coba cari header lain
        for header in ["TOPIK UTAMA", "KEPUTUSAN", "ACTION ITEMS"]:
            h_idx = text.find(header)
            if h_idx != -1:
                line_start = text.rfind("\n", 0, h_idx)
                text = text[line_start + 1:] if line_start != -1 else text[h_idx:]
                break

    # 2. Rapikan tautan markdown ganda seperti [https://url](https://url)
    text = re.sub(r'\[(https?://[^\s\]]+)\]\(\1\)', r'\1', text)

    # 3. Rapikan bullet point ganda seperti * *Topik*: atau * - Poin
    text = re.sub(r'^\s*[\*\-]\s*[\*\-]\s*', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[\*\-]\s+', '• ', text, flags=re.MULTILINE)

    # 4. Pastikan header standar memiliki format Telegram Bold yang rapi
    text = re.sub(r'📌\s*\*?TOPIK UTAMA\*?:?', '📌 *TOPIK UTAMA*', text)
    text = re.sub(r'✅\s*\*?KEPUTUSAN\s*(&|DAN)?\s*KESEPAKATAN\*?:?', '✅ *KEPUTUSAN & KESEPAKATAN*', text)
    text = re.sub(r'📋\s*\*?ACTION ITEMS\s*(&|DAN)?\s*TINDAK LANJUT\*?:?', '📋 *ACTION ITEMS & TINDAK LANJUT*', text)
    text = re.sub(r'🔗\s*\*?LINK\s*(&|DAN)?\s*REFERENSI PENTING\*?:?', '🔗 *LINK & REFERENSI PENTING*', text)

    return text.strip()

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
    if chunk_size <= 0:
        chunk_size = MAX_MESSAGES_PER_CHUNK
    return [messages[i:i + chunk_size] for i in range(0, len(messages), chunk_size)]


def get_summary_chunk_plan(message_count: int) -> int:
    """Pilih strategi pemecahan ringkasan yang lebih cepat untuk jumlah pesan normal."""
    if message_count <= FAST_SUMMARY_MAX_MESSAGES:
        return 1
    if message_count <= MAX_MESSAGES_PER_CHUNK * 2:
        return 2
    return max(2, min(4, (message_count + FAST_SUMMARY_MAX_MESSAGES - 1) // FAST_SUMMARY_MAX_MESSAGES))

class ChatSummarizer:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = (provider or config.AI_PROVIDER).strip().lower()
        if self.provider in ["gpt", "chatgpt", "openai"]:
            self.provider = "openai"
        self.gemini_client: Optional[genai.Client] = None
        self.anthropic_client: Optional[anthropic.AsyncAnthropic] = None

        if self.provider == "gemini":
            if config.GEMINI_API_KEY:
                self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
            self.model = model or config.GEMINI_MODEL
        elif self.provider == "openai":
            self.model = model or config.OPENAI_MODEL
        elif self.provider == "anthropic":
            if config.ANTHROPIC_API_KEY:
                self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
            self.model = model or config.ANTHROPIC_MODEL
        else:
            self.provider = "hermes"
            self.model = model or config.HERMES_MODEL

    async def _call_openai(self, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
        """Panggil OpenAI GPT API (gpt-4o, gpt-4o-mini, dll)."""
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY belum diisi di file .env!")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.OPENAI_API_KEY}"
        }
        url = f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        model_name = self.model if (self.model and ("gpt" in self.model.lower() or "o1" in self.model.lower() or "o3" in self.model.lower())) else config.OPENAI_MODEL

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 2048
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if content and str(content).strip():
                    return str(content)
                raise RuntimeError("OpenAI API returned empty response content.")
            else:
                raise RuntimeError(f"OpenAI API Error ({resp.status_code}): {resp.text}")

    async def _call_gemini(self, prompt: str) -> str:
        """Panggil Google Gemini dengan retry otomatis & fallback model jika 503 high demand."""
        if not self.gemini_client:
            self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

        models_to_try = []
        if self.model and self.model.startswith("gemini"):
            models_to_try.append(self.model)
        for m in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"]:
            if m not in models_to_try:
                models_to_try.append(m)

        first_exception = None
        last_exception = None
        for target_model in models_to_try:
            for attempt in range(3):
                try:
                    response = await self.gemini_client.aio.models.generate_content(
                        model=target_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            max_output_tokens=2048,
                            temperature=0.2,
                        )
                    )
                    if response and response.text:
                        return response.text
                except Exception as e:
                    if first_exception is None:
                        first_exception = e
                    last_exception = e
                    err_str = str(e).lower()
                    if "503" in err_str or "unavailable" in err_str or "high demand" in err_str:
                        logger.warning("Gemini model %s 503 high demand (attempt %d/3), waiting 1.5s...", target_model, attempt + 1)
                        await asyncio.sleep(1.5)
                        continue
                    if "404" in err_str or "not_found" in err_str:
                        logger.warning("Gemini model %s not found, trying next model...", target_model)
                        break
                    if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                        logger.warning("Gemini model %s rate limited, trying next model...", target_model)
                        break
                    logger.warning("Gemini model %s failed: %s", target_model, e)
                    break

        if first_exception and ("404" not in str(first_exception).lower() and "not_found" not in str(first_exception).lower()):
            raise first_exception
        if last_exception:
            raise last_exception
        return ""

    async def _call_anthropic(self, prompt: str) -> str:
        """Panggil Claude Anthropic API."""
        if not self.anthropic_client:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

        model_name = self.model if self.model.startswith("claude") else config.ANTHROPIC_MODEL
        response = await self.anthropic_client.messages.create(
            model=model_name,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text

    async def _call_hermes(self, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
        """Panggil Hermes AI API dengan retry terbatas agar ringkasan cepat."""
        headers = {"Content-Type": "application/json"}
        if config.HERMES_API_KEY:
            headers["Authorization"] = f"Bearer {config.HERMES_API_KEY}"
        if "openrouter" in config.HERMES_BASE_URL.lower():
            headers["HTTP-Referer"] = "https://github.com/ai-agent/telegram-bot"
            headers["X-Title"] = "Telegram Chat Assistant"

        url = f"{config.HERMES_BASE_URL.rstrip('/')}/chat/completions"
        models_to_try = []
        if self.model and not self.model.startswith("gemini") and not self.model.startswith("claude"):
            models_to_try.append(self.model)
        for m in [
            "nex-agi/nex-n2.5-mini:free",
            "nex-agi/nex-n2.5-pro:free",
            "nvidia/nemotron-3.5-lightning:free",
            "qwen/qwen3.8-27b:free",
            "dots-studio/dots-3-note-preview:free",
            "liquid/lfm-2.5-2.6b:free",
            "openrouter/auto"
        ]:
            if m not in models_to_try:
                models_to_try.append(m)

        last_err = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            for model_name in models_to_try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2048
                }
                try:
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
                    elif resp.status_code in [429, 503]:
                        logger.warning("OpenRouter model %s rate limited (%d), trying next model...", model_name, resp.status_code)
                        last_err = f"OpenRouter Error ({resp.status_code}): {resp.text}"
                        continue
                    elif resp.status_code in [400, 402, 404]:
                        logger.warning("OpenRouter model %s error status %d, skipping to next model...", model_name, resp.status_code)
                        last_err = f"OpenRouter Error ({resp.status_code}): {resp.text}"
                        continue
                    else:
                        logger.warning("OpenRouter model %s returned status %d: %s", model_name, resp.status_code, resp.text)
                        last_err = f"OpenRouter Error ({resp.status_code}): {resp.text}"
                        continue
                except Exception as req_err:
                    logger.warning("OpenRouter request error on %s: %s", model_name, req_err)
                    last_err = str(req_err)
                    continue

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
                "Buat CATATAN FAKTA untuk tahap penggabungan berikutnya, bukan ringkasan pendek yang menghilangkan detail. "
                "Kelompokkan seluruh topik/isu dan untuk setiap topik catat fakta penting, angka/tanggal/jam, nama alat atau dokumen, "
                "pertanyaan/kendala, usulan, keputusan final, status, action item, PIC (@username), deadline, serta semua URL. "
                "Pertahankan detail yang hanya muncul satu kali, bedakan usulan dari keputusan, dan jangan mengarang informasi."
            )
        else:
            prompt += (
                "Buat ringkasan lengkap sesuai format standar. Pastikan setiap topik, angka, tanggal, nama, keputusan, kendala, "
                "status, URL, dan penugasan penting dari transkrip terwakili. Gabungkan duplikasi, tetapi jangan membuang detail "
                "yang membedakan satu isu dari isu lain."
            )

        # Coba provider utama, jika gagal coba provider cadangan
        primary = self.provider
        fallback = "hermes" if primary == "gemini" else "gemini"

        try:
            if primary == "gemini":
                res = await self._call_gemini(prompt)
                self.last_used_provider = "gemini"
                return res
            elif primary == "openai":
                res = await self._call_openai(prompt)
                self.last_used_provider = "openai"
                return res
            elif primary == "anthropic":
                res = await self._call_anthropic(prompt)
                self.last_used_provider = "anthropic"
                return res
            else:
                res = await self._call_hermes(prompt)
                self.last_used_provider = "hermes"
                return res
        except Exception as primary_err:
            logger.warning("Provider utama %s gagal: %s. Mencoba provider cadangan %s...", primary, primary_err, fallback)
            try:
                if fallback == "gemini" and config.GEMINI_API_KEY:
                    res = await self._call_gemini(prompt)
                    self.last_used_provider = "gemini"
                    return res
                elif fallback == "openai" and config.OPENAI_API_KEY:
                    res = await self._call_openai(prompt)
                    self.last_used_provider = "openai"
                    return res
                elif fallback == "hermes" and config.HERMES_API_KEY:
                    res = await self._call_hermes(prompt)
                    self.last_used_provider = "hermes"
                    return res
            except Exception as fallback_err:
                logger.error("Provider cadangan %s juga gagal: %s", fallback, fallback_err)
            
            # Jika primary anthropic/openai/hermes gagal, selalu usahakan fallback ke Gemini jika ada key nya
            if config.GEMINI_API_KEY:
                try:
                    res = await self._call_gemini(prompt)
                    self.last_used_provider = "gemini"
                    return res
                except Exception as gem_err:
                    logger.error("Fallback darurat ke Gemini gagal: %s", gem_err)

            raise primary_err

    async def _call_gemini_chat(self, prompt: str, system_instruction: str) -> str:
        """Panggil Gemini untuk Chat Interaktif dengan fallback model."""
        if not self.gemini_client:
            self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
        models_to_try = [m for m in [config.GEMINI_MODEL, "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest"] if m and m.startswith("gemini")]
        if self.model and self.model.startswith("gemini") and self.model not in models_to_try:
            models_to_try.insert(0, self.model)
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
        first_exception = None
        last_exception = None
        for target_model in models_to_try:
            for attempt in range(3):
                try:
                    response = await self.gemini_client.aio.models.generate_content(
                        model=target_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            max_output_tokens=4096,
                            temperature=0.7,
                        )
                    )
                    if response and response.text:
                        return response.text
                except Exception as e:
                    if first_exception is None:
                        first_exception = e
                    last_exception = e
                    err_str = str(e).lower()
                    if "503" in err_str or "unavailable" in err_str or "429" in err_str or "resource_exhausted" in err_str:
                        wait_seconds = 3 * (attempt + 1)
                        logger.warning(
                            "Gemini chat model %s temporarily unavailable (attempt %d/3), retrying in %ds...",
                            target_model, attempt + 1, wait_seconds
                        )
                        await asyncio.sleep(wait_seconds)
                    else:
                        logger.warning("Gemini chat model %s failed: %s", target_model, e)
                        break
        if first_exception and ("404" not in str(first_exception).lower() and "not_found" not in str(first_exception).lower()):
            raise first_exception
        if last_exception:
            raise last_exception
        return ""

    async def chat_reply(self, user_message: str, history_context: str = "") -> str:
        """Memproses pesan percakapan langsung pengguna (Chat Interaktif)."""
        chat_system_prompt = (
            "Anda adalah asisten AI Telegram bernama Chat Assistant yang ramah, sopan, cerdas, dan sigap. "
            "Tugas Anda adalah membalas obrolan atau menjawab pertanyaan pengguna dengan Bahasa Indonesia yang jelas, "
            "akurat, dan bermanfaat. Jawab langsung inti pesan pengguna. "
            "Jangan memperkenalkan diri atau mengirim pesan pembuka kecuali pengguna secara eksplisit meminta perkenalan. "
            "Gunakan format Markdown yang rapi jika diperlukan."
        )
        
        prompt = user_message
        if history_context:
            prompt = f"Konteks obrolan sebelumnya:\n{history_context}\n\nPesan pengguna saat ini: {user_message}"

        primary = self.provider
        fallback = "hermes" if primary == "gemini" else "gemini"

        try:
            if primary == "gemini":
                return await self._call_gemini_chat(prompt, chat_system_prompt)
            elif primary == "openai":
                return await self._call_openai(prompt, system_instruction=chat_system_prompt)
            elif primary == "anthropic":
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
        except Exception as primary_err:
            logger.warning("Chat reply provider utama (%s) gagal: %s. Mencoba fallback (%s)...", primary, primary_err, fallback)
            try:
                if fallback == "gemini" and config.GEMINI_API_KEY:
                    return await self._call_gemini_chat(prompt, chat_system_prompt)
                elif fallback == "openai" and config.OPENAI_API_KEY:
                    return await self._call_openai(prompt, system_instruction=chat_system_prompt)
                elif fallback == "hermes" and config.HERMES_API_KEY:
                    return await self._call_hermes(prompt, system_instruction=chat_system_prompt)
            except Exception as fallback_err:
                logger.error("Provider cadangan %s juga gagal: %s", fallback, fallback_err)
            
            return f"❌ *Maaf, terjadi kesalahan saat memproses jawaban:* {str(primary_err)}"

    async def translate_text(self, text: str, target_language: str) -> str:
        """Menerjemahkan pesan yang direply tanpa menambahkan perkenalan atau komentar."""
        prompt = (
            f"Terjemahkan teks berikut ke {target_language}. "
            "Pertahankan makna, angka, nama, tautan, struktur heading, dan format Markdown. "
            "Keluarkan hanya hasil terjemahan tanpa pengantar, penjelasan, atau perkenalan.\n\n"
            f"TEKS:\n{text}"
        )
        system_instruction = (
            f"Anda adalah penerjemah profesional. Terjemahkan teks ke {target_language}. "
            "Jangan menjawab isi teks, jangan meringkas, dan jangan memperkenalkan diri. "
            "Keluarkan hanya terjemahannya."
        )

        try:
            if self.provider == "gemini":
                return await self._call_gemini_chat(prompt, system_instruction)
            if self.provider == "openai":
                return await self._call_openai(prompt, system_instruction=system_instruction)
            if self.provider == "anthropic":
                if not self.anthropic_client:
                    self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
                response = await self.anthropic_client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_instruction,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
            return await self._call_hermes(prompt, system_instruction=system_instruction)
        except Exception as primary_err:
            logger.warning("Translation provider utama (%s) gagal: %s", self.provider, primary_err)

            # Gemini bisa sementara penuh; gunakan provider lain jika tersedia.
            if self.provider != "hermes" and config.HERMES_API_KEY:
                try:
                    return await self._call_hermes(prompt, system_instruction=system_instruction)
                except Exception as fallback_err:
                    logger.warning("Fallback terjemahan ke Hermes gagal: %s", fallback_err)

            if self.provider != "gemini" and config.GEMINI_API_KEY:
                try:
                    return await self._call_gemini_chat(prompt, system_instruction)
                except Exception as fallback_err:
                    logger.warning("Fallback terjemahan ke Gemini gagal: %s", fallback_err)

            return "❌ *Maaf, layanan AI sedang sibuk.* Silakan coba terjemahkan lagi beberapa detik kemudian."

    async def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        timeframe_info: str = ""
    ) -> str:
        """Meringkas pesan dengan strategi cepat untuk jumlah pesan normal dan chunking terbatas untuk data besar."""
        if not messages:
            return "⚠️ Tidak ada pesan baru untuk diringkas."

        total_msgs = len(messages)
        chunk_plan = get_summary_chunk_plan(total_msgs)
        chunks = chunk_messages(messages, max(1, total_msgs // chunk_plan if chunk_plan > 1 else FAST_SUMMARY_MAX_MESSAGES))

        logger.info("Processing summary for %d messages across %d chunk(s) using %s (%s)",
                    total_msgs, len(chunks), self.provider, self.model)

        try:
            if len(chunks) == 1:
                transcript = format_messages_transcript(chunks[0])
                summary_content = await self.summarize_chunk(transcript, is_intermediate=False)
            else:
                logger.info("Summarizing %d chunks with fast aggregation...", len(chunks))
                tasks = [self.summarize_chunk(format_messages_transcript(chunk), is_intermediate=True) for chunk in chunks]
                intermediate_summaries = list(await asyncio.gather(*tasks))
                combined_intermediates = "\n\n".join(intermediate_summaries)
                consolidation_prompt = (
                    f"Berikut adalah ringkasan parsial dari {total_msgs} pesan obrolan grup:\n\n"
                    f"{combined_intermediates}\n\n"
                    f"Gabungkan semua detail penting menjadi satu Executive Summary yang padat dan akurat. "
                    f"Pertahankan nama/@username, angka, tanggal/jam, status, keputusan, action item, dan link penting. "
                    f"Bedakan keputusan final dari usulan. Jangan mengarang fakta baru. "
                    f"Langsung mulai dengan format berikut:\n\n"
                    f"📌 *TOPIK UTAMA*\n"
                    f"• [Fakta utama]\n\n"
                    f"✅ *KEPUTUSAN & KESEPAKATAN*\n"
                    f"• [Keputusan final atau 'Tidak ada keputusan khusus']\n\n"
                    f"📋 *ACTION ITEMS & TINDAK LANJUT*\n"
                    f"• [Tugas & PIC atau 'Tidak ada action item']\n\n"
                    f"🔗 *LINK & REFERENSI PENTING*\n"
                    f"• [Keterangan]: URL"
                )
                summary_content = await self.summarize_chunk(consolidation_prompt, is_intermediate=False)

            used_prov = getattr(self, "last_used_provider", self.provider)
            if used_prov == "gemini":
                ai_label = "Google Gemini AI (Gratis)"
            elif used_prov == "openai":
                ai_label = f"OpenAI GPT ({config.OPENAI_MODEL})"
            elif used_prov == "anthropic":
                ai_label = f"Claude ({config.ANTHROPIC_MODEL})"
            else:
                ai_label = f"Nous-Hermes ({config.HERMES_MODEL})"

            if used_prov != self.provider:
                ai_label += f" (Fallback dari {self.provider.upper()})"

            summary_content = clean_summary_output(summary_content)

            header = f"📊 *RINGKASAN CHAT GRUP*\n"
            if timeframe_info:
                header += f"🕒 Periode: _{timeframe_info}_\n"
            header += f"💬 Total Pesan: *{total_msgs} pesan*\n\n"

            footer = f"\n\n_— Diringkas otomatis dengan {ai_label}_"
            return f"{header}{summary_content}{footer}"

        except Exception as e:
            logger.exception("Error during summarization: %s", e)
            err_str = str(e)
            lower_err = err_str.lower()
            if "503" in lower_err or "unavailable" in lower_err or "high demand" in lower_err:
                return (
                    "⏳ *Server Google Gemini sedang padat / High Demand (503).*\n\n"
                    "Server Google AI sedang mengalami lonjakan beban tinggi sementara.\n\n"
                    "💡 *Solusi:* Silakan coba kirim permintaan lagi dalam beberapa detik, atau gunakan perintah `/model` untuk mengganti AI."
                )
            if "insufficient_quota" in lower_err or "credit_balance_exhausted" in lower_err:
                return (
                    "⚠️ *OpenAI API Key Belum Memiliki Saldo/Credit ($0 Credit)*\n\n"
                    "API Key dari OpenAI membutuhkan saldo terisi di [platform.openai.com/billing](https://platform.openai.com/settings/organization/billing).\n\n"
                    "💡 *Solusi Gratis:* Gunakan perintah `/model gemini` di Telegram untuk memakai **Google Gemini AI 100% Gratis**!"
                )
            if "api_key" in lower_err or "api key" in lower_err or "invalid" in lower_err:
                return f"❌ *Error API Key:* API Key {self.provider.upper()} tidak valid atau belum diisi. Periksa file `.env`."
            if "resource_exhausted" in lower_err or "rate_limit" in lower_err or "429" in err_str or "quota" in lower_err:
                return (
                    "⏳ *AI sedang rate-limited / kuota habis.*\n\n"
                    "Solusi: gunakan API key yang valid untuk provider lain, atau tunggu beberapa menit lalu coba lagi."
                )
            if "not_found" in lower_err or "404" in err_str:
                return (
                    "❌ *Model AI yang dipilih tidak tersedia lagi (404).* \n\n"
                    "Model yang diatur di `.env` mungkin sudah usang/dihentikan oleh Google/OpenAI.\n\n"
                    "💡 *Solusi:* Gunakan `GEMINI_MODEL=gemini-3.6-flash` atau `gemini-3.5-flash` di file `.env`."
                )
            return f"❌ *Terjadi kesalahan saat memproses ringkasan:* {err_str}"
