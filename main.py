from google.adk import run_agent
from grant_hunter.agent import GrantHunterOrchestrator

if __name__ == "__main__":
    agent = GrantHunterOrchestrator()
    run_agent(agent)