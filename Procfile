web: gunicorn app:app --config gunicorn.conf.py --bind 0.0.0.0:$PORT
worker: celery -A app.celery worker --loglevel=info --concurrency=2 --max-tasks-per-child=50 --without-gossip --without-mingle
