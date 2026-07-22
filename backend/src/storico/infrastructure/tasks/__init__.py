"""Background task utilities for Storico.

Replaces the previous Celery-based approach with a simple
``asyncio.create_task`` pattern.  No Redis, no worker process — just
an async function that runs in the same event loop as the web server.

Run the API server normally — background tasks are launched inline::

    uvicorn storico.api.app:create_app --factory
"""
