"""
PDF Resume Parser Module
Extracts structured data from PDF resume using AI (Gemini) and fallback to regex
"""
import pdfplumber
import fitz  # PyMuPDF
import re
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .brain import AIBrain


class ResumeData(BaseModel):
    """Structured resume data model"""
    stack_tecnico: List[str] = Field(default_factory=list, description="Technical stack/skills")
    experiencia_anos: int = Field(default=0, description="Years of experience")
    senioridade_pretendida: str = Field(default="", description="Desired seniority level")
    palavras_chave: List[str] = Field(default_factory=list, description="Keywords from resume")


class ResumeParser:
    """Parser for extracting structured data from PDF resumes using AI (Gemini)"""
    
    # Common technical skills patterns (fallback)
    TECH_KEYWORDS = [
        'python', 'javascript', 'typescript', 'java', 'c++', 'c#', 'go', 'rust',
        'react', 'vue', 'angular', 'node', 'django', 'flask', 'fastapi',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform',
        'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
        'git', 'ci/cd', 'jenkins', 'github actions',
        'machine learning', 'ai', 'data science', 'pandas', 'numpy',
        'playwright', 'selenium', 'pytest', 'unittest'
    ]
    
    # Seniority patterns (fallback)
    SENIORITY_PATTERNS = {
        'junior': ['junior', 'jr', 'entry', 'iniciante', 'estágio'],
        'pleno': ['pleno', 'mid', 'intermediate', 'médio'],
        'senior': ['senior', 'sr', 'sênior', 'lead', 'principal', 'expert'],
        'especialista': ['especialista', 'specialist', 'architect', 'arquiteto']
    }
    
    def __init__(self, pdf_path: str, use_ai: bool = True):
        self.pdf_path = pdf_path
        self.full_text = ""
        self.cleaned_text = ""
        self.use_ai = use_ai
        self.brain = AIBrain() if use_ai else None
        # Fixed metadata - user confirmed
        self.FIXED_EXPERIENCE_YEARS = 8
        self.FIXED_SENIORITY = 'senior'
    
    def extract_text(self) -> str:
        """Extract all text from PDF using pdfplumber (primary) or PyMuPDF (fallback)"""
        print("  Extracting text from PDF...")
        
        text_parts = []
        
        # Try pdfplumber first (better for structured text)
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                print(f"  ✓ PDF opened successfully. Pages: {len(pdf.pages)}")
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                print(f"  ✓ Extracted {sum(len(t) for t in text_parts)} characters from {len(pdf.pages)} pages")
        except Exception as e:
            print(f"  ⚠ pdfplumber extraction failed: {e}")
            # Fallback to PyMuPDF
            try:
                print(f"  Trying PyMuPDF (fallback)...")
                doc = fitz.open(self.pdf_path)
                for page in doc:
                    text = page.get_text()
                    if text:
                        text_parts.append(text)
                doc.close()
                print(f"  ✓ Extracted {sum(len(t) for t in text_parts)} characters with PyMuPDF")
            except Exception as e2:
                print(f"  ✗ PyMuPDF extraction also failed: {e2}")
                raise ValueError(f"Could not extract text from PDF: {e2}")
        
        if not text_parts:
            raise ValueError("PDF appears to be empty or unreadable")
        
        self.full_text = "\n".join(text_parts)
        return self.full_text
    
    def clean_text(self) -> str:
        """
        Pre-process and clean extracted text:
        - Remove unnecessary line breaks
        - Remove double spaces
        - Normalize whitespace
        """
        if not self.full_text:
            self.extract_text()
        
        # Clean the text
        cleaned = self.full_text
        
        # Remove excessive line breaks (keep single line breaks)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Remove double spaces
        cleaned = re.sub(r' {2,}', ' ', cleaned)
        
        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in cleaned.split('\n')]
        cleaned = '\n'.join([line for line in lines if line])  # Remove empty lines
        
        self.cleaned_text = cleaned
        print(f"  ✓ Text cleaned: {len(self.cleaned_text)} characters")
        return self.cleaned_text
    
    def extract_technical_stack(self) -> List[str]:
        """Extract technical skills from resume text"""
        found_skills = []
        text_lower = self.full_text.lower()
        
        for keyword in self.TECH_KEYWORDS:
            # Check for keyword variations
            patterns = [
                rf'\b{re.escape(keyword)}\b',
                rf'\b{re.escape(keyword.replace(" ", ""))}\b',
            ]
            
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    found_skills.append(keyword.title())
                    break
        
        # Also look for common patterns like "Skills:", "Technologies:", etc.
        skills_sections = re.findall(
            r'(?:skills?|technologies?|tech stack|stack|tools?)[:\s]+(.*?)(?:\n\n|\n[A-Z])',
            self.full_text,
            re.IGNORECASE | re.DOTALL
        )
        
        for section in skills_sections:
            # Extract words that look like tech terms
            words = re.findall(r'\b[a-z]+\+?[a-z]*\b', section.lower())
            for word in words:
                if any(kw in word for kw in self.TECH_KEYWORDS):
                    skill = word.title()
                    if skill not in found_skills:
                        found_skills.append(skill)
        
        return list(set(found_skills))  # Remove duplicates
    
    def extract_experience_years(self) -> int:
        """Extract years of experience from resume"""
        # Look for patterns like "5 years", "3+ years", "anos de experiência"
        patterns = [
            r'(\d+)\+?\s*(?:years?|anos?)\s*(?:of\s*)?(?:experience|experiência)',
            r'(?:experience|experiência)[:\s]+.*?(\d+)\+?\s*(?:years?|anos?)',
            r'(\d+)\+?\s*(?:years?|anos?)\s*(?:in|em)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, self.full_text, re.IGNORECASE)
            if matches:
                try:
                    years = max([int(m) for m in matches])
                    return years
                except ValueError:
                    continue
        
        # Look for date ranges in experience section
        date_pattern = r'(\d{4})\s*[-–]\s*(\d{4}|present|atual)'
        dates = re.findall(date_pattern, self.full_text, re.IGNORECASE)
        
        if dates:
            try:
                years_list = []
                for start, end in dates:
                    start_year = int(start)
                    if end.lower() in ['present', 'atual', 'current']:
                        from datetime import datetime
                        end_year = datetime.now().year
                    else:
                        end_year = int(end)
                    years_list.append(end_year - start_year)
                
                if years_list:
                    return max(years_list)
            except (ValueError, TypeError):
                pass
        
        return 0
    
    def extract_seniority(self) -> str:
        """Extract desired seniority level"""
        text_lower = self.full_text.lower()
        
        # Check for explicit seniority mentions
        for level, patterns in self.SENIORITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(rf'\b{re.escape(pattern)}\b', text_lower):
                    return level
        
        # Infer from years of experience
        years = self.extract_experience_years()
        if years >= 7:
            return "senior"
        elif years >= 3:
            return "pleno"
        else:
            return "junior"
    
    def extract_keywords(self) -> List[str]:
        """Extract important keywords from resume"""
        keywords = []
        
        # Extract technical stack as keywords
        keywords.extend(self.extract_technical_stack())
        
        # Extract job titles and roles
        title_patterns = [
            r'(?:software|backend|frontend|full.?stack|devops|data|ml|ai)\s+(?:engineer|developer|architect|scientist)',
            r'(?:engenheiro|desenvolvedor|arquiteto)\s+(?:de\s+)?(?:software|backend|frontend|full.?stack|devops|dados)',
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, self.full_text, re.IGNORECASE)
            keywords.extend([m.title() for m in matches])
        
        # Extract domain keywords (industries, methodologies)
        domain_keywords = [
            'agile', 'scrum', 'kanban', 'ci/cd', 'microservices',
            'rest api', 'graphql', 'aws', 'cloud', 'serverless'
        ]
        
        for keyword in domain_keywords:
            if re.search(rf'\b{re.escape(keyword)}\b', self.full_text, re.IGNORECASE):
                keywords.append(keyword.title())
        
        return list(set(keywords))  # Remove duplicates
    
    def extract_with_regex(self) -> ResumeData:
        """
        Fallback method: Extract resume data using regex patterns.
        Called when AI parsing fails (e.g., 429 quota error).
        If regex also fails, returns default skills to prevent empty resume.
        """
        print("Using regex-based extraction (fallback)...")
        
        try:
            self.extract_text()
            
            stack_tecnico = self.extract_technical_stack()
            experiencia_anos = self.extract_experience_years()
            senioridade_pretendida = self.extract_seniority()
            palavras_chave = self.extract_keywords()
            
            # If regex extraction returned empty, use hardcoded skills
            if not stack_tecnico:
                print("  ⚠ Regex extraction returned empty stack. Using hardcoded skills.")
                stack_tecnico = [
                    'React', 'Next.js', 'React Native', 'Node.js', 'Python', 
                    'Ruby on Rails', 'Go', 'AWS', 'OpenAI', 'LangChain', 
                    'TypeScript', 'SQL'
                ]
            
            if not palavras_chave:
                palavras_chave = stack_tecnico.copy()
            
            if not senioridade_pretendida:
                senioridade_pretendida = 'pleno'
            
            return ResumeData(
                stack_tecnico=stack_tecnico,
                experiencia_anos=experiencia_anos if experiencia_anos > 0 else 3,
                senioridade_pretendida=senioridade_pretendida,
                palavras_chave=palavras_chave
            )
        except Exception as e:
            print(f"  ⚠ Regex extraction failed: {e}. Using hardcoded skills as ultimate fallback.")
            # Ultimate fallback: return hardcoded skills to prevent empty resume
            hardcoded_skills = [
                'React', 'Next.js', 'React Native', 'Node.js', 'Python', 
                'Ruby on Rails', 'Go', 'AWS', 'OpenAI', 'LangChain', 
                'TypeScript', 'SQL'
            ]
            return ResumeData(
                stack_tecnico=hardcoded_skills,
                experiencia_anos=3,
                senioridade_pretendida='pleno',
                palavras_chave=hardcoded_skills + ['Backend', 'Full Stack', 'API', 'REST', 'Automation']
            )
    
    def extract_skills_with_ai(self, text: str) -> List[str]:
        """
        Extract ONLY technical skills from text using AI (Gemini/Groq via SmartAI).
        Focused prompt for skill extraction only.
        """
        if not self.use_ai or not self.brain:
            return []
        
        try:
            # Use SmartAI handler from brain (which has fallback support)
            smart_ai = self.brain.smart_ai
            
            prompt = f"""Analyze this resume text and extract ONLY the hard technical skills (programming languages, frameworks, tools, technologies).

Return ONLY a JSON array of skills, like this:
["Python", "React", "PostgreSQL", "Docker"]

Resume text:
{text[:6000]}

Extract all technical skills mentioned. Return ONLY the JSON array, no explanations, no markdown."""
            
            response = smart_ai.generate_content(prompt)
            
            # Try to parse JSON from response
            import json
            # Remove markdown if present
            response_clean = response.strip()
            if response_clean.startswith('```'):
                response_clean = re.sub(r'^```(?:json)?\s*', '', response_clean)
                response_clean = re.sub(r'\s*```$', '', response_clean)
            
            # Try to extract JSON array
            json_match = re.search(r'\[.*?\]', response_clean, re.DOTALL)
            if json_match:
                skills = json.loads(json_match.group(0))
                if isinstance(skills, list) and len(skills) > 0:
                    print(f"  ✓ AI extracted {len(skills)} technical skills")
                    return skills
            
            # Try parsing entire response as JSON
            try:
                skills = json.loads(response_clean)
                if isinstance(skills, list):
                    return skills
                elif isinstance(skills, dict) and 'skills' in skills:
                    return skills['skills']
            except:
                pass
            
            return []
                    
        except Exception as e:
            print(f"  ⚠ AI skill extraction failed: {e}")
            return []
    
    def parse(self) -> ResumeData:
        """
        Main parsing method with new strategy:
        1. Extract and clean text from PDF
        2. Inject fixed metadata (8 years, senior)
        3. Use AI ONLY for skill extraction
        4. Validate and return ResumeData
        """
        print("Using structured extraction strategy...")
        
        # Step 1: Extract and clean text
        self.extract_text()
        self.clean_text()
        
        # Step 2: Inject fixed metadata (user confirmed: 8 years, senior)
        resume_data = {
            'experiencia_anos': self.FIXED_EXPERIENCE_YEARS,
            'senioridade_pretendida': self.FIXED_SENIORITY,
            'stack_tecnico': [],
            'palavras_chave': []
        }
        
        print(f"  ✓ Injected fixed metadata: {resume_data['experiencia_anos']} years, {resume_data['senioridade_pretendida']}")
        
        # Step 3: Extract skills using AI (focused prompt)
        if self.use_ai and self.brain:
            try:
                print("  Extracting technical skills with AI...")
                skills = self.extract_skills_with_ai(self.cleaned_text)
                if skills:
                    resume_data['stack_tecnico'] = skills
                    resume_data['palavras_chave'] = skills.copy()  # Use skills as keywords
                    print(f"  ✓ AI extracted {len(skills)} skills: {', '.join(skills[:5])}...")
                else:
                    # Fallback to regex if AI returns empty
                    print("  ⚠ AI returned no skills. Using regex fallback...")
                    resume_data['stack_tecnico'] = self.extract_technical_stack()
                    resume_data['palavras_chave'] = self.extract_keywords()
            except Exception as e:
                error_str = str(e).lower()
                is_429 = '429' in error_str or 'quota' in error_str or 'rate limit' in error_str
                
                if is_429:
                    print(f"  ⚠ AI Quota Exceeded. Using regex fallback for skills...")
                else:
                    print(f"  ⚠ AI failed: {e}. Using regex fallback for skills...")
                
                # Fallback to regex
                resume_data['stack_tecnico'] = self.extract_technical_stack()
                resume_data['palavras_chave'] = self.extract_keywords()
        else:
            # No AI available, use regex
            print("  Using regex-based skill extraction...")
            resume_data['stack_tecnico'] = self.extract_technical_stack()
            resume_data['palavras_chave'] = self.extract_keywords()
        
        # Step 4: Validation - ensure we have skills
        # HARDCODED SKILLS: Fallback de segurança para garantir que o robô sempre pesquise
        # mesmo se a IA falhar (erro 429) ou regex retornar vazio
        HARDCODED_SKILLS = [
            'React', 'Next.js', 'React Native', 'Node.js', 'Python', 
            'Ruby on Rails', 'Go', 'AWS', 'OpenAI', 'LangChain', 
            'TypeScript', 'SQL'
        ]
        
        if not resume_data['stack_tecnico']:
            print("  ⚠ No skills found. Using hardcoded skills as fallback...")
            resume_data['stack_tecnico'] = HARDCODED_SKILLS.copy()
            resume_data['palavras_chave'] = HARDCODED_SKILLS.copy()
        else:
            # Merge hardcoded skills with extracted skills (ensure key skills are always present)
            # Add hardcoded skills that are not already in the list
            existing_lower = [s.lower() for s in resume_data['stack_tecnico']]
            for skill in HARDCODED_SKILLS:
                if skill.lower() not in existing_lower:
                    resume_data['stack_tecnico'].append(skill)
                    print(f"  ✓ Added hardcoded skill: {skill}")
        
        # Step 5: Create and return ResumeData
        result = ResumeData(
            stack_tecnico=resume_data['stack_tecnico'],
            experiencia_anos=resume_data['experiencia_anos'],
            senioridade_pretendida=resume_data['senioridade_pretendida'],
            palavras_chave=resume_data['palavras_chave']
        )
        
        print(f"\n  ✓ Resume data extracted:")
        print(f"    - Skills: {len(result.stack_tecnico)} technologies")
        print(f"    - Experience: {result.experiencia_anos} years")
        print(f"    - Seniority: {result.senioridade_pretendida}")
        
        return result


if __name__ == "__main__":
    # Test the parser
    parser = ResumeParser("curriculo.pdf")
    data = parser.parse()
    print(data.model_dump_json(indent=2))

