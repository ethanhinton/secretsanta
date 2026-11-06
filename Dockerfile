# Secret Santa — self-hostable image.
#
#   docker build -t secretsanta .
#   docker run -d --name secretsanta -p 8000:8000 -v secretsanta-data:/data secretsanta
#
# Then open http://localhost:8000.
#
# Notes:
# - The *published* host port must be 8000 (match -p 8000:8000), because
#   the Google OAuth callback redirects the browser to
#   http://localhost:8000/auth/gmail/callback.
# - state.json + tokens.json live in /data — mount a volume there so the
#   Gmail authorisation and the draw survive container recreation.
# - To use your own OAuth client instead of the bundled one:
#   -e GMAIL_OAUTH_CLIENT_ID=<your-desktop-client-id>
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    SANTA_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .

VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "run.py"]
