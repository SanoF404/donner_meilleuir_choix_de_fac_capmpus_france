from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

DOSSIER = Path(__file__).resolve().parent
SORTIE = DOSSIER / "preuves_formations.xlsx"

ENTETES = {
    "User-Agent": "CampusFranceAdvisor/0.1 (educational research)"
}

THEMES = {
    "Prérequis académiques": [
        "prérequis", "prerequis", "conditions d'admission",
        "conditions d'accès", "diplôme requis", "licence",
        "admission en master", "candidats titulaires"
    ],
    "Niveau de français": [
        "niveau de français", "niveau de langue",
        "tcf", "delf", "dalf", "b2", "c1",
        "français langue"
    ],
    "Prérequis techniques": [
        "programmation", "algorithmique", "réseaux",
        "systèmes", "compétences informatiques",
        "connaissances recommandées"
    ],
    "Frais de scolarité": [
        "droits d'inscription", "frais de scolarité",
        "droits différenciés", "exonération",
        "étudiants internationaux", "tarifs"
    ],
    "Modalités de candidature": [
        "candidater", "candidature", "mon master",
        "études en france", "date limite",
        "calendrier de candidature"
    ],
    "Documents demandés": [
        "pièces justificatives", "relevés de notes",
        "lettre de motivation", "dossier de candidature",
        "documents à fournir", "diplôme"
    ],
    "Alternance": [
        "alternance", "apprentissage", "contrat d'apprentissage",
        "formation continue", "formation initiale"
    ],
}


def est_domaine_institutionnel(url):
    domaine = urlparse(url).netloc.lower().split(":")[0]
    return (
        domaine.endswith(".fr")
        and not any(
            terme in domaine
            for terme in [
                "wikipedia", "youtube", "facebook",
                "linkedin", "instagram", "tiktok"
            ]
        )
    )


def autorise_par_robots(url):
    """Vérifie robots.txt avant de tenter de télécharger une page."""
    parties = urlparse(url)
    robots_url = f"{parties.scheme}://{parties.netloc}/robots.txt"

    robot = RobotFileParser()
    robot.set_url(robots_url)

    try:
        reponse = requests.get(
            robots_url,
            headers=ENTETES,
            timeout=8
        )

        if reponse.status_code == 404:
            return True

        reponse.raise_for_status()
        robot.parse(reponse.text.splitlines())
        return robot.can_fetch(ENTETES["User-Agent"], url)

    except requests.RequestException:
        # En cas de doute, ne pas télécharger la page.
        return False


def chercher_pages(formation, niveau, maximum=8):
    requetes = [
        f'"{formation}" {niveau} site:univ.fr admission',
        f'"{formation}" {niveau} université programme officiel',
        f'"{formation}" {niveau} conditions candidature frais',
        f'"{formation}" alternance niveau français université'
    ]

    resultats = []
    urls_vues = set()

   
    with DDGS() as recherche:
        for requete in requetes:
            try:
                pages = recherche.text(
                    requete,
                    region="fr-fr",
                    max_results=maximum
                )

                for page in pages or []:
                    url = page.get("href", "")
                    if not url.startswith("https://"):
                        continue
                    if url in urls_vues:
                        continue

                    urls_vues.add(url)
                    resultats.append({
                        "Formation recherchée": formation,
                        "Niveau recherché": niveau,
                        "Titre de la page": page.get("title", ""),
                        "URL source": url,
                        "Domaine .fr": est_domaine_institutionnel(url),
                        "Extrait du moteur de recherche": page.get("body", ""),
                        "Page téléchargée": False,
                        "Texte extrait": "",
                        "Date de collecte": datetime.now().isoformat(
                            timespec="seconds"
                        )
                    })

                time.sleep(1)

            except Exception as erreur:
                print(f"Recherche partiellement échouée : {erreur}")

    return resultats



def extraire_page(url):
    if not est_domaine_institutionnel(url):
        return "", "Domaine non institutionnel .fr : téléchargement ignoré"

    if not autorise_par_robots(url):
        return "", "Téléchargement non effectué : accès non autorisé ou robots.txt inaccessible"

    try:
        reponse = requests.get(
            url,
            headers=ENTETES,
            timeout=12
        )
        reponse.raise_for_status()

        type_contenu = reponse.headers.get("Content-Type", "").lower()
        if "text/html" not in type_contenu:
            return "", "La ressource n'est pas une page HTML"

        soup = BeautifulSoup(reponse.text, "html.parser")

        for element in soup([
            "script", "style", "nav", "footer",
            "header", "noscript", "svg"
        ]):
            element.decompose()

        texte_page = " ".join(soup.stripped_strings)
        return texte_page[:30000], "Page téléchargée"

    except requests.RequestException as erreur:
        return "", f"Erreur de téléchargement : {erreur}"


def trouver_preuves(texte_page):
    preuves = {}

    texte_page = " ".join(texte_page.split())
    texte_bas = texte_page.lower()

    for theme, mots_cles in THEMES.items():
        extraits = []

        for mot in mots_cles:
            position = texte_bas.find(mot.lower())

            if position >= 0:
                debut = max(0, position - 180)
                fin = min(len(texte_page), position + 420)
                extrait = texte_page[debut:fin].strip()

                if extrait and extrait not in extraits:
                    extraits.append(extrait)

            if len(extraits) >= 3:
                break

        preuves[theme] = " | ".join(extraits)

    return preuves


def main():
    print("\n=== Campus France Advisor : moteur de recherche ===\n")

    formation = input(
        "Formation recherchée (ex. Master Cybersécurité) : "
    ).strip()

    if not formation:
        print("La formation recherchée est obligatoire.")
        return

    niveau = input(
        "Niveau (BTS/BUT, Licence, Master, Doctorat) : "
    ).strip()

    if not niveau:
        niveau = "Master"

    print("\nRecherche de pages...")
    pages = chercher_pages(formation, niveau)

    if not pages:
        print("Aucune page trouvée. Vérifie ta connexion et réessaie.")
        return

    print(f"{len(pages)} pages candidates trouvées.")

    lignes = []

    for index, page in enumerate(pages, start=1):
        print(f"\n[{index}/{len(pages)}] {page['Titre de la page']}")
        print(page["URL source"])

        texte_page, statut = extraire_page(page["URL source"])
        page["Page téléchargée"] = bool(texte_page)
        page["Statut extraction"] = statut
        page["Texte extrait"] = texte_page

        preuves = trouver_preuves(texte_page)

        for theme, extrait in preuves.items():
            page[f"Preuve - {theme}"] = extrait
            page[f"Statut - {theme}"] = (
                "Extrait trouvé - à vérifier"
                if extrait
                else "Aucune preuve trouvée sur cette page"
            )

        lignes.append(page)
        time.sleep(1)

    tableau = pd.DataFrame(lignes)

    # Crée un fichier séparé : ne remplace pas les fichiers existants.
    if SORTIE.exists():
        precedent = pd.read_excel(SORTIE)
        tableau = pd.concat(
            [precedent, tableau],
            ignore_index=True
        )
        tableau = tableau.drop_duplicates(
            subset=["URL source", "Formation recherchée"],
            keep="last"
        )

    tableau.to_excel(SORTIE, index=False)

    print("\nRecherche terminée.")
    print(f"Résultats enregistrés dans : {SORTIE}")
    print(
        "Important : les extraits sont des pistes documentaires, "
        "pas des conditions d'admission automatiquement confirmées."
    )


if __name__ == "__main__":
    main()
