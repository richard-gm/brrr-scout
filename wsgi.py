"""Production WSGI entry point.

Local dev:    python wsgi.py
Docker:       CMD ["python", "wsgi.py"]
Gunicorn:     gunicorn wsgi:app
"""
from brrr_scout import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
