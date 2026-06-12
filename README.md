 # 0xGrantHunter

Full ADK agent for non-dilutive funding discovery (grants for small businesses).

## Atlas / MongoDB (current as of 2026-06-11)

- Org: HudsonR&D
- Project: 0xGrantHunter
- Cluster: 0xGrantHunter (FREE tier, GCP CENTRAL_US, MongoDB 8.0.26, IDLE)
- DB: `granthunter`
- App user: `granthunter-app` (readWrite on `granthunter`)
- Full URI (store only in .env + Secret Manager):

  `mongodb+srv://granthunter-app:<YOUR_PASSWORD>@0xgranthunter.gkpazno.mongodb.net/granthunter?retryWrites=true&w=majority`

**Security note:** 0.0.0.0/0 was added for the hackathon demo. Remove it via Atlas UI or MCP tools as soon as possible and restrict to your IPs + Cloud Run ranges.

The MCP (`mongodb` server) is configured with both the connection string (for data ops) and the temporary 24h owner SA (for admin tools). Use natural language in Grok sessions to query/insert via the MCP.

## Local Run
```bash
pip install -r requirements.txt
cp .env.example .env   # then fill real values
python main.py
```

## GCP Deployment - Final "Ready-to-Cut" with Custom Domain (granthunter.hudsonrnd.com)

This uses a **Global External HTTPS Load Balancer + Serverless NEG** (Google-managed SSL, A record DNS).

```bash
# 1. Terraform (full stack: LB, NEG, Cloud Run, Secret, Firestore, Artifact Registry, SA + IAM)
terraform init
terraform plan
terraform apply -auto-approve

# 2. Populate / update the secret (include agent deps if you want them in the JSON)
echo -n '{
  "GEMINI_API_KEY": "your-real-gemini-key",
  "MONGODB_ATLAS_URI": "mongodb+srv://granthunter-app:<YOUR_PASSWORD>@0xgranthunter.gkpazno.mongodb.net/granthunter?retryWrites=true&w=majority",
  "REVIEWER_AGENT_ENABLED": "true",
  "WRITER_AGENT_ENABLED": "true"
}' | gcloud secrets versions add granthunter-secrets --data-file=-

# 3. Build & push the container (Terraform owns the service + LB definition)
gcloud builds submit --config cloudbuild.yaml .

# After the image is pushed, re-apply Terraform (or run a targeted image update)
# so the Cloud Run revision picks up the new container while the LB stays stable.
terraform apply -auto-approve
```

**DNS Cutover (manual step after terraform apply):**
- Terraform output will show `load_balancer_ip`.
- In your DNS provider for hudsonrnd.com, create an **A record**:
  - Host: `granthunter`
  - Value: the `load_balancer_ip`
- Google will provision/validate the managed SSL cert for granthunter.hudsonrnd.com (can take a few minutes).
- Once the cert is ACTIVE, traffic will flow through the Global LB → Serverless NEG → Cloud Run multi-agent service.

Public LB URL after DNS propagation: https://granthunter.hudsonrnd.com

### Hardening Notes (applied in this iteration)
- Real external search API hook ready in `web_search_for_grants` (just drop in Tavily/Serper key).
- Stronger scoring heuristic + clear path for an LLM-judge tool.
- Rate limiting / abuse protection: input guards + dedup; for production put Cloud Armor in front of the Global LB (WAF, rate limits by IP/path).
- All previous security (secret mount, dedicated SA, least-privilege Mongo user, indexes, etc.) retained.

## Implemented
- Real tools (`grant_hunter/tools.py`):
  - `web_search_for_grants(profile)` (research entrypoint — swap in real search API easily)
  - `extract_grant_opportunities(...)` — Gemini structured output straight into your `GrantOpportunity` Pydantic model + scoring
  - Full persistence + DB search tools
- Agent fully wired with the tools + strict research → structured extract → persist workflow.
- `config.py` + `mongo.py`: secret loading (local .env or mounted Secret Manager JSON), automatic indexes (deadline, match_score, funder+score, text search, unique dedup).
- Terraform: dedicated SA + secretAccessor, secret volume mount so the app can read the JSON without code changes.
- .gitignore, .env.example, requirements, main.py, agent, etc. all updated for the new Mongo-first world.

## Atlas security & operations (via MCP — you have it connected)
- Indexes: created automatically on first `get_db()` (see `mongo.py:ensure_indexes`).
- Performance advisor: In your Grok session run: "Using the mongodb MCP, run atlas-get-performance-advisor on the 0xGrantHunter cluster and give me the top recommendations + slow queries."
- Additional users: "Create a read-only user granthunter-readonly with read role on the granthunter database."
- Rate limits / spam / security in app:
  - Field length guards in tools
  - Deduplication on (title + funder)
  - Secrets never logged or committed
  - Least-privilege DB user for the runtime app
  - Cloud Run uses dedicated SA that can *only* read the specific secret
- Critical: Remove the 0.0.0.0/0 access list entry as soon as the hackathon/demo is over (use MCP or Atlas UI).

## Next
- Swap the body of `web_search_for_grants` for a real paid/free search API (Tavily, Serper, etc.) + API key in the secret.
- Stronger scoring (add an LLM-as-judge tool that takes the extracted grants + profile and returns calibrated scores + rationale).
- If keeping the ADK HTTP server public long-term, add rate limiting / auth.
- (Optional) `atlas-upgrade-cluster` via MCP when you need more than free tier.