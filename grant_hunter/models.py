from pydantic import BaseModel, Field
from typing import List, Optional

class BusinessProfile(BaseModel):
    business_name: str
    location: str = Field(..., description="City, State, ZIP – critical for local/state grants")
    industry_sector: str
    employee_count: int
    annual_revenue: Optional[float] = None
    ownership_type: List[str] = Field(default_factory=list, description="e.g. woman-owned, veteran, minority, rural, etc.")
    mission_focus: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)

class GrantOpportunity(BaseModel):
    title: str
    funder: str
    amount: str
    deadline: Optional[str]
    eligibility_summary: str
    match_score: int = Field(..., ge=0, le=100)
    official_url: str
    source: str  # "Federal (Grants.gov)", "State (CO)", "NGO", etc.