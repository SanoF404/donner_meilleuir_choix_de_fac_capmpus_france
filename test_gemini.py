

import os
from dotenv import load_dotenv
from google import genai

# Charger la clé depuis le fichier .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERREUR : clé GEMINI_API_KEY introuvable dans .env")
else:
    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents="Réponds simplement : Connexion Gemini réussie !"
        )

        print("SUCCÈS : Gemini répond correctement.")
        print(response.text)

    except Exception as error:
        print("Échec de la connexion Gemini.")
        print("Type d'erreur :", type(error).__name__)
        print("Détail :", error)
