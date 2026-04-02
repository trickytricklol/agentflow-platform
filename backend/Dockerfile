FROM python:3.11-slim
WORKDIR /app
COPY src ./src
ENV PYTHONPATH=/app/src
EXPOSE 8080
CMD ["python", "-m", "agentflow.api"]
