"""
celery_app.py — Celery factory for GRPS Weight.

Usage
-----
In app.py, after Flask app creation:

    from celery_app import make_celery
    celery = make_celery(app)

Start the worker (development):

    celery -A app.celery worker --loglevel=info --concurrency=2

Start the worker (production via Procfile/render.yaml):

    celery -A app.celery worker --loglevel=warning --concurrency=2 --max-tasks-per-child=50

Environment variables required
-------------------------------
REDIS_URL   – Redis connection string, e.g. redis://localhost:6379/0
              (Render injects this automatically when a Redis service is linked)
"""

from celery import Celery


def make_celery(app) -> Celery:
    """
    Create and configure a Celery instance tied to the given Flask app.

    Every task runs inside a Flask application context so that any code that
    touches ``current_app``, ``g``, or Flask-SQLAlchemy works as expected.
    """
    redis_url = app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0")

    celery = Celery(
        app.import_name,
        broker=redis_url,
        backend=redis_url,
    )

    # Sensible production defaults.
    celery.conf.update(
        # Use JSON everywhere — no pickle, no security surprises.
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Keep results for 2 hours (matches the grps_jobs cleanup window).
        result_expires=7200,
        # Do not store successful task results in Redis beyond what the app
        # already persists to Postgres; avoids unbounded Redis memory growth.
        task_ignore_result=False,
        # Reconnect gracefully if Redis restarts.
        broker_connection_retry_on_startup=True,
        # Visibility timeout must exceed the longest possible optimization run.
        # ALNS on 80+ customers can take several minutes; 30 min is safe.
        broker_transport_options={"visibility_timeout": 1800},
    )

    # Wrap every task so it has a Flask app context.
    class ContextTask(celery.Task):  # type: ignore[misc]
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask  # type: ignore[assignment]
    return celery
