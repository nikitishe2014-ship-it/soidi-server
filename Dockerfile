FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y libasound2-dev && rm -rf /var/lib/apt/lists/*
EXPOSE 32766
CMD ["python", "server.py"]
