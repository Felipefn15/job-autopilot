"""
AI Brain Module
Uses SmartAI handler with Gemini (primary) and Groq (fallback) for intelligent decision-making
"""
import os
import warnings
import re
import time
import random
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from dotenv import load_dotenv

# Suppress FutureWarning for google.generativeai
warnings.filterwarnings('ignore', category=FutureWarning)

import google.generativeai as genai

# Configure Gemini - SIMPLIFICADO
genai.configure(api_key="AIzaSyALpGJX6HWYrEhP0zwp2at0wEajbQR-gJA")

# Usar modelo estável: gemini-flash-latest (mais estável e disponível)
# Fallback para gemini-2.5-flash se falhar
try:
    model = genai.GenerativeModel('models/gemini-flash-latest')
    print(f"✓ Gemini configurado: models/gemini-flash-latest")
except Exception as e:
    print(f"⚠ Modelo gemini-flash-latest falhou: {e}")
    print(f"⚠ Tentando models/gemini-2.5-flash como fallback...")
    try:
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        print(f"✓ Gemini configurado: models/gemini-2.5-flash (fallback)")
    except Exception as e2:
        print(f"✗ Erro ao configurar modelos: {e2}")
        raise

# Import SmartAI handler
from .ai_handler import SmartAI


class AIBrain:
    """AI-powered brain for intelligent automation decisions"""

    def __init__(self, no_ai_fallback: bool = False):
        # Use modelo global configurado no topo
        self.model = model
        # Initialize SmartAI handler for resume analysis with fallback
        self.smart_ai = SmartAI()
        self._last_reason = "No reason available yet"  # Initialize reason storage
        self._last_justificativa = "No justification available yet"
        self._last_skills_faltantes = []
        self._last_score = 0.0
        # Quando True, usa heurística local quando Groq e Gemini falham (ex.: 429)
        self.no_ai_fallback = no_ai_fallback

    def calculate_heuristic_score(self, job_description: str, resume_data: Dict[str, Any]) -> float:
        """
        Fallback local sem chamada de API. Score por keywords, senioridade, remote, moeda forte e global.
        Limite: 0.0 a 1.0.
        """
        if not job_description:
            return 0.0
        text = (job_description if isinstance(job_description, str) else str(job_description)).lower()
        score = 0.0
        # Keywords: +0.1 por tecnologia do stack presente na vaga (máx ~0.5 com 5 techs)
        stack = resume_data.get("stack_tecnico") or []
        for tech in stack[:10]:
            if tech and str(tech).lower() in text:
                score += 0.1
        score = min(score, 0.5)  # cap keywords
        # Senioridade: +0.3 se vaga pede Senior/Staff/Lead e currículo é Senior
        seniority = (resume_data.get("senioridade_pretendida") or "").lower()
        if seniority in ("senior", "staff", "lead", "especialista"):
            if any(k in text for k in ("senior", "staff", "lead")):
                score += 0.3
        # Remote: +0.2 se "remote" ou "remoto"
        if "remote" in text or "remoto" in text:
            score += 0.2
        # Bônus moeda forte (+0.25): USD, dollar, US$, CAD, EUR, £, Dólar
        currency_terms = ("usd", "dollar", "us$", "cad", "eur", "£", "dólar", "dolar")
        if any(term in text for term in currency_terms):
            score += 0.25
        # Bônus global tech (+0.1): English, Fluent, International, Global
        global_terms = ("english", "fluent", "international", "global")
        if any(term in text for term in global_terms):
            score += 0.1
        return max(0.0, min(1.0, score))

    def analyze_resume(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract structured JSON from resume PDF using SmartAI (Gemini -> Groq -> Static fallback)
        
        Returns:
            {
                "stack_tecnico": ["Python", "JavaScript", ...],
                "experiencia_anos": 5,
                "senioridade_pretendida": "senior",
                "palavras_chave": ["automation", "backend", ...],
                "educacao": [...],
                "experiencia_profissional": [...]
            }
        """
        # Use SmartAI handler which automatically handles fallback
        result = self.smart_ai.analyze_resume(pdf_path)
        
        # Ensure required fields exist
        if 'stack_tecnico' not in result:
            result['stack_tecnico'] = []
        if 'experiencia_anos' not in result:
            result['experiencia_anos'] = 0
        if 'senioridade_pretendida' not in result:
            result['senioridade_pretendida'] = 'pleno'
        if 'palavras_chave' not in result:
            result['palavras_chave'] = []
        if 'educacao' not in result:
            result['educacao'] = []
        if 'experiencia_profissional' not in result:
            result['experiencia_profissional'] = []
        
        return result

    def _evaluate_job_via_groq(self, prompt: str) -> Optional[str]:
        """
        Motor principal: calcula Match Score via Groq (llama-3.3-70b).
        Groq tem RPM mais generoso; Gemini fica como fallback.
        Returns:
            Texto da resposta (JSON) ou None se falhar.
        """
        if not getattr(self.smart_ai, "groq_client", None):
            print("  ⚠ Groq não disponível (GROQ_API_KEY?).")
            return None
        try:
            response = self.smart_ai.groq_client.chat.completions.create(
                model=self.smart_ai.groq_model,
                messages=[
                    {"role": "system", "content": "You are a job-resume matcher. Return ONLY valid JSON with match_score, is_remote_eligible, reasoning, reason, justificativa, skills_faltantes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )
            text = response.choices[0].message.content.strip()
            if text:
                print("  [AI] Groq (Primary) → Match score OK")
            return text or None
        except Exception as e:
            print(f"  ⚠ Groq error: {e}")
            return None
    
    def evaluate_job(self, job_description: str, resume_data: Dict[str, Any], job_location: str = "") -> float:
        """
        Evaluate job match score (0 to 1). Groq (Llama 3.3 70B) é o motor principal;
        Gemini atua apenas como fallback secundário quando Groq falha.
        Rejects non-remote jobs or jobs that don't accept LATAM candidates.
        
        Args:
            job_description: Full job description text
            resume_data: Extracted resume data
            job_location: Job location string
            
        Returns:
            Match score between 0.0 and 1.0 (0.0 if not remote eligible)
        """
        # Extract job title from description if available
        job_title = ""
        if isinstance(job_description, dict):
            job_title = job_description.get('title', '')
            job_description = job_description.get('description', '')
        elif 'title' in str(job_description):
            # Try to extract title from description string
            lines = str(job_description).split('\n')
            if lines:
                job_title = lines[0][:100]
        
        print(f"DEBUG: Calculando match para {job_title or 'vaga'}...")
        
        # FORCE DEBUG: Print entrada ANTES de qualquer try
        print("\n" + "="*50)
        print(f"🔥 DEBUG ENTRADA GEMINI")
        print(f"Resume data type: {type(resume_data)}")
        print(f"Resume data keys: {list(resume_data.keys()) if isinstance(resume_data, dict) else 'Not a dict'}")
        print(f"Job description type: {type(job_description)}")
        print(f"Job description length: {len(job_description) if job_description else 0}")
        print(f"Job location: {job_location}")
        print("="*50 + "\n")
        
        try:
            resume_summary = json.dumps({
                "skills": resume_data.get("stack_tecnico", []),
                "experience_years": resume_data.get("experiencia_anos", 0),
                "seniority": resume_data.get("senioridade_pretendida", ""),
                "keywords": resume_data.get("palavras_chave", []),
                "location": "Brazil/LATAM"
            }, ensure_ascii=False)
            
            full_text = f"Location: {job_location}\n\n{job_description[:2000] if job_description else 'NO DESCRIPTION'}"
            
            # FORCE DEBUG: Verificar se textos estão vazios
            print("\n" + "="*50)
            print(f"🔥 DEBUG ENTRADA GEMINI - VALIDAÇÃO")
            print(f"Resume summary length: {len(resume_summary)}")
            print(f"Full text length: {len(full_text)}")
            print(f"Resume summary (first 200 chars): {resume_summary[:200]}")
            print(f"Full text (first 200 chars): {full_text[:200]}")
            print("="*50 + "\n")
            
            if len(resume_summary) < 10 or len(full_text) < 10:
                raise ValueError("ERRO CRÍTICO: Texto enviado para o Gemini está vazio ou muito curto!")
            
            # DEBUG: Log entrada
            print(f"  DEBUG BRAIN: Texto do currículo enviado (primeiros 200 chars): {resume_summary[:200]}")
            print(f"  DEBUG BRAIN: Texto da vaga enviado (primeiros 200 chars): {full_text[:200]}")
            
            prompt = f"""Analyze the job description and candidate resume. Return ONLY a JSON object with a match score from 0.0 to 1.0.

CRITICAL REMOTE ELIGIBILITY CHECK:
- The candidate is located in Brazil/LATAM and can ONLY work remotely
- REJECT (score = 0.0) if the job mentions:
  * "Hybrid", "On-site", "Onsite", "Office-based"
  * "Must be US Citizen" or "Authorized to work in US/EU/UK only"
  * Location restrictions outside Latin America
  * "Local candidates only" or similar restrictions
- ACCEPT (can score > 0) if the job mentions:
  * "Remote", "Remoto", "Work from Home", "WFH"
  * "Anywhere", "Worldwide", "Global"
  * "Remote LATAM", "Remote Brazil", "Latin America"
  * Explicitly accepts international/remote candidates

Job Description:
{full_text}

Candidate Resume Summary:
{resume_summary}

Return ONLY this JSON format (no markdown, no explanations):
{{
    "match_score": <float between 0.0 and 1.0>,
    "is_remote_eligible": <true if remote and accepts LATAM, false otherwise>,
    "reasoning": "detailed explanation including: why this score, what skills match/don't match, seniority alignment, and remote eligibility. If score is low, explain specifically why (e.g., 'Seniority mismatch: job requires 8+ years, candidate has 2 years' or 'Stack mismatch: job requires React, candidate is Python-focused')",
    "reason": "brief one-line explanation of the score (e.g., 'Good match: Python/Backend skills align' or 'Low score: Seniority mismatch (2 years vs 8+ required)')",
    "justificativa": "detailed explanation in Portuguese: why this score was given, what skills match/don't match, seniority alignment, and what's missing. Example: 'O candidato tem AWS e Node, mas a vaga pede 5 anos de experiência e ele tem 2.'",
    "skills_faltantes": ["list of missing skills that the job requires but candidate doesn't have, e.g., ['Docker', 'Kubernetes']"]
}}

Consider:
- REMOTE ELIGIBILITY (MANDATORY - score must be 0.0 if not remote eligible)
- Technical skills match (BE LENIENT - if candidate has the main language of the job, give minimum 0.5)
- Experience level alignment (DON'T be too strict - if job doesn't specify exact years, don't penalize)
- Seniority requirements (DON'T reject if seniority differs - reduce score by 0.1-0.2 max)
- Domain knowledge overlap

CRITICAL RULE: You are a recruiter who gives chances. If the candidate has the main language of the job (e.g., Python or Node), the minimum score MUST be 0.5, regardless of seniority differences.

SCORING GUIDELINES (Be LESS RIGOROUS - prioritize volume):
- 0.9-1.0: Perfect match - all required skills match, same domain, right seniority
- 0.7-0.8: Good match - most skills match, similar domain
- 0.5-0.6: Moderate match - some skills match, different domain acceptable
- 0.3-0.4: Weak match - few skills match, different domain
- 0.0-0.2: Poor match - minimal overlap, wrong domain

FLEXIBILITY RULES (Be lenient):
1. If candidate has "Node" and job requires "Javascript", consider it a HIGH partial match (0.6-0.7).
2. If candidate has 2 years and job doesn't specify exact decades required, DON'T give zero score.
3. Give a score of 0.5 for ANY Backend or Fullstack job that uses languages from the candidate's stack.
4. If the job is for Python, Backend, or Fullstack (even if seniority differs), give a base score of at least 0.5. Experience level differences should reduce by 0.1-0.2 max, but not below 0.3 if technical stack matches.
5. Be flexible with technology variations: "Docker" vs "Docker Compose", "React" vs "React.js", etc. - treat as matches.

IMPORTANT: Only give scores below 0.3 if the job is COMPLETELY different (e.g., "Frontend React Developer" when candidate is pure "Python Backend" with no frontend experience).

If the job is NOT remote eligible, return match_score: 0.0 and is_remote_eligible: false."""

            # Inversão de prioridade: Groq (llama-3.3-70b-versatile) primeira tentativa; Gemini só fallback
            response_text = None
            print("  [AI] Calling Groq (Primary)...")
            response_text = self._evaluate_job_via_groq(prompt)
            
            if not response_text:
                # Fallback: Gemini quando Groq falha; backoff curto (10–20s) pois não é mais motor principal
                print("  [AI] Calling Gemini (Fallback)...")
                max_retries = 2
                for attempt in range(max_retries):
                    try:
                        response = self.model.generate_content(prompt)
                        response_text = response.text.strip()
                        if response_text:
                            print("  [AI] Gemini (Fallback) → Match score OK")
                        break
                    except Exception as e:
                        error_str = str(e)
                        if "429" in error_str or "quota" in error_str.lower() or "Quota exceeded" in error_str:
                            if attempt < max_retries - 1:
                                backoff = random.randint(10, 20)
                                print(f"  ⚠ Gemini 429. Waiting {backoff}s (backoff 10–20s) before retry {attempt + 1}/{max_retries}...")
                                time.sleep(backoff)
                                continue
                            print("  ✗ Gemini 429 após retries.")
                        else:
                            print(f"  ⚠ Gemini error: {error_str[:80]}")
                        if getattr(self, "no_ai_fallback", False):
                            print("  [FALLBACK] AI Quota Exceeded. Using Heuristic Scoring...")
                            return self.calculate_heuristic_score(full_text, resume_data)
                        print("  ⚠ Brain error, defaulting to score 0.6 (Optimistic Mode)")
                        return 0.6
            
            if not response_text:
                if getattr(self, "no_ai_fallback", False):
                    print("  [FALLBACK] AI Quota Exceeded. Using Heuristic Scoring...")
                    return self.calculate_heuristic_score(full_text, resume_data)
                print("  ⚠ Nenhuma resposta (Groq/Gemini). Retornando score padrão.")
                print("  ⚠ Brain error, defaulting to score 0.6 (Optimistic Mode)")
                return 0.6
            
            # Debug: resposta pode vir do Groq ou do Gemini
            print(f"\n{'='*60}")
            print(f"DEBUG RAW (Groq/Gemini): {response_text[:200]}...")
            print(f"{'='*60}\n")
            
            # Try to parse JSON first
            result = None
            try:
                # Remove markdown if present
                cleaned_text = response_text
                if cleaned_text.startswith('```'):
                    cleaned_text = cleaned_text.split('```')[1]
                    if cleaned_text.startswith('json'):
                        cleaned_text = cleaned_text[4:]
                    cleaned_text = cleaned_text.strip()
                
                result = json.loads(cleaned_text)
                print(f"  DEBUG BRAIN: JSON parseado com sucesso")
            except json.JSONDecodeError as e:
                print(f"  ⚠ DEBUG BRAIN: Erro ao parsear JSON: {e}")
                print(f"  DEBUG BRAIN: Tentando extrair primeiro número float com regex...")
                
                # Fallback: Extract FIRST float number from response using regex
                number_match = re.search(r'([0-9]*\.?[0-9]+)', response_text)
                if number_match:
                    try:
                        extracted_score = float(number_match.group(1))
                        # Normalize to 0-1 range
                        if extracted_score > 1.0:
                            extracted_score = extracted_score / 100.0 if extracted_score <= 100 else 1.0
                        if 0.0 <= extracted_score <= 1.0:
                            print(f"  DEBUG BRAIN: Score extraído via regex: {extracted_score}")
                            result = {
                                "match_score": extracted_score,
                                "is_remote_eligible": True,
                                "reasoning": "Score extracted via regex fallback",
                                "reason": f"Score: {extracted_score}",
                                "justificativa": f"Score extraído automaticamente: {extracted_score}",
                                "skills_faltantes": []
                            }
                        else:
                            print(f"  ⚠ DEBUG BRAIN: Score extraído fora do range: {extracted_score}")
                            result = None
                    except ValueError:
                        print(f"  ⚠ DEBUG BRAIN: Não foi possível converter para float")
                        result = None
                else:
                    print(f"  ⚠ DEBUG BRAIN: Nenhum número encontrado na resposta")
                    result = None
            
            # If still no result, try emergency prompt (just a number) - SEM try/except
            if result is None:
                print(f"  ⚠ DEBUG BRAIN: Tentando prompt de emergência (apenas número)...")
                emergency_prompt = f"""Analyze this job and candidate. Return ONLY a number between 0.0 and 1.0. No text, no explanation, just the number.

Job: {full_text[:500]}
Candidate: {resume_summary[:500]}

If remote eligible and has main language match, return at least 0.5. Otherwise return 0.0.
Return ONLY the number:"""
                
                emergency_response = self.model.generate_content(emergency_prompt)
                emergency_text = emergency_response.text.strip()
                print(f"  DEBUG BRAIN: Resposta emergência: {emergency_text}")
                
                # Extract FIRST float number from response
                number_match = re.search(r'([0-9]*\.?[0-9]+)', emergency_text)
                if number_match:
                    emergency_score = float(number_match.group(1))
                    if 0.0 <= emergency_score <= 1.0:
                        result = {
                            "match_score": emergency_score,
                            "is_remote_eligible": True,
                            "reasoning": "Emergency fallback - score extracted from number-only response",
                            "reason": f"Emergency score: {emergency_score}",
                            "justificativa": f"Score de emergência: {emergency_score}",
                            "skills_faltantes": []
                        }
                        print(f"  ✓ DEBUG BRAIN: Score de emergência: {emergency_score}")
                    else:
                        print(f"  ⚠ DEBUG BRAIN: Score de emergência fora do range: {emergency_score}")
                else:
                    print(f"  ⚠ DEBUG BRAIN: Nenhum número encontrado na resposta de emergência")
            
            # If still no result, return 0.0 with error logging
            if result is None:
                print(f"  ✗ DEBUG BRAIN: Não foi possível obter score. Retornando 0.0")
                print(f"  ❌ ERRO DA IA: Resposta completa do Gemini: {response_text}")
                print(f"  ❌ ERRO DA IA: Verifique se é quota, segurança ou bloqueio de conteúdo")
                return 0.0
            
            # Check remote eligibility first (only if result has this field)
            is_remote_eligible = result.get('is_remote_eligible', True)
            if not is_remote_eligible:
                reasoning = result.get('reasoning', 'Not remote eligible')
                print(f"  ⚠ Job rejected: Not remote eligible for LATAM candidate")
                print(f"    Reasoning: {reasoning}")
                return 0.0
            
            score = float(result.get('match_score', 0.0))
            
            # FORÇAR LOG DE ERRO SE SCORE FOR 0.0
            if score == 0.0:
                print(f"\n  ❌ ERRO DA IA: Score retornado foi 0.0")
                print(f"  Resposta completa do Gemini: {response_text[:1000]}")
                print(f"  Verifique se é:")
                print(f"    - Quota excedida (quota exceeded)")
                print(f"    - Bloqueio de segurança (safety)")
                print(f"    - Bloqueio de conteúdo (content blocked)")
                print(f"    - Erro de API (API error)")
            
            reasoning = result.get('reasoning', 'No reasoning provided')
            reason = result.get('reason', reasoning[:100])  # Use reason if available, fallback to reasoning
            justificativa = result.get('justificativa', reasoning)  # Portuguese justification
            skills_faltantes = result.get('skills_faltantes', [])  # Missing skills
            
            # FORÇAR LOG DE JUSTIFICATIVA (obrigatório)
            if not justificativa or justificativa.strip() == "":
                print(f"  ❌ ERRO CRÍTICO: Gemini não retornou justificativa!")
                print(f"  Resposta completa: {response_text[:500]}")
                raise ValueError("Gemini não retornou justificativa - sistema deve parar!")
            
            # Store all info for later use
            self._last_reason = reason
            self._last_justificativa = justificativa
            self._last_skills_faltantes = skills_faltantes
            self._last_score = score
            
            # Log reasoning for all scores (verbose mode)
            print(f"\n  📊 JUSTIFICATIVA DO GEMINI:")
            print(f"  Score: {score:.2f}")
            print(f"  Justificativa: {justificativa}")
            if skills_faltantes:
                print(f"  Skills faltantes: {', '.join(skills_faltantes)}")
            print()
            
            # FALLBACK: If score is 0.0 or very low, check for common technologies
            if score == 0.0 or score < 0.1:
                print(f"  ⚠ Score muito baixo ({score:.2f}). Verificando tecnologias em comum...")
                candidate_skills = resume_data.get("stack_tecnico", [])
                job_text_lower = (job_description or "").lower()
                
                # Check for common technologies
                common_techs = []
                for skill in candidate_skills:
                    skill_lower = str(skill).lower()
                    # Check if skill appears in job description
                    if skill_lower in job_text_lower:
                        common_techs.append(skill)
                    # Also check for variations (React vs React.js, Python vs Python3)
                    skill_variations = [
                        skill_lower.replace('.js', '').replace('.', ''),
                        skill_lower + '.js',
                        skill_lower + '3',
                        skill_lower.replace(' ', '')
                    ]
                    for variation in skill_variations:
                        if variation in job_text_lower and skill not in common_techs:
                            common_techs.append(skill)
                            break
                
                if common_techs:
                    print(f"  ✓ Tecnologias em comum encontradas: {', '.join(common_techs[:5])}")
                    print(f"  → Aplicando score mínimo de 0.5 (fallback)")
                    score = max(score, 0.5)  # Minimum score of 0.5 if technologies match
                    self._last_score = score
            
            if score < 0.3:
                print(f"  ⚠ Low score ({score:.2f}): {justificativa}")
                if skills_faltantes:
                    print(f"    Skills faltantes: {', '.join(skills_faltantes)}")
            elif score < 0.5:
                print(f"  ⚠ Moderate-low score ({score:.2f}): {justificativa}")
            elif score < 0.7:
                print(f"  ℹ Moderate score ({score:.2f}): {justificativa}")
            else:
                print(f"  ✓ Good score ({score:.2f}): {justificativa}")
            
            # Clamp to 0-1 range
            return max(0.0, min(1.0, score))
            
        except Exception as e:
            print(f"Error evaluating job with Gemini: {e}")
            
            # FALLBACK: Check for common technologies and assign minimum score
            candidate_skills = resume_data.get("stack_tecnico", [])
            job_text_lower = (str(job_description) or "").lower()
            
            # Check for common technologies
            common_techs = []
            for skill in candidate_skills:
                skill_lower = str(skill).lower()
                if skill_lower in job_text_lower:
                    common_techs.append(skill)
                # Check variations
                skill_variations = [
                    skill_lower.replace('.js', '').replace('.', ''),
                    skill_lower + '.js',
                    skill_lower + '3',
                    skill_lower.replace(' ', '')
                ]
                for variation in skill_variations:
                    if variation in job_text_lower and skill not in common_techs:
                        common_techs.append(skill)
                        break
            
            if common_techs:
                print(f"  ✓ Fallback: Tecnologias em comum encontradas: {', '.join(common_techs[:5])}")
                print(f"  → Retornando score mínimo de 0.5 (fallback após erro)")
                return 0.5
            
            # On error, do basic remote check
            description_lower = job_description.lower() if job_description else ""
            location_lower = job_location.lower() if job_location else ""
            
            # Quick rejection check
            reject_indicators = ['hybrid', 'on-site', 'onsite', 'must be us citizen', 
                               'authorized to work in us', 'eu only', 'uk only']
            if any(indicator in description_lower or indicator in location_lower 
                   for indicator in reject_indicators):
                return 0.0
            
            # Quick acceptance check
            remote_indicators = ['remote', 'remoto', 'anywhere', 'work from home', 
                              'latam', 'latin america', 'brazil']
            if any(indicator in description_lower or indicator in location_lower 
                   for indicator in remote_indicators):
                return 0.5  # Default neutral score if remote
            else:
                return 0.0  # Reject if unclear
    
    def resolve_form_fields(self, html_chunk: str, field_names: List[str]) -> Dict[str, str]:
        """
        Analyze HTML and return CSS/XPath selectors for form fields
        Uses SmartAI with fallback (Gemini -> Groq -> Manual selectors)
        
        Args:
            html_chunk: HTML content (can be partial page)
            field_names: List of field names to find (e.g., ["email", "name", "phone", "resume"])
            
        Returns:
            {
                "email": "#email-input or input[name='email'] or ...",
                "name": "selector for name field",
                ...
            }
        """
        # Limit HTML size to avoid token limits
        html_preview = html_chunk[:5000]  # First 5000 chars
        
        prompt = f"""Analyze this HTML form and find CSS selectors or XPath for the requested fields.

HTML (partial):
{html_preview}

Fields to find: {', '.join(field_names)}

For each field, return the BEST selector (CSS selector preferred, XPath if CSS not possible).
Consider:
- id attributes
- name attributes
- label associations (for attribute)
- placeholder text
- nearby text labels
- input type attributes

Return ONLY valid JSON (no markdown, no explanations):
{{
    "email": "best selector for email field",
    "name": "best selector for name field",
    "phone": "best selector for phone field",
    "resume": "best selector for resume upload field",
    ...
}}

If a field is not found, use null for that field."""

        # Use SmartAI with fallback (Gemini -> Groq)
        try:
            response_text = self.smart_ai.generate_content(prompt)
            
            # Remove markdown if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            # Try to extract JSON
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from text
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    raise ValueError("Could not extract JSON from AI response")
            
            # Ensure all requested fields are in result (even if null)
            for field in field_names:
                if field not in result:
                    result[field] = None
            
            print(f"  ✓ AI resolved {len([f for f in field_names if result.get(f)])} field selectors")
            return result
            
        except Exception as e:
            error_str = str(e).lower()
            is_429 = '429' in error_str or 'quota' in error_str or 'rate limit' in error_str
            
            if is_429:
                print(f"  ⚠ AI Quota Exceeded (429) when resolving form fields. Using manual fallback...")
            else:
                print(f"  ⚠ Error resolving form fields with AI: {e}. Using manual fallback...")
            
            # Return empty dict with nulls - applier will use manual selectors
            return {field: None for field in field_names}
    
    def answer_form_question(self, question_text: str, question_type: str, user_data: Dict[str, any], resume_data: Dict[str, any] = None) -> str:
        """
        Answer form questions using user identity and resume data
        Step 2: Form Negotiator - Uses AI to answer questions based on user profile
        
        Args:
            question_text: The question text from the form
            question_type: Type of question (experience, qualification, contract_type, etc.)
            user_data: User configuration data (from user_config.json)
            resume_data: Resume data with experience, skills, metrics (optional)
            
        Returns:
            str: Answer to the question
        """
        # Build identity prompt based on user_config.json
        name = user_data.get('name', 'Felipe França Nogueira')
        experience_years = resume_data.get('experiencia_anos', 8) if resume_data else 8
        
        # Extract metrics from resume if available
        metrics = []
        if resume_data and resume_data.get('experiencia_profissional'):
            for exp in resume_data['experiencia_profissional']:
                if isinstance(exp, dict):
                    desc = exp.get('description', '') or exp.get('descricao', '')
                    if '30%' in desc or '40%' in desc or 'reduction' in desc.lower() or 'increase' in desc.lower():
                        metrics.append(desc[:200])  # Limit length
        
        # System Prompt: Identidade completa do Felipe
        location = user_data.get('location', 'Rio de Janeiro, Brasil')
        salary_range_usd = user_data.get('salary_range_usd', '$5k - $8k USD')
        salary_range_brl = user_data.get('salary_range_brl', 'R$ 15k - R$ 22k PJ')
        stack_tecnico = resume_data.get('stack_tecnico', []) if resume_data else []
        stack_str = ', '.join(stack_tecnico[:10]) if stack_tecnico else 'React, Node.js, Python, OpenAI/LangChain'
        
        # Build identity context with complete profile
        identity_prompt = f"""Você é o assistente de candidatura do {name}, um Senior Full Stack Engineer com {experience_years} anos de experiência real (começou em 2017).

CONTEXTO DO PERFIL:
- Nome: {name}
- Senioridade: Senior Full Stack Engineer
- Experiência Total: {experience_years} anos (timeline real desde 2017)
- Localização: {location} (aceita remoto global)
- Email: {user_data.get('email', 'N/A')}
- LinkedIn: {user_data.get('linkedin', 'N/A')}
- Telefone: {user_data.get('phone', 'N/A')}

STACK TÉCNICO:
{stack_str}

ESPECIALIZAÇÕES:
- Especialista em React, Node.js, Python
- Integração de IA (OpenAI/LangChain)
- Arquitetura de sistemas escaláveis
- Otimização de performance

MÉTRICAS DE OURO (Impacto Real):
{chr(10).join(f"- {m}" for m in metrics[:3]) if metrics else "- Redução de 30% no tempo de resposta (Redis/AI)" + chr(10) + "- 40% de aumento em reusabilidade de código (UI Library)"}

PRETENSÃO SALARIAL:
- USD: {salary_range_usd}
- BRL (PJ): {salary_range_brl}
- Use range de mercado sênior para Latam/USA quando perguntado

INSTRUÇÕES ESPECÍFICAS PARA RESPOSTAS:
1. Anos de Experiência: Responda sempre com base na timeline real ({experience_years} anos de experiência total desde 2017).
   - Exemplo: "Quantos anos de experiência com Nuxt.js?" → "1 ano, focado na Basis"
   - Exemplo: "Anos de experiência total?" → "{experience_years} anos"

2. Visto/Autorização: Se perguntarem sobre visto para trabalhar nos EUA ou outros países:
   - Responda conforme user_config.json
   - Se não especificado, responda honestamente (ex: "Não, mas aberto a relocação")

3. Salário/Pretensão: Se perguntarem sobre pretensão salarial:
   - Use range de mercado sênior: {salary_range_usd} ou {salary_range_brl}
   - Seja específico mas flexível

4. Qualificações Técnicas: Se perguntarem sobre tecnologias específicas:
   - Confirme experiência real baseada no stack técnico
   - Seja honesto: se não tem experiência, diga "Não, mas tenho experiência similar em [tecnologia relacionada]"

5. Proposta de Valor: Quando apropriado, mencione métricas de impacto:
   - Redução de 30% no tempo de resposta
   - 40% de aumento em reusabilidade de código
   - Mas seja natural, não force

6. Localização: Se perguntarem sobre localização ou remoto:
   - Rio de Janeiro, Brasil
   - Aceita remoto global

PERGUNTA DO FORMULÁRIO:
Tipo: {question_type}
Texto: "{question_text}"

Responda de forma profissional, concisa e baseada nos dados reais do perfil. Retorne APENAS a resposta, sem explicações adicionais.

IMPORTANTE: Seja específico e honesto. Use os dados reais do perfil. Não invente experiências que não existem."""

        try:
            response = self.smart_ai.generate_content(identity_prompt)
            # Clean response
            response = response.strip()
            # Remove quotes if present
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]
            if response.startswith("'") and response.endswith("'"):
                response = response[1:-1]
            
            print(f"  ✓ [Form Negotiator] Answered {question_type}: {response[:50]}...")
            return response
        except Exception as e:
            print(f"  ⚠ Error generating answer with AI: {e}")
            # Fallback answers based on question type
            if 'experience' in question_type.lower() or 'anos' in question_text.lower() or 'years' in question_text.lower():
                return str(experience_years)
            elif 'qualification' in question_type.lower() or 'match' in question_text.lower():
                return "Yes" if 'en' in question_text.lower() else "Sim"
            elif 'contract' in question_type.lower() or 'vínculo' in question_text.lower():
                return user_data.get('contract_type', 'Full-time') if user_data.get('contract_type') else "Full-time"
            else:
                return "Yes" if 'en' in question_text.lower() else "Sim"
    
    def find_submit_button(self, html_chunk: str) -> Optional[str]:
        """
        Find the submit/apply button selector in HTML
        Uses SmartAI with fallback (Gemini -> Groq)
        
        Returns:
            CSS selector or XPath for submit button, or None
        """
        try:
            html_preview = html_chunk[:3000]
            
            prompt = f"""Find the submit/apply button in this HTML form.

HTML (partial):
{html_preview}

Return ONLY a JSON object with the selector:
{{
    "selector": "best CSS selector or XPath for submit/apply button"
}}

Look for:
- button[type='submit']
- buttons with text "Apply", "Submit", "Aplicar", "Enviar"
- links with apply/submit text
- form submit buttons

Return ONLY the JSON, no markdown."""

            # Use SmartAI with fallback (Gemini -> Groq)
            response_text = self.smart_ai.generate_content(prompt)
            response_text = response_text.strip()
            
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            # Try to parse JSON
            try:
                result = json.loads(response_text)
                return result.get('selector')
            except json.JSONDecodeError:
                # Try to extract selector from text
                selector_match = re.search(r'["\']selector["\']\s*:\s*["\']([^"\']+)["\']', response_text)
                if selector_match:
                    return selector_match.group(1)
                # Try to find any CSS selector in response
                css_match = re.search(r'(input|button|a)\[[^\]]+\]|#[a-zA-Z][\w-]+|\.\w+', response_text)
                if css_match:
                    return css_match.group(0)
                return None
            
        except Exception as e:
            error_str = str(e).lower()
            is_429 = '429' in error_str or 'quota' in error_str or 'rate limit' in error_str
            if is_429:
                print(f"  ⚠ AI Quota Exceeded (429) when finding submit button. Using manual selectors...")
            else:
                print(f"  ⚠ Error finding submit button with AI: {e}. Using manual selectors...")
            return None
    
    def audit_and_fix(self, log_file_path: str = "logs/applications_history.json") -> Dict[str, Any]:
        """
        Audit recent failures and generate root cause analysis
        Returns suggestions for code fixes if patterns are detected
        
        Returns:
            {
                "audit_complete": bool,
                "total_failures": int,
                "recurring_errors": List[Dict],
                "root_cause_analysis": str,
                "code_fixes": List[Dict],
                "fixes_applied": int
            }
        """
        try:
            log_path = Path(log_file_path)
            if not log_path.exists():
                return {
                    "audit_complete": False,
                    "message": "No logs found to audit",
                    "total_failures": 0,
                    "recurring_errors": [],
                    "code_fixes": []
                }
            
            # Load logs
            with open(log_path, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            
            if not logs:
                return {
                    "audit_complete": True,
                    "message": "No logs to analyze",
                    "total_failures": 0,
                    "recurring_errors": [],
                    "code_fixes": []
                }
            
            # Get recent failures (last 20)
            recent_logs = logs[-20:] if len(logs) > 20 else logs
            # Include both code errors AND match failures (low scores)
            failures = []
            for log in recent_logs:
                status = log.get('status', '')
                # Code errors
                if status in ['failed', 'APPLICATION_FAILED', 'EXCEPTION']:
                    failures.append(log)
                # Match failures (low scores that prevented application)
                elif status == 'APPLIED_SUCCESSFULLY' or status == 'APPLICATION_FAILED':
                    match_score = log.get('match_score', 1.0)
                    if match_score < 0.3:  # Low match score
                        failures.append({
                            **log,
                            'error_type': 'match_failure',
                            'error_details': {
                                'type': 'low_match_score',
                                'message': f"Match score too low: {match_score:.2f}",
                                'reason': log.get('match_analysis', 'No analysis available')
                            }
                        })
            
            if not failures:
                return {
                    "audit_complete": True,
                    "message": "No failures to analyze",
                    "total_failures": 0,
                    "recurring_errors": [],
                    "code_fixes": []
                }
            
            # Analyze failures with Gemini
            failures_summary = []
            for failure in failures:
                error_details = failure.get('error_details', {})
                if isinstance(error_details, str):
                    error_msg = error_details
                elif isinstance(error_details, dict):
                    error_msg = error_details.get('message', str(error_details))
                else:
                    error_msg = str(error_details)
                
                failures_summary.append({
                    "job_title": failure.get('job_title', 'Unknown'),
                    "company": failure.get('company', 'Unknown'),
                    "url": failure.get('url', ''),
                    "error": error_msg[:200],  # Limit size
                    "error_type": error_details.get('type', 'unknown') if isinstance(error_details, dict) else 'unknown',
                    "gemini_suggestion": failure.get('gemini_suggestion', ''),
                    "selectors_used": failure.get('selectors_used', {})
                })
            
            # Use Gemini to analyze patterns
            prompt = f"""Analyze these job application failures and identify recurring patterns and root causes.

Failures ({len(failures)} total):
{json.dumps(failures_summary, indent=2, ensure_ascii=False)[:3000]}

Identify:
1. Recurring error patterns (same error in 2+ applications)
2. Root causes (e.g., "SelectorNotFound for email field", "Submit button changed ID")
3. Code fixes needed (specific changes to applier.py or brain.py)

Return ONLY valid JSON (no markdown):
{{
    "root_cause_analysis": "Summary of main issues found",
    "recurring_errors": [
        {{
            "error_type": "SelectorNotFound",
            "error_description": "Email field selector failed in 3 applications",
            "occurrence_count": 3,
            "affected_companies": ["Company1", "Company2"],
            "suggested_fix": "Update email selector logic in applier.py to use AI fallback",
            "code_change": {{
                "file": "modules/applier.py",
                "function": "find_element_with_fallback",
                "change": "Add AI-powered selector resolution when traditional selectors fail"
            }}
        }}
    ],
    "code_fixes": [
        {{
            "file": "modules/applier.py",
            "location": "Line ~450 in fill_field method",
            "current_code": "element = self.page.query_selector(selector)",
            "suggested_code": "element = self.find_element_with_fallback(selector, use_ai=True)",
            "reason": "Recurring SelectorNotFound errors require AI fallback"
        }}
    ],
    "priority": "high|medium|low"
}}

Focus on actionable fixes that can be applied automatically."""
            
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            analysis = json.loads(response_text)
            
            # Count recurring errors (2+ occurrences)
            recurring = [err for err in analysis.get('recurring_errors', []) 
                        if err.get('occurrence_count', 0) >= 2]
            
            return {
                "audit_complete": True,
                "total_failures": len(failures),
                "recurring_errors": recurring,
                "root_cause_analysis": analysis.get('root_cause_analysis', 'No patterns identified'),
                "code_fixes": analysis.get('code_fixes', []),
                "priority": analysis.get('priority', 'low')
            }
            
        except Exception as e:
            print(f"Error in audit_and_fix: {e}")
            import traceback
            traceback.print_exc()
            return {
                "audit_complete": False,
                "error": str(e),
                "total_failures": 0,
                "recurring_errors": [],
                "code_fixes": []
            }


if __name__ == "__main__":
    # Test the brain
    brain = AIBrain()
    print("AI Brain initialized with Gemini 1.5 Flash")
    print(f"API Key configured: {bool(os.getenv('GEMINI_API_KEY'))}")

