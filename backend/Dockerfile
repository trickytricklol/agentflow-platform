FROM python:3.11-slim
WORKDIR /app
COPY src ./src
ENV PYTHONPATH=/app/src \
    AGENTFLOW_HOST=0.0.0.0 \
    AGENTFLOW_PORT=8080 \
    AGENTFLOW_DATA_DIR=/app/data
RUN mkdir -p /app/data
EXPOSE 8080
CMD ["python", "-m", "agentflow.api"]
