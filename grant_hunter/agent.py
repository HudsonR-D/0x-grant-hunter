"""
GrantHunterOrchestrator - ADK agent for non-dilutive funding discovery.

Uses MongoDB Atlas (granthunter DB) for persistence of profiles and discovered grants.
Real tools:
- web_search_for_grants (research)
- extract_grant_opportunities (Gemini structured output -> GrantOpportunity Pydantic)
- persist_* and search_grants_in_db (Mongo persistence + query)
"""

from google.adk import Agent

from .config import load_secrets
from .mongo import get_db, grants_collection, profiles_collection
from .models import BusinessProfile, GrantOpportunity
from .tools import (
    web_search_for_grants,
    extract_grant_opportunities,
    persist_business_profile,
    persist_grant_opportunity,
    search_grants_in_db,
)


class GrantHunterOrchestrator(Agent):
    def __init__(self):
        # Load secrets (env or mounted Secret Manager) as early as possible
        load_secrets()

        # Early DB connectivity + index creation
        _ = get_db()

        tools = [
            web_search_for_grants,
            extract_grant_opportunities,
            persist_business_profile,
            persist_grant_opportunity,
            search_grants_in_db,
        ]

        super().__init__(
            name="grant_hunter",
            model="gemini-2.0-flash",
            description="Expert researcher that finds, scores, and tracks non-dilutive funding (grants) for small businesses.",
            instruction=(
                "You are GrantHunter, a world-class expert at discovering non-dilutive funding opportunities "
                "(federal, state, foundation, corporate, local, NGO grants) for small businesses.\n\n"
                "Workflow you MUST follow:\n"
                "1. Understand the user's BusinessProfile in detail (location is critical for state/local grants).\n"
                "2. ALWAYS call web_search_for_grants(profile) first to get fresh research.\n"
                "3. Then call extract_grant_opportunities(research_notes, profile) to turn the research into "
                "   properly typed GrantOpportunity objects (this uses Gemini structured output).\n"
                "4. For each extracted grant, call persist_grant_opportunity(grant).\n"
                "5. Also call persist_business_profile(profile) so we remember the user.\n"
                "6. Use search_grants_in_db when the user wants to see previously discovered opportunities.\n\n"
                "Scoring & quality rules:\n"
                "- Be honest about fit. Use the match_score field (0-100).\n"
                "- Always include official_url when possible.\n"
                "- Respect deadlines and eligibility constraints.\n"
                "- Cite sources.\n"
                "- If research is weak, say so and suggest how the user can improve their profile.\n\n"
                "Output style: concise, actionable, list the top matches with scores and why they fit, then the URLs."
            ),
            tools=tools,
        )

    # Convenience methods (can also be called directly if needed outside tool use)
    def save_profile(self, profile: BusinessProfile):
        return persist_business_profile(profile)

    def save_grant(self, grant: GrantOpportunity):
        return persist_grant_opportunity(grant)

    def recent_grants(self, limit: int = 20):
        return search_grants_in_db(limit=limit)
