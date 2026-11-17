FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENTFLOW_HOST=0.0.0.0 \
    AGENTFLOW_PORT=8080 \
    AGENTFLOW_DATA_DIR=/app/data \
    HOME=/tmp
RUN mkdir -p /app/data \
    && chown -R 10001:10001 /app
COPY --chown=10001:10001 backend/src ./src
COPY --chown=10001:10001 frontend ./frontend
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "agentflow.api"]
