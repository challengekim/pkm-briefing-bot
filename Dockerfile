FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .
COPY . .
# NOTE: main.py runs a blocking APScheduler loop with no HTTP endpoint.
# WB4 (web dashboard) will add an HTTP health check server so Railway can
# probe service liveness. Until then, Railway relies on process uptime only.
EXPOSE 8080
CMD ["python", "-m", "compound_agent.main"]
