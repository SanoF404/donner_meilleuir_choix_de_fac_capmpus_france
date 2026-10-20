
import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()


def generer_reponse(question, formations, profil=None, historique=None):
    """Génère une réponse à partir du profil et des formations fournies."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Clé GEMINI_API_KEY introuvable. Vérifie le fichier .env."
        )

    client = genai.Client(api_key=api_key)

    # Ne transmettre que les champs utiles à l'orientation.
    champs_profil = [
        "formation", "niveau", "type", "niveau_actuel", "diplome",
        "specialite", "villes_preferees", "modalite", "rentree",
        "budget", "moyenne_l1", "moyenne_l2", "moyenne_l3",
        "moyenne_s1", "moyenne_generale", "notes", "echelle_notes",
        "certifications", "competences", "francais", "anglais",
        "autres_langues"
    ]

    profil = profil or {}
    profil_filtre = {
        cle: profil[cle]
        for cle in champs_profil
        if cle in profil and profil[cle] not in (None, "")
    }

    # Limiter les données transmises à Gemini.
    colonnes_utiles = [
        "Titre", "Domaine", "Niveau détecté", "Type détecté",
        "Recherche", "Résumé", "URL", "Prérequis académiques",
        "Niveau de français", "Frais de scolarité",
        "Modalités de candidature", "Alternance", "Rentrée",
        "TCF B2 accepté", "Vérification humaine"
    ]
    colonnes = [c for c in colonnes_utiles if c in formations.columns]
    catalogue = formations[colonnes].head(12).fillna("").to_dict(
        orient="records"
    )

    contexte = {
        "profil_etudiant": profil_filtre,
        "formations_du_catalogue": catalogue,
        "historique_recent": (historique or [])[-8:]
    }

    instructions = """
Tu es Campus France Advisor, un assistant d'orientation pour les études
supérieures en France.

RÈGLES OBLIGATOIRES :
- Réponds en français, clairement, avec des explications accessibles.
- Utilise le profil et les données de formations fournis.
- N'invente jamais une formation, une URL, un prérequis, des frais,
  une date, une exigence de langue ou une règle d'admission.
- Les informations absentes doivent être signalées comme « à vérifier
  sur le site officiel ».
- Cite les liens officiels présents dans les données, sans en inventer.
- Distingue les faits fournis des conseils et des points à vérifier.
- Une pertinence ou un classement n'est pas une probabilité d'admission.
- Ne garantis jamais une admission.
- Si les données sont insuffisantes, dis-le et pose une question utile.
- Ne présente pas le catalogue fourni comme exhaustif.
- Ne répète pas inutilement les informations personnelles de l'étudiant.
- Pour les recommandations, explique pourquoi chaque formation correspond
  au profil et indique aussi les incertitudes importantes.
"""

    prompt = (
        instructions
        + "\n\nCONTEXTE DISPONIBLE :\n"
        + json.dumps(contexte, ensure_ascii=False, default=str)
        + "\n\nQUESTION DE L'ÉTUDIANT :\n"
        + question
    )

    reponse = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt
    )

    texte_reponse = (reponse.text or "").strip()
    if not texte_reponse:
        raise RuntimeError("Gemini a renvoyé une réponse vide.")

    return texte_reponse
