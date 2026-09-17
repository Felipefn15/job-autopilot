"""
AI Providers Module
Unified interface for multiple AI backends with same ask/generate signature.
Hierarchy: Gemini (Primary) → Groq (Secondary) → HuggingFace (Failsafe 1) → Ollama (Failsafe 2) → Heuristic NER+Regex (Hard Fallback).
"""
import os
import re
import json
import hashlib
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Retry config for Gemini (504 / 429 / 503)
GEMINI_MAX_RETRIES = 1  # fail fast: Groq já é Plan B, Gemini só tenta 1x para não bloquear
GEMINI_BACKOFF_SECONDS = [2, 4, 8]  # exponential backoff (só usado se MAX_RETRIES > 1)
GEMINI_REQUEST_TIMEOUT_SECONDS = 60


# --- Base / interface ---

class BaseAIProvider:
    """Base interface: ask(prompt, system_prompt) -> str or None."""

    def ask(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.") -> Optional[str]:
        raise NotImplementedError


# --- 1. Primary: Gemini Flash (rápido / contexto longo) ---

class GeminiProvider(BaseAIProvider):
    def __init__(self, model_name: str = "models/gemini-flash-latest"):
        self.model = None
        self._model_name = model_name
        self._init()

    def _init(self):
        try:
            import google.generativeai as genai
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return
            genai.configure(api_key=api_key)
            try:
                self.model = genai.GenerativeModel(self._model_name)
                print("  ✓ [AI] Gemini Flash (Primary) ready")
            except Exception:
                self._model_name = "models/gemini-2.5-flash"
                self.model = genai.GenerativeModel(self._model_name)
                print("  ✓ [AI] Gemini 2.5 Flash (Primary fallback) ready")
        except Exception as e:
            print(f"  ⚠ [AI] Gemini init failed: {e}")
            self.model = None

    def _is_retryable_error(self, e: Exception) -> bool:
        err = str(e).lower()
        return (
            "504" in err or "429" in err or "503" in err
            or "deadline exceeded" in err or "quota" in err or "rate limit" in err
            or "service unavailable" in err or "high demand" in err
        )

    def ask(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.") -> Optional[str]:
        if not self.model:
            return None
        full_prompt = f"{system_prompt}\n\n{prompt}"
        last_error = None
        for attempt in range(GEMINI_MAX_RETRIES):
            try:
                # Prefer 60s timeout if SDK supports it (reduces 504 from slow Free Tier queue)
                try:
                    from google.generativeai.types import RequestOptions
                    opts = RequestOptions(timeout=GEMINI_REQUEST_TIMEOUT_SECONDS)
                    response = self.model.generate_content(full_prompt, request_options=opts)
                except (ImportError, TypeError, AttributeError):
                    response = self.model.generate_content(full_prompt)
                return (response.text or "").strip() or None
            except Exception as e:
                last_error = e
                if not self._is_retryable_error(e) or attempt == GEMINI_MAX_RETRIES - 1:
                    raise RuntimeError(str(e))
                wait = GEMINI_BACKOFF_SECONDS[min(attempt, len(GEMINI_BACKOFF_SECONDS) - 1)]
                print(f"  ⚠ [AI] Gemini 504/429/503 (attempt {attempt + 1}/{GEMINI_MAX_RETRIES}). Backoff {wait}s...")
                time.sleep(wait)
        raise RuntimeError(str(last_error))


# --- 2. Secondary: Groq Llama 3.3 (velocidade pura) ---

class GroqProvider(BaseAIProvider):
    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        self.client = None
        self._model_name = model_name
        self._init()

    def _init(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                return
            self.client = Groq(api_key=api_key)
            print("  ✓ [AI] Groq Llama 3.3 (Secondary) ready")
        except Exception as e:
            print(f"  ⚠ [AI] Groq init failed: {e}")
            self.client = None

    def ask(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.") -> Optional[str]:
        if not self.client:
            return None
        try:
            response = self.client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            text = (response.choices[0].message.content or "").strip()
            return text or None
        except Exception as e:
            raise RuntimeError(str(e))


# --- 3. Failsafe 1: Hugging Face (independente) ---

class HuggingFaceProvider(BaseAIProvider):
    def __init__(self, model_id: str = "google/flan-t5-base"):
        self.model_id = model_id
        self.api_url = f"https://api-inference.huggingface.co/models/{model_id}"
        self.token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

    def ask(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.") -> Optional[str]:
        if not self.token:
            return None
        try:
            import requests
            full_prompt = f"{system_prompt}\n\n{prompt}"
            payload = {
                "inputs": full_prompt[:1024],
                "parameters": {"max_new_tokens": 256, "temperature": 0.3},
            }
            r = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload,
                timeout=30,
            )
            if r.status_code != 200:
                return None
            out = r.json()
            if isinstance(out, list) and len(out) > 0:
                return (out[0].get("generated_text") or "").strip() or None
            if isinstance(out, dict) and "generated_text" in out:
                return (out["generated_text"] or "").strip() or None
            return None
        except Exception as e:
            print(f"  ⚠ [AI] Hugging Face error: {e}")
            return None


# --- 4. Plan A: Ollama local (mistral-small:22b via Metal/GPU) ---

# Cache de processo: resultado da verificação de saúde do Ollama compartilhado entre
# todas as threads. Evita N smoke-tests simultâneos que sobrecarregam o servidor local.
_ollama_health_cache: dict = {}  # {host: (model, available)}
_ollama_health_lock = __import__('threading').Lock()

# Semáforo de concorrência: Ollama é single-threaded para inferência.
# Mais de 1 chamada simultânea resulta em timeout. Serializa as requisições.
_ollama_semaphore = __import__('threading').Semaphore(1)


class OllamaProvider(BaseAIProvider):
    # Modelos em ordem de preferência — tenta o maior disponível
    _MODEL_FALLBACKS = ["mistral-small:22b", "mistral:7b", "llama3.2:1b"]

    def __init__(self, model: str = None):
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.base_url = host
        self.chat_url = f"{host}/v1/chat/completions"
        preferred = model or os.getenv("OLLAMA_MODEL", "mistral-small:22b")
        self.model = preferred
        self.available = False

        # Usa cache para evitar múltiplos smoke-tests em paralelo
        with _ollama_health_lock:
            if host in _ollama_health_cache:
                cached_model, cached_avail = _ollama_health_cache[host]
                self.model = cached_model
                self.available = cached_avail
                if cached_avail:
                    print(f"  ✓ [AI] Ollama {self.model} (Plan A / local) ready")
                return

            # Primeira thread chega aqui e faz a checagem real
            result_model, result_avail = self._probe(host, preferred)
            # Só cacheia resultados positivos: se Ollama estiver fora, a próxima
            # chamada (ex: loop de cooldown no worker) vai retentar em vez de usar
            # o resultado negativo cacheado.
            if result_avail:
                _ollama_health_cache[host] = (result_model, result_avail)
            self.model = result_model
            self.available = result_avail

    def _probe(self, host: str, preferred: str):
        """Verifica disponibilidade via /api/tags (sem smoke test de geração)."""
        try:
            import requests
            r = requests.get(f"{host}/api/tags", timeout=5)
            if r.status_code != 200:
                print(f"  ⚠ [AI] Ollama not reachable at {host}")
                return preferred, False
            pulled = [m["name"] for m in r.json().get("models", [])]
            # Tenta o modelo preferido, depois os fallbacks
            for candidate in [preferred] + self._MODEL_FALLBACKS:
                base = candidate.split(":")[0]
                if any(base in m for m in pulled):
                    print(f"  ✓ [AI] Ollama {candidate} (Plan A / local) ready")
                    return candidate, True
            # Nenhum modelo disponível
            missing = [m for m in [preferred] + self._MODEL_FALLBACKS
                       if not any(m.split(":")[0] in p for p in pulled)]
            if missing:
                print(f"  ⚠ [AI] Ollama: nenhum modelo disponível. Pull: ollama pull {missing[0]}")
            return preferred, False
        except Exception:
            print(f"  ⚠ [AI] Ollama not reachable at {host}")
            return preferred, False

    def ask(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.", expect_json: bool = False) -> Optional[str]:
        if not self.available:
            return None
        # Serializa chamadas: Ollama é single-threaded, chamadas simultâneas causam timeout
        with _ollama_semaphore:
            try:
                import requests
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "temperature": 0.3,
                }
                if expect_json:
                    payload["format"] = "json"
                response = requests.post(self.chat_url, json=payload, timeout=120)
                if response.status_code == 200:
                    content = (
                        response.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content") or ""
                    ).strip()
                    return content or None
                err = response.json().get("error", {})
                msg = err.get("message", "") if isinstance(err, dict) else str(err)
                print(f"  ⚠ [AI] Ollama request failed: {msg[:100]}")
                return None
            except Exception as e:
                print(f"  ⚠ [AI] Ollama error: {e}")
                return None


# --- 5. Hard Fallback: Heurística NER + Regex (zero custo) ---

def _extract_skills_regex(text: str) -> list:
    """Extrai termos que parecem tecnologias (palavras em maiúscula, termos conhecidos)."""
    if not text or not text.strip():
        return []
    tech_patterns = [
        r"\b(Python|JavaScript|TypeScript|React|Node\.?js|Vue|Angular|Ruby|Rails|Java|Kotlin|Swift|Go|Rust|C\+\+|PHP|PostgreSQL|MongoDB|Redis|AWS|Docker|Kubernetes|Git|REST|GraphQL|gRPC)\b",
        r"\b([A-Z][a-z]+(?:\.[a-z]+)?)\b",  # CamelCase or Word.word
    ]
    seen = set()
    for pat in tech_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            s = m.group(1).strip()
            if len(s) >= 2 and s.lower() not in ("the", "and", "for", "you", "your", "this", "that"):
                seen.add(s)
    return list(seen)[:15]


def _extract_years_regex(text: str) -> int:
    """Tenta extrair anos de experiência do texto."""
    m = re.search(r"(\d+)\+?\s*(?:years?|anos?|yoe|experiência|experience)", text, re.IGNORECASE)
    if m:
        return min(99, max(0, int(m.group(1))))
    m = re.search(r"(?:experience|experiência|years?|anos?)\s*(?:of|:)?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return min(99, max(0, int(m.group(1))))
    return 3


class HeuristicNERRegex(BaseAIProvider):
    """Fallback sem API: regex + templates. Para generate_content retorna texto curto; para JSON retorna estrutura fixa."""

    def ask(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.") -> Optional[str]:
        # Para prompts que pedem carta/cover letter: retorna um template genérico
        prompt_lower = (prompt or "").lower()
        if "carta" in prompt_lower or "cover letter" in prompt_lower or "letter" in prompt_lower:
            return (
                "I am a Senior Full Stack Engineer with several years of experience, "
                "focused on the technologies mentioned in your post. I would be glad to discuss how I can contribute. "
                "Please find my resume attached."
            )
        # Para outros prompts: resposta mínima
        return "I am a Senior Full Stack Engineer interested in this position. Please see my attached resume."

    def extract_resume_json(self, text: str) -> Dict[str, Any]:
        """Extrai estrutura tipo resume a partir de texto (PDF extraído) usando regex."""
        skills = _extract_skills_regex(text)
        years = _extract_years_regex(text)
        seniority = "senior" if years >= 5 else "pleno" if years >= 2 else "junior"
        return {
            "stack_tecnico": skills or ["Python", "React", "Node.js", "PostgreSQL"],
            "experiencia_anos": years or 3,
            "senioridade_pretendida": seniority,
            "palavras_chave": skills[:10] or ["Python", "Backend", "Full Stack"],
            "educacao": [],
            "experiencia_profissional": [],
        }


# --- Fingerprint (email + job_id) para unicidade no banco ---

def make_fingerprint(email: str, job_id: str) -> str:
    """Hash estável para chave de unicidade: evita duplicados por (email, job_id)."""
    raw = f"{ (email or '').strip().lower() }|{ (job_id or '').strip() }"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
