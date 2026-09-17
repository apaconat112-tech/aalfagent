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
    return [messages[i:i + chunk_size] for i in range(0, len(messages), chunk_size)]

class ChatSummarizer:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = (provider or config.AI_PROVIDER).strip().lower()
        self.gemini_client: Optional[genai.Client] = None
        self.anthropic_client: Optional[anthropic.AsyncAnthropic] = None

        if self.provider == "gemini":
            if config.GEMINI_API_KEY:
                self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
            self.model = model or config.GEMINI_MODEL
        elif self.provider == "anthropic":
            if config.ANTHROPIC_API_KEY:
                self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
            self.model = model or config.ANTHROPIC_MODEL
        else:
            self.provider = "hermes"
            self.model = model or config.HERMES_MODEL

    async def _call_gemini(self, prompt: str) -> str:
        """Panggil Google Gemini API (Gratis) dengan retry otomatis & fallback jika server busy 503."""
        if not self.gemini_client:
            self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

        models_to_try = [m for m in [config.GEMINI_MODEL, "gemini-3.6-flash"] if m.startswith("gemini")]
        if self.model and self.model.startswith("gemini") and self.model not in models_to_try:
            models_to_try.insert(0, self.model)
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
        last_exception = None

        for target_model in models_to_try:
            for attempt in range(3):
                try:
                    response = await self.gemini_client.aio.models.generate_content(
                        model=target_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            max_output_tokens=4096,
                            temperature=0.3,
                        )
                    )
                    if response and response.text:
                        return response.text
                except Exception as e:
                    last_exception = e
                    err_str = str(e).lower()
                    if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                        logger.warning("Gemini model %s rate limited (429, attempt %d/3). Retrying in 5s...", target_model, attempt + 1)
                        await asyncio.sleep(5)
                    elif "404" in err_str or "not_found" in err_str:
                        logger.warning("Gemini model %s not found (404), trying next model...", target_model)
                        break
                    elif "503" in err_str or "unavailable" in err_str:
                        logger.warning("Gemini API (%s) busy (attempt %d/3): %s. Retrying...", target_model, attempt+1, e)
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
        """Panggil Hermes AI API via OpenRouter / Ollama (OpenAI-compatible endpoint)."""
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
            "openrouter/auto",
            "google/gemma-4-31b-it:free",
            "z-ai/glm-5.2:free",
            "google/gemma-4-26b-a4b-it:free",
            "liquid/lfm-2.5-2.6b:free"
        ]:
            if m not in models_to_try:
                models_to_try.append(m)

        last_err = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for model_name in models_to_try:
                for attempt in range(4):
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4096
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
                            wait_s = 4 * (attempt + 1)
                            logger.warning("OpenRouter model %s rate limited (%d, attempt %d/4). Retrying in %ds...", model_name, resp.status_code, attempt + 1, wait_s)
                            await asyncio.sleep(wait_s)
                        elif resp.status_code in [400, 402, 404]:
                            logger.warning("OpenRouter model %s error status %d, skipping to next model...", model_name, resp.status_code)
                            last_err = f"OpenRouter Error ({resp.status_code}): {resp.text}"
                            break
                        else:
                            logger.warning("OpenRouter model %s returned status %d: %s", model_name, resp.status_code, resp.text)
                            last_err = f"OpenRouter Error ({resp.status_code}): {resp.text}"
                            break
                    except Exception as req_err:
                        logger.warning("OpenRouter request error on %s: %s", model_name, req_err)
                        last_err = str(req_err)
                        await asyncio.sleep(2)

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
            
            # Jika primary anthropic gagal, selalu usahakan fallback ke Gemini jika ada key nya
            if config.GEMINI_API_KEY:
                try:
                    return await self._call_gemini(prompt)
                except Exception as gem_err:
                    logger.error("Fallback darurat ke Gemini gagal: %s", gem_err)

            raise primary_err

    async def _call_gemini_chat(self, prompt: str, system_instruction: str) -> str:
        """Panggil Gemini untuk Chat Interaktif dengan fallback model."""
        if not self.gemini_client:
            self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
        models_to_try = [m for m in [config.GEMINI_MODEL, "gemini-3.6-flash"] if m.startswith("gemini")]
        if self.model and self.model.startswith("gemini") and self.model not in models_to_try:
            models_to_try.insert(0, self.model)
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
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
                logger.info("Summarizing %d chunks in parallel...", len(chunks))
                tasks = [self.summarize_chunk(format_messages_transcript(chunk), is_intermediate=True) for chunk in chunks]
                intermediate_summaries = list(await asyncio.gather(*tasks))

                combined_intermediates = "\n\n".join(intermediate_summaries)
                consolidation_prompt = (
                    f"Berikut adalah poin-poin informasi dari total {total_msgs} pesan obrolan grup:\n\n"
                    f"{combined_intermediates}\n\n"
                    f"Tolong gabungkan SEMUA informasi di atas menjadi SATU Executive Summary yang CERDAS, KAYA INFORMASI, SPESIFIK, dan TO-THE-POINT. "
                    f"Jangan hanya mengambil poin yang paling sering muncul. Pertahankan juga fakta yang hanya muncul satu kali, termasuk nama/@username, "
                    f"angka, tanggal/jam, harga, kode/ID, nama alat/dokumen, status, kendala, solusi, deadline, dan URL. "
                    f"Hilangkan hanya duplikasi yang benar-benar sama, bedakan keputusan final dari usulan/pertanyaan, dan jangan mengarang fakta baru. "
                    f"Cocokkan hasil dengan seluruh poin sumber sebelum menjawab agar tidak ada topik atau action item yang hilang. "
                    f"DILARANG KERAS menuliskan kata pengantar / basa-basi. "
                    f"LANGSUNG MULAI DENGAN FORMAT BERIKUT:\n\n"
                    f"📌 *TOPIK UTAMA*\n"
                    f"- [Poin utama kaya detail & fakta teknis]\n\n"
                    f"✅ *KEPUTUSAN & KESEPAKATAN*\n"
                    f"- [Keputusan final/operasional spesifik atau 'Tidak ada keputusan khusus']\n\n"
                    f"📋 *ACTION ITEMS & TINDAK LANJUT*\n"
                    f"- [Poin tugas & @username PIC atau 'Tidak ada action item']\n\n"
                    f"🔗 *LINK & REFERENSI PENTING*\n"
                    f"- [Keterangan]: URL (atau 'Tidak ada tautan dibagikan')"
                )

                summary_content = await self.summarize_chunk(consolidation_prompt, is_intermediate=False)

            if self.provider == "gemini":
                ai_label = "Google Gemini AI (Gratis)"
            elif self.provider == "anthropic":
                ai_label = f"Claude ({self.model})"
            else:
                ai_label = f"Nous-Hermes ({self.model})"

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
            if "API_KEY" in err_str.upper() or "API KEY" in err_str.upper() or "INVALID" in err_str.upper():
                return f"❌ *Error API Key:* API Key {self.provider.upper()} tidak valid atau belum diisi. Periksa file `.env`."
            elif "RESOURCE_EXHAUSTED" in err_str or "RATE_LIMIT" in err_str.upper():
                return f"⏳ *Error Rate Limit:* Terkena kuota limit {self.provider.upper()}. Silakan coba lagi sebentar lagi."
            return f"❌ *Terjadi kesalahan saat memproses ringkasan:* {err_str}"
