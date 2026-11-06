"""Entry point.

    python run.py

Then open http://127.0.0.1:8000

Host and port come from the HOST / PORT environment variables (see
app/config.py). In Docker, HOST is 0.0.0.0 and PORT must match the
*published* host port, because the Google OAuth callback redirects the
user's browser to http://localhost:<PORT>/auth/gmail/callback.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
