"""
Real tools for the GrantHunterOrchestrator.

- web_search_for_grants: "web research" entrypoint (replace body with real search API in prod)
- extract_grant_opportunities: Gemini structured output directly into GrantOpportunity Pydantic models
- persist_profile / persist_grant: save to Mongo (granthunter DB)
- search_grants_in_db: query persisted grants
"""

import os
from typing import List

import google.generativeai as genai
from pydantic import BaseModel

from .config import get_genai_key, load_secrets
from .models import BusinessProfile, GrantOpportunity
from .mongo import profiles_collection, grants_collection


# --- Gemini structured output setup (called lazily) ---
_structured_model = None

def _get_structured_model():
    global _structured_model
    if _structured_model is None:
        load_secrets()
        genai.configure(api_key=get_genai_key())
        # We use a dedicated model instance configured for JSON / Pydantic output
        _structured_model = genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config={
                "response_mime_type": "application/json",
                # response_schema can be used with newer SDKs; we fall back to instruction + parse
            },
        )
    return _structured_model


# --- TOOLS ---

def web_search_for_grants(profile: BusinessProfile) -> str:
    """
    Perform (simulated or real) web / knowledge search for current grant opportunities
    matching the business profile.

    HARDENING: This is the hook for real external search API integration.
    Recommended production integrations (add the API key to the Secret Manager JSON):
      - Tavily (great for agents)
      - Google Custom Search JSON API
      - Serper.dev / Bing Web Search
      - DuckDuckGo (via duckduckgo-search package)

    Example real implementation sketch (uncomment + add key):
    # import requests
    # api_key = os.getenv("TAVILY_API_KEY") or ...
    # resp = requests.post("https://api.tavily.com/search", json={"api_key": api_key, "query": query, "max_results": 8})
    # return resp.json()["results"]
    """
    load_secrets()

    # Basic spam / abuse protection (part of rate-limiting / input hardening)
    if len(profile.business_name) > 200 or len(profile.location) > 100:
        raise ValueError("Profile fields too long (possible abuse)")

    # For the hackathon / demo we return a high-quality prompt that the LLM (when this tool
    # is invoked by the agent) will expand using its knowledge + any built-in search.
    # The agent prompt tells the model to treat the return value as "live web results".
    research_prompt = f"""
Research current, real, non-dilutive funding opportunities (federal, state, foundation, corporate, 
local government, NGO) that are a good fit for this business:

Business: {profile.business_name}
Location: {profile.location}
Industry/Sector: {profile.industry_sector}
Employees: {profile.employee_count}
Annual Revenue: {profile.annual_revenue or 'unknown'}
Ownership: {', '.join(profile.ownership_type) if profile.ownership_type else 'general'}
Mission focus: {profile.mission_focus or 'general small business'}
Keywords: {', '.join(profile.keywords) if profile.keywords else 'none'}

Return a concise research report with:
- Specific open or recently announced grants (with titles, funders, approximate amounts, deadlines if known)
- Eligibility notes that match or conflict with the profile above
- Official URLs where possible
- Any special set-asides (woman-owned, veteran, rural, minority, etc.)

Focus on opportunities that are actually open or have upcoming deadlines in the next 6-12 months.
If you have live search capability, use it. Be specific and cite sources.
"""
    return research_prompt.strip()


def extract_grant_opportunities(research_notes: str, profile: BusinessProfile) -> List[GrantOpportunity]:
    """
    Use Gemini with structured output to turn research notes into a list of GrantOpportunity models.
    This is the "Gemini structured output into your GrantOpportunity model" tool.
    """
    model = _get_structured_model()

    # We ask for a JSON array of objects matching GrantOpportunity (minus match_score which we compute after)
    prompt = f"""
You are an expert grant analyst.

Given the following research notes about funding opportunities and the business profile below,
extract a list of the BEST matching grant opportunities.

Business Profile:
{profile.model_dump_json(indent=2)}

Research Notes:
{research_notes}

For each opportunity produce a JSON object with these exact fields (do not invent extra fields):
- title: string
- funder: string
- amount: string (e.g. "$50,000 - $250,000" or "$10,000")
- deadline: string or null (use YYYY-MM-DD if known, otherwise a human description like "rolling" or "Q3 2026")
- eligibility_summary: string (2-4 sentences, highlight fit with the business profile)
- official_url: string (real URL if known, otherwise "https://example.com/grant" as placeholder)
- source: string (e.g. "Federal (Grants.gov)", "State (Colorado)", "Foundation", "NGO", "Corporate")

Return ONLY a JSON array of objects, no other text. Maximum 8 high-quality opportunities.
If the research notes are weak, still produce the best plausible opportunities you can based on the profile.
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # The model should return JSON because of response_mime_type
        import json
        data = json.loads(text)

        opportunities: List[GrantOpportunity] = []
        for item in data:
            # Compute a simple heuristic match score (0-100)
            score = _heuristic_match_score(item, profile)
            grant = GrantOpportunity(
                title=item.get("title", "Untitled Grant"),
                funder=item.get("funder", "Unknown Funder"),
                amount=item.get("amount", "Unknown"),
                deadline=item.get("deadline"),
                eligibility_summary=item.get("eligibility_summary", ""),
                match_score=score,
                official_url=item.get("official_url", "https://example.com"),
                source=item.get("source", "Research"),
            )
            opportunities.append(grant)

        return opportunities
    except Exception as e:
        # Fallback: return empty so the agent can still continue
        print(f"Warning: structured grant extraction failed: {e}")
        return []


def _heuristic_match_score(grant_dict: dict, profile: BusinessProfile) -> int:
    """
    Improved heuristic scoring.
    HARDENING: For production, add a dedicated `llm_judge_score(grant, profile)` tool that
    calls Gemini with a structured prompt to return a calibrated 0-100 score + rationale.
    This can be called after extract_grant_opportunities for stronger, context-aware scoring.
    """
    score = 45
    text = " ".join([
        grant_dict.get("title", ""),
        grant_dict.get("eligibility_summary", ""),
        grant_dict.get("funder", "")
    ]).lower()

    loc = profile.location.lower()
    if loc and any(part in text for part in loc.split(",")):
        score += 18  # location is very important for grants

    for own in profile.ownership_type:
        if own.lower() in text:
            score += 14

    if profile.industry_sector.lower() in text:
        score += 12

    # Stronger keyword / mission boost
    for kw in (profile.keywords or []):
        if kw.lower() in text:
            score += 8

    if profile.mission_focus and profile.mission_focus.lower() in text:
        score += 10

    # Small penalty for very generic "small business" language if the profile is specific
    if "small business" in text and profile.industry_sector:
        score -= 3

    return max(0, min(100, score))


def persist_business_profile(profile: BusinessProfile) -> str:
    """Save or update a business profile in MongoDB."""
    col = profiles_collection()
    doc = profile.model_dump()
    result = col.update_one(
        {"business_name": profile.business_name, "location": profile.location},
        {"$set": doc},
        upsert=True
    )
    return f"Profile saved (upserted={result.upserted_id is not None}, matched={result.matched_count})"


def persist_grant_opportunity(grant: GrantOpportunity) -> str:
    """Save or update a grant opportunity. Dedupes on (title, funder)."""
    col = grants_collection()
    doc = grant.model_dump()
    result = col.update_one(
        {"title": grant.title, "funder": grant.funder},
        {"$set": doc},
        upsert=True
    )
    return f"Grant saved (upserted={result.upserted_id is not None})"


def search_grants_in_db(keywords: List[str] = None, location: str = None, min_score: int = 60, limit: int = 10) -> List[GrantOpportunity]:
    """Query previously discovered grants from the DB."""
    col = grants_collection()
    query = {}
    if min_score:
        query["match_score"] = {"$gte": min_score}
    if location:
        query["$or"] = [
            {"eligibility_summary": {"$regex": location, "$options": "i"}},
            {"title": {"$regex": location, "$options": "i"}},
        ]
    if keywords:
        # simple OR on any keyword in title or summary
        or_clauses = []
        for kw in keywords:
            or_clauses.append({"title": {"$regex": kw, "$options": "i"}})
            or_clauses.append({"eligibility_summary": {"$regex": kw, "$options": "i"}})
        query["$or"] = or_clauses

    docs = col.find(query).sort("match_score", -1).limit(limit)
    return [GrantOpportunity(**d) for d in docs]
