"""Root application entry point forwarding to app.main:app.

Allows running both:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
and
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn
    from app.core.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
