web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60
worker: celery -A tasks worker --loglevel=info --concurrency=2
