"""
Shared Data Models
Avoids circular imports by centralizing common models
"""
from pydantic import BaseModel, Field
from typing import Optional, Union, Any


class JobListing(BaseModel):
    """Job listing data model"""
    title: str
    company: str
    location: str = ""
    url: str
    posted_date: Optional[Union[str, int, None]] = None  # Accepts string, int, or None (for Arbeitnow API)
    description: str = ""
    match_score: float = Field(default=0.0, description="Match score based on resume")
    email: Optional[str] = Field(default=None, description="Contact email extracted from job posting")
    source: Optional[str] = Field(default=None, description="Job source (e.g., 'github_br', 'hackernews', 'remoteok', 'linkedin_post')")
    language: Optional[str] = Field(default=None, description="Language of job posting ('pt' or 'en')")
    external_links: Optional[list] = Field(default=None, description="External application links found in post")
    search_skill: Optional[str] = Field(default=None, description="Technology/skill used to find this job (for personalized cover letters)")
    job_code: Optional[str] = Field(default=None, description="Recruiter job identification code extracted from post (e.g. 'ENGFULLJAVA - 01')")

