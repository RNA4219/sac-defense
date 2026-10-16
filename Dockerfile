FROM python:3.12-slim
WORKDIR /app
COPY sac_defense /app/sac_defense
USER 65532:65532
EXPOSE 4319 4320
ENTRYPOINT ["python", "-m", "sac_defense"]
