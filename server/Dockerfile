FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies first (better layer caching)
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy models.py to /app so server/app.py can import it via sys.path
COPY models.py ./models.py

# Copy entire server directory (includes app.py + sql_query_review_environment.py)
COPY server/ ./server/

# HF Spaces requires a non-root user with uid=1000
RUN useradd -m -u 1000 user
USER user

# Environment defaults
ENV SQL_REVIEW_TASK=easy
ENV HOST=0.0.0.0
ENV PORT=7860
ENV WORKERS=2

WORKDIR /app/server

EXPOSE 7860

# JSON array form prevents shell-signal issues
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]