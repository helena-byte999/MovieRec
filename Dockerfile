FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY flask_app.py .
COPY static/ static/
COPY templates/ templates/

# Data files (movie_list.pkl + similarity.pkl) are mounted at runtime
# via docker run -v — they are too large to bake into the image

EXPOSE 5000

# Use gunicorn in production (4 workers, 120s timeout for large pkl load)
CMD ["sh", "-c", "gunicorn --workers 2 --timeout 120 --bind 0.0.0.0:${PORT:-5000} flask_app:app"]
