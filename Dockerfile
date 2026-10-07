FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app.py .

RUN mkdir -p /data

USER 65532:65532

EXPOSE 8080

CMD ["python", "/app/app.py"]
