FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY protocol.py interviewer.py ./
# LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET and TTS_API_KEY come from the environment
CMD ["python", "interviewer.py", "start"]
