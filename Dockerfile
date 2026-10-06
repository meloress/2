FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mafia_zone ./mafia_zone
COPY kun.mp4 tun.mp4 ./
CMD ["python", "-m", "mafia_zone"]
