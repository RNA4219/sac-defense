FROM python:3.12-slim
WORKDIR /app
COPY ghostwall /app/ghostwall
USER 65532:65532
EXPOSE 4319 4320
ENTRYPOINT ["python", "-m", "ghostwall"]
