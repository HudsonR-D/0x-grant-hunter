 # 0xGrantHunter

Full ADK agent for non-dilutive funding discovery.

## Local Run
pip install -r requirements.txt
python main.py

## GCP Deployment
1. terraform apply
2. gcloud builds submit --config cloudbuild.yaml .

Public URL will be in Terraform output.

For hackathon: rapid-agent.devpost.com