"""
Smart AI Handler Module
Manages AI provider fallback cascade:
  Plan A:  Ollama local (mistral-small:22b via Metal) — sem quota, sem cooldown
  Plan B:  Groq Llama 3.3 (velocidade pura)
  Plan C:  Gemini Flash (rápido / contexto longo)
  Fallback: Heurística NER + Regex (zero custo, sem API)
"""
import os
import time
import warnings
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

warnings.filterwarnings('ignore', category=FutureWarning)

load_dotenv()

from .ai_providers import OllamaProvider, GeminiProvider, GroqProvider, HeuristicNERRegex


class SmartAI:
    """
    Smart AI handler with automatic fallback cascade:
    1. Ollama local (Plan A) — sem quota, sem cooldown
    2. Groq Llama 3.3 (Plan B) — confiável, rápido
    3. Gemini Flash (Plan C) — fallback externo
    4. Heuristic NER + Regex (Hard Fallback)
    """

    def __init__(self):
        self.gemini_model = None
        self.groq_client = None
        self.groq_model = None
        self._providers = []
        self._heuristic = HeuristicNERRegex()
        self._ollama_provider = None
        self._init_ollama()
        self._init_gemini()
        self._init_groq()
        self._build_cascade()

    def _init_ollama(self):
        """Initialize Ollama local provider (Plan A)."""
        self._ollama_provider = OllamaProvider()

    def _init_gemini(self):
        """Initialize Gemini AI client."""
        try:
            import google.generativeai as genai
            api_key = os.getenv('GEMINI_API_KEY') or "AIzaSyALpGJX6HWYrEhP0zwp2at0wEajbQR-gJA"
            genai.configure(api_key=api_key)
            try:
                self.gemini_model = genai.GenerativeModel('models/gemini-flash-latest')
                print("  ✓ Gemini AI initialized: models/gemini-flash-latest")
            except Exception as e:
                print(f"  ⚠ Gemini flash-latest failed: {e}")
                try:
                    self.gemini_model = genai.GenerativeModel('models/gemini-2.5-flash')
                    print("  ✓ Gemini AI initialized: models/gemini-2.5-flash (fallback)")
                except Exception as e2:
                    print(f"  ✗ Gemini initialization failed: {e2}")
                    self.gemini_model = None
        except ImportError:
            print("  ⚠ google-generativeai not installed. Gemini unavailable.")
            self.gemini_model = None
        except Exception as e:
            print(f"  ⚠ Gemini initialization error: {e}")
            self.gemini_model = None

    def _init_groq(self):
        """Initialize Groq AI client."""
        try:
            from groq import Groq
            api_key = os.getenv('GROQ_API_KEY')
            if not api_key:
                print("  ⚠ GROQ_API_KEY not found in environment. Groq unavailable.")
                self.groq_client = None
                return
            self.groq_client = Groq(api_key=api_key)
            self.groq_model = "llama-3.3-70b-versatile"
            print(f"  ✓ Groq AI initialized: {self.groq_model}")
        except ImportError:
            print("  ⚠ groq library not installed. Install with: pip install groq")
            self.groq_client = None
        except Exception as e:
            print(f"  ⚠ Groq initialization error: {e}")
            self.groq_client = None

    def _build_cascade(self):
        """Build ordered provider list: Ollama (A) → Groq (B) → Gemini (C) → Heuristic."""
        self._providers = []
        if self._ollama_provider and self._ollama_provider.available:
            self._providers.append(("Ollama", self._ollama_provider))
        groq_p = GroqProvider()
        if groq_p.client:
            self._providers.append(("Groq", groq_p))
        gemini_p = GeminiProvider()
        if gemini_p.model:
            self._providers.append(("Gemini", gemini_p))
        self._providers.append(("Heuristic", self._heuristic))

    def get_ai_decision(self, prompt: str, system_prompt: str = "You are a senior tech recruiter.") -> str:
        """
        Cascade: Ollama (Plan A) → Groq (Plan B) → Gemini (Plan C) → Heurística.
        Delay de 4s apenas para chamadas externas (Groq/Gemini).
        """
        for name, provider in self._providers:
            if name in ("Gemini", "Groq"):
                time.sleep(4)
            try:
                out = provider.ask(prompt, system_prompt)
                if out and out.strip():
                    if name == "Heuristic":
                        print("  🤖 Hard Fallback (Heuristic NER + Regex).")
                    return out.strip()
            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ("429", "504", "503", "quota", "rate limit", "deadline", "service unavailable", "high demand")):
                    print(f"  ⚠ {name} quota/504/503. Tentando próximo provider...")
                else:
                    print(f"  ⚠ {name} failed: {e}. Trying next provider...")
                continue
        return ""

    def analyze_resume(self, pdf_path: str) -> Dict[str, Any]:
        """
        Analyze resume PDF: Ollama (A) → Gemini (B) → Groq (C) → Heuristic → Static.
        """
        # 1. Ollama (Plan A — local, sem quota)
        if self._ollama_provider and self._ollama_provider.available:
            try:
                result = self._analyze_resume_ollama(pdf_path)
                if result:
                    return result
            except Exception as e:
                print(f"  ⚠ Ollama resume analysis failed: {e}. Switching to Gemini...")

        # 2. Gemini (Plan B — vision)
        if self.gemini_model:
            try:
                return self._analyze_resume_gemini(pdf_path)
            except Exception as e:
                error_str = str(e).lower()
                if any(x in error_str for x in ('429', '503', 'quota', 'rate limit', 'service unavailable', 'high demand')):
                    print("  ⚠ Gemini Quota Exceeded. Switching to Groq AI...")
                else:
                    print(f"  ⚠ Gemini failed: {e}. Switching to Groq AI...")

        # 3. Groq (Plan C — text from PDF)
        if self.groq_client:
            try:
                return self._analyze_resume_groq(pdf_path)
            except Exception as e:
                print(f"  ⚠ Groq failed: {e}")

        # 4. Heuristic (regex on extracted text)
        try:
            text = self._extract_pdf_text(pdf_path)
            if text and len(text) >= 100:
                data = self._heuristic.extract_resume_json(text)
                print("  ✓ Resume data extracted via Heuristic NER+Regex (Hard Fallback)")
                return data
        except Exception as e:
            print(f"  ⚠ Heuristic extraction failed: {e}")

        # 5. Static fallback
        print("  ⚠ All AI providers failed. Using static profile.")
        return self._get_static_resume_data()

    def _extract_pdf_text(self, pdf_path: str) -> str:
        """Extract text from PDF for text-based providers (Groq/Ollama/Heuristic)."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return ""
        text_parts = []
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
        except Exception:
            try:
                import fitz
                doc = fitz.open(str(pdf_path))
                for page in doc:
                    t = page.get_text()
                    if t:
                        text_parts.append(t)
                doc.close()
            except Exception:
                pass
        return "\n".join(text_parts)

    def _analyze_resume_ollama(self, pdf_path: str) -> Optional[Dict[str, Any]]:
        """Analyze resume using Ollama with extracted PDF text."""
        text = self._extract_pdf_text(pdf_path)
        if not text or len(text) < 100:
            return None
        prompt = f"""Analyze this resume text and extract structured information. Return ONLY valid JSON with this exact structure:

{{
    "stack_tecnico": ["list", "of", "technical", "skills"],
    "experiencia_anos": <number>,
    "senioridade_pretendida": "junior|pleno|senior|especialista",
    "palavras_chave": ["keywords"],
    "educacao": [],
    "experiencia_profissional": []
}}

Resume text:
{text[:6000]}

Return ONLY the JSON, no markdown."""
        raw = self._ollama_provider.ask(prompt, "You are a resume analyzer. Return only valid JSON.", expect_json=True)
        if not raw:
            return None
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        return None

    def _analyze_resume_gemini(self, pdf_path: str) -> Dict[str, Any]:
        """Analyze resume using Gemini Vision API."""
        import google.generativeai as genai
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Resume not found: {pdf_path}")
        uploaded_file = genai.upload_file(path=str(pdf_path), mime_type="application/pdf")
        prompt = """Analyze this resume PDF and extract structured information. Return ONLY valid JSON with this exact structure:

{
    "stack_tecnico": ["list", "of", "technical", "skills", "and", "technologies"],
    "experiencia_anos": <number of years of experience as integer>,
    "senioridade_pretendida": "junior|pleno|senior|especialista",
    "palavras_chave": ["relevant", "keywords", "from", "resume"],
    "educacao": [{"instituicao": "...", "curso": "...", "ano": "..."}],
    "experiencia_profissional": [{"empresa": "...", "cargo": "...", "periodo": "...", "descricao": "..."}]
}

Return ONLY the JSON, no markdown, no explanations."""
        response = self.gemini_model.generate_content([uploaded_file, prompt])
        response_text = response.text.strip()
        if response_text.startswith('```'):
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
        result = json.loads(response_text.strip())
        print("  ✓ Resume data extracted successfully via Gemini")
        return result

    def _analyze_resume_groq(self, pdf_path: str) -> Dict[str, Any]:
        """Analyze resume using Groq (text from PDF)."""
        pdf_path = Path(pdf_path)
        resume_text = self._extract_pdf_text(str(pdf_path))
        if not resume_text or len(resume_text) < 100:
            raise ValueError("Could not extract sufficient text from PDF")
        prompt = f"""Analyze this resume text and extract structured information. Return ONLY valid JSON with this exact structure:

{{
    "stack_tecnico": ["list", "of", "technical", "skills", "and", "technologies"],
    "experiencia_anos": <number of years of experience as integer>,
    "senioridade_pretendida": "junior|pleno|senior|especialista",
    "palavras_chave": ["relevant", "keywords", "from", "resume"],
    "educacao": [{{"instituicao": "...", "curso": "...", "ano": "..."}}],
    "experiencia_profissional": [{{"empresa": "...", "cargo": "...", "periodo": "...", "descricao": "..."}}]
}}

Resume text:
{resume_text[:8000]}

Return ONLY the JSON, no markdown, no explanations."""
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {"role": "system", "content": "You are a resume analyzer. Always return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        response_text = response.choices[0].message.content.strip()
        try:
            result = json.loads(response_text)
            print("  ✓ Resume data extracted successfully via Groq")
            return result
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                print("  ✓ Resume data extracted successfully via Groq (extracted from text)")
                return result
            raise ValueError("Failed to parse Groq response as JSON")

    def _get_static_resume_data(self) -> Dict[str, Any]:
        """Return static resume data as ultimate fallback."""
        return {
            "stack_tecnico": ["Python", "Ruby on Rails", "React", "Node.js", "PostgreSQL"],
            "experiencia_anos": 3,
            "senioridade_pretendida": "pleno",
            "palavras_chave": ["Python", "Ruby on Rails", "React", "Node.js", "PostgreSQL", "Backend", "Full Stack", "API", "REST", "Automation"],
            "educacao": [],
            "experiencia_profissional": []
        }

    def generate_content(self, prompt: str) -> str:
        """Generate content using full cascade: Ollama → Groq → Gemini → Heuristic."""
        system_prompt = "You are a senior tech recruiter and professional writer. Be concise and professional."
        return self.get_ai_decision(prompt, system_prompt) or ""


if __name__ == "__main__":
    print("Testing SmartAI Handler...")
    ai = SmartAI()
    static_data = ai._get_static_resume_data()
    print(f"\nStatic fallback data: {json.dumps(static_data, indent=2)}")
