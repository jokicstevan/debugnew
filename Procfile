web: gunicorn app:app --workers 1 --worker-class gthread --threads 4 --timeout 900 --graceful-timeout 30 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:${PORT:-5000}
