# Image de production de Planning Assistantes (Espace K Dentaire).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic doit pouvoir importer les reglages, qui exigent une cle secrete.
# Cette valeur sert UNIQUEMENT au build : elle ne signe rien, n'est jamais
# utilisee a l'execution, et n'est donc pas un secret.
RUN DJANGO_SECRET_KEY=build-only-not-a-secret \
    DJANGO_DEBUG=0 \
    python manage.py collectstatic --noinput

# Forme shell volontaire : $PORT est fourni par Railway et doit etre developpe.
CMD gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60
