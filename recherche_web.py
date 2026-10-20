from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

DOSSIER = Path(__file__).resolve().parent
FICHIER_SORTIE = DOSSIER / "resultats_recherche.xlsx"

MOTS_CLES = {
    "Prérequis académiques": [
        "prérequis", "prerequis", "conditions d'admission",
        "conditions d'accès", "diplôme requis", "licence requise"
    ],
    "Niveau de français": [
        "niveau de français", "niveau de langue",
        "tcf", "delf", "dalf", "b2", "c1"
    ],
    "Frais de scolarité": [
        "frais de scolarité", "droits d'inscription",
        "droits différenciés", "tarifs"
    ],
    "Modalités de candidature": [
        "candidature", "mon master", "e-candidat",
        "études en france", "étudiants internationaux"
    ],
    "Documents demandés": [
        "pièces justificatives", "documents à fournir",
        "relevés de notes", "lettre de motivation", "curriculum vitae"
    ],
    "Alternance": [
        "alternance", "apprentissage", "contrat d'apprentissage"
    ],
}

ETABLISSEMENTS_PRIVES = [
    "epitech", "epita", "esiea", "efrei", "esilv",
    "ynov", "supinfo", "guardia", "hetic"
]


def determiner_type(titre, url):
    domaine = urlparse(url).netloc.lower()
    texte = f"{titre} {domaine}".lower()

    if any(nom in texte for nom in ETABLISSEMENTS_PRIVES):
        return "Privé (à confirmer)"

    indices_publics = (
        "univ-", "universite", "université",
        "sorbonne-universite", "u-paris.fr",
        "enseignementsup-recherche.gouv.fr",
        "ip-paris.fr", "ensicaen.fr"
    )

    if any(indice in texte for indice in indices_publics):
        return "Public probable"

    return "À vérifier"


def extraire_page(url):
    try:
        reponse = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 CampusFranceAdvisor/1.0"}
        )
        reponse.raise_for_status()

        soup = BeautifulSoup(reponse.content, "html.parser")

        for element in soup([
            "script", "style", "nav", "footer", "header", "noscript"
        ]):
            element.decompose()

        titre = soup.title.get_text(" ", strip=True) if soup.title else ""
        paragraphes = [
            p.get_text(" ", strip=True)
            for p in soup.find_all(["p", "li"])
        ]
        texte = " ".join(p for p in paragraphes if p)
        texte = re.sub(r"\s+", " ", texte)

        return titre, texte[:60000]

    except Exception:
        return "", ""


def trouver_extraits(texte, mots):
    if not texte:
        return "Non trouvé automatiquement"

    phrases = re.split(r"(?<=[.!?])\s+|\n+", texte)
    extraits = []

    for phrase in phrases:
        phrase = phrase.strip()
        if len(phrase) < 20:
            continue

        if any(mot in phrase.lower() for mot in mots):
            if phrase not in extraits:
                extraits.append(phrase[:400])

        if len(extraits) >= 3:
            break

    if not extraits:
        return "Non trouvé automatiquement"

    return " | ".join(extraits)


def rechercher(formation, niveau, type_souhaite):
    requetes = [
        f'"{formation}" {niveau} France formation admission',
        f'"{formation}" {niveau} France prérequis frais de scolarité',
        f'"{formation}" {niveau} université école candidature internationale',
    ]

    resultats = []
    urls_vues = set()

    for requete in requetes:
        print(f"\nRecherche : {requete}")

        try:
            with DDGS() as moteur:
                pages = list(moteur.text(requete, max_results=8))
        except Exception as erreur:
            print(f"Recherche impossible : {erreur}")
            continue

        for page in pages:
            url = page.get("href", "").strip()
            titre = page.get("title", "").strip()
            resume = page.get("body", "").strip()

            if not url.startswith("http") or url in urls_vues:
                continue

            urls_vues.add(url)

            titre_page, contenu = extraire_page(url)
            if titre_page:
                titre = titre_page

            statut = determiner_type(titre, url)

            # Ne pas prétendre connaître le statut d'un établissement
            # lorsque les indices disponibles sont insuffisants.
            if type_souhaite == "Public" and not statut.startswith("Public"):
                continue
            if type_souhaite == "Privé" and not statut.startswith("Privé"):
                continue

            ligne = {
                "Formation recherchée": formation,
                "Niveau recherché": niveau,
                "Titre": titre,
                "Type d'établissement estimé": statut,
                "URL": url,
                "Résumé du moteur de recherche": resume,
            }

            for nom, mots in MOTS_CLES.items():
                ligne[nom] = trouver_extraits(contenu, mots)

            ligne["Vérification humaine"] = "À vérifier"
            ligne["Date de collecte"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            resultats.append(ligne)

            print(f"  Trouvé : {titre[:90]}")
            time.sleep(0.3)

    colonnes = [
        "Formation recherchée", "Niveau recherché", "Titre",
        "Type d'établissement estimé", "URL",
        "Résumé du moteur de recherche",
        *MOTS_CLES.keys(),
        "Vérification humaine", "Date de collecte"
    ]

    tableau = pd.DataFrame(resultats, columns=colonnes)

    if not tableau.empty:
        tableau = tableau.drop_duplicates(subset=["URL"])
        tableau.to_excel(FICHIER_SORTIE, index=False)
        print(f"\n{len(tableau)} résultats enregistrés dans : {FICHIER_SORTIE}")
    else:
        print("\nAucun résultat exploitable trouvé.")
        print("Essaie une autre formulation ou relance la recherche plus tard.")

    return tableau


if __name__ == "__main__":
    print("=== Campus France Advisor : recherche généraliste ===")

    formation = input("Formation recherchée (ex. Cybersécurité, Data Science) : ").strip()
    niveau = input("Niveau (BTS/BUT, Licence, Master, Doctorat...) : ").strip()
    type_souhaite = input("Type d'établissement (Public, Privé, Tous) : ").strip().capitalize()

    if not formation or not niveau:
        print("La formation et le niveau sont obligatoires.")
    elif type_souhaite not in ["Public", "Privé", "Tous"]:
        print("Type invalide. Saisis Public, Privé ou Tous.")
    else:
        rechercher(formation, niveau, type_souhaite)
