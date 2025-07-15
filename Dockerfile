# Utiliser une image officielle Python 3.10
FROM python:3.10-slim

# Créer un dossier de travail
WORKDIR /app

# Copier tous les fichiers dans le conteneur
COPY . /app

# Installer les dépendances
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Lancer ton bot
CMD ["python", "main.py"]
