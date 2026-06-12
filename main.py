from grant_hunter.config import load_secrets
from google.adk import run_agent
from grant_hunter.agent import GrantHunterOrchestrator

if __name__ == "__main__":
    load_secrets()  # populate env from .env or mounted Secret Manager before anything else
    agent = GrantHunterOrchestrator()
    run_agent(agent)