FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "-m", "google.adk.cli", "serve", "--agent", "grant_hunter.agent:GrantHunterOrchestrator"]