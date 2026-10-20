from urllib.parse import urlparse, urlunparse
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
SORTIE = DOSSIER / "preuves_formations_v2.xlsx"

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
    domaine = domaine.removeprefix("www.")
    marqueurs_officiels = (
        ".gouv.fr",
        "univ-",
        "univ.",
        "universite",
        "university",
        "unicaen",
        "ensicaen",
        "sorbonne",
        "dauphine",
        "cnam",
        "insa-",
        "polytech",
        "sciencespo",
        "univ-lorraine",
        "univ-tln",
    )
    return domaine.endswith(".fr") and any(
        marqueur in domaine for marqueur in marqueurs_officiels
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


def score_pertinence(titre, extrait, formation, niveau):
    import re
    import unicodedata

    def normaliser(texte):
        texte = unicodedata.normalize("NFD", texte.lower())
        texte = "".join(
            caractere
            for caractere in texte
            if unicodedata.category(caractere) != "Mn"
        )
        return re.sub(r"\s+", " ", texte).strip()

    contenu = normaliser(f"{titre} {extrait}")
    formation_norm = normaliser(formation)
    niveau_norm = normaliser(niveau)
    score = 0

    # Mots directement présents dans la recherche.
    termes = set(
        terme
        for terme in (formation_norm + " " + niveau_norm).split()
        if len(terme) > 2
    )
    for terme in termes:
        if terme in contenu:
            score += 1

    # Variantes fréquentes des intitulés de formation.
    variantes = {
        "cybersecurite": [
            "cybersecurite",
            "cyber security",
            "securite informatique",
            "securite des systemes d'information",
            "securite des reseaux",
        ],
        "master": [
            "master",
            "diplome national de master",
            "mention de master",
        ],
        "licence": [
            "licence",
            "licence generale",
        ],
        "doctorat": [
            "doctorat",
            "ecole doctorale",
        ],
    }
    for cle, expressions in variantes.items():
        if cle in formation_norm or cle in niveau_norm:
            if any(normaliser(expr) in contenu for expr in expressions):
                score += 2

    # Les pages de formation et d'admission sont plus pertinentes
    # que les pages institutionnelles générales.
    expressions_formation = (
        "conditions d'acces",
        "admission",
        "candidature",
        "programme de formation",
        "parcours",
        "prerequis",
        "modalites de selection",
    )
    for expression in expressions_formation:
        if normaliser(expression) in contenu:
            score += 1

    return score


def normaliser_url(url):
    parties = urlparse(url)

    # Supprime les paramètres de suivi et les fragments.
    chemin = parties.path.rstrip("/")

    return urlunparse((
        parties.scheme.lower(),
        parties.netloc.lower(),
        chemin,
        "",
        "",
        ""
    ))





def chercher_pages(formation, niveau, maximum=8):
    if maximum <= 0 or not formation.strip():
        return []

    requetes = [
        f'"{formation}" {niveau} France formation admission université',
        f'"{formation}" {niveau} programme prérequis candidature site:.fr',
        f'"{formation}" {niveau} frais alternance langues établissement',
    ]
    resultats_par_url = {}
    erreurs = []

    # DDGS interroge plusieurs moteurs via son backend auto. Les requêtes
    # suivantes servent de relance ciblée si la première rapporte peu de pages.
    try:
        with DDGS() as recherche:
            for requete in requetes:
                if len(resultats_par_url) >= maximum:
                    break
                try:
                    pages = recherche.text(
                        requete,
                        region="fr-fr",
                        max_results=max(maximum, 5),
                        backend="auto"
                    )
                except Exception as erreur:
                    erreurs.append(f"{requete}: {erreur}")
                    continue

                for page in pages or []:
                    url = str(page.get("href", "")).strip()
                    titre = str(page.get("title", "")).strip()
                    extrait = str(page.get("body", "")).strip()

                    if not url.startswith(("https://", "http://")):
                        continue
                    if not urlparse(url).netloc:
                        continue

                    url_unique = normaliser_url(url)
                    if url_unique in resultats_par_url:
                        continue

                    score = score_pertinence(
                        titre, extrait, formation, niveau
                    )
                    if score == 0:
                        continue

                    resultats_par_url[url_unique] = {
                        "Formation recherchée": formation,
                        "Niveau recherché": niveau,
                        "Titre de la page": titre,
                        "URL source": url,
                        "Domaine .fr": urlparse(url).netloc,
                        "Source institutionnelle probable":
                            est_domaine_institutionnel(url),
                        "Score de pertinence": score,
                        "Extrait du moteur de recherche": extrait,
                        "Mode de découverte": "Recherche Web multi-moteur",
                        "Description catalogue (non vérifiée)": "",
                        "Statut recherche": "Résultat fourni par DDGS",
                        "Erreurs recherche": "",
                        "Page téléchargée": False,
                        "Texte extrait": "",
                        "Date de collecte": datetime.now().isoformat(
                            timespec="seconds"
                        )
                    }
    except Exception as erreur:
        erreurs.append(f"Initialisation DDGS: {erreur}")

    # Le catalogue n'est qu'un secours local pour la seule recherche qu'il
    # couvre. Ses descriptions ne sont jamais présentées comme des extraits web.
    if not resultats_par_url:
        recherche = f"{formation} {niveau}".lower()
        termes_cyber = ("cyber", "sécurité", "securite", "security")
        termes_master = ("master", "bac+5")
        if (
            any(terme in recherche for terme in termes_cyber)
            and any(terme in recherche for terme in termes_master)
        ):
            catalogue = [
                {
                    "titre": "Master Cybersécurité et sciences des données — Université Paris 8",
                    "url": "https://www.univ-paris8.fr/-Master-Cybersecurite-et-sciences-des-donnees-",
                    "description": "Page du catalogue local à revisiter pour obtenir les informations actuelles.",
                },
                {
                    "titre": "Master Cybersecurity — Université de Caen Normandie",
                    "url": "https://uniform.unicaen.fr/catalogue/formation/m/7616-master-s-degree-cybersecurity?e=FA",
                    "description": "Page du catalogue local à revisiter pour obtenir les informations actuelles.",
                },
                {
                    "titre": "Admission Master cybersécurité — Université de Rennes",
                    "url": "https://cyberschool.univ-rennes.fr/admission/admission-master-cybersecurite-parcours-securite-logicielle-et-materielle/",
                    "description": "Page du catalogue local à revisiter pour obtenir les informations actuelles.",
                },
                {
                    "titre": "Master CyberSécurité — ENSICAEN",
                    "url": "https://www.ensicaen.fr/formation/master-cybersecurite/",
                    "description": "Page du catalogue local à revisiter pour obtenir les informations actuelles.",
                },
            ]
            for page in catalogue:
                url = page["url"]
                resultats_par_url[normaliser_url(url)] = {
                    "Formation recherchée": formation,
                    "Niveau recherché": niveau,
                    "Titre de la page": page["titre"],
                    "URL source": url,
                    "Domaine .fr": urlparse(url).netloc,
                    "Source institutionnelle probable":
                        est_domaine_institutionnel(url),
                    "Score de pertinence": 0,
                    "Extrait du moteur de recherche": "",
                    "Mode de découverte": "Catalogue local de secours — non exhaustif",
                    "Description catalogue (non vérifiée)": page["description"],
                    "Statut recherche": "Aucun résultat de recherche Web exploitable",
                    "Erreurs recherche": " | ".join(erreurs),
                    "Page téléchargée": False,
                    "Texte extrait": "",
                    "Date de collecte": datetime.now().isoformat(
                        timespec="seconds"
                    )
                }

    resultats = list(resultats_par_url.values())
    resultats.sort(
        key=lambda page: (
            page["Source institutionnelle probable"],
            page["Score de pertinence"]
        ),
        reverse=True
    )
    if erreurs and resultats:
        for page in resultats:
            page["Erreurs recherche"] = " | ".join(erreurs)
    return resultats[:maximum]




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
    import re
    import unicodedata

    if not texte_page:
        return {theme: "" for theme in THEMES}

    def normaliser(texte):
        texte = unicodedata.normalize("NFD", texte.lower())
        return "".join(
            caractere
            for caractere in texte
            if unicodedata.category(caractere) != "Mn"
        )

    # Expressions supplémentaires pour mieux reconnaître
    # les formulations utilisées par les universités.
    expressions = {
        "Prérequis académiques": [
            "diplomes conseilles",
            "licence informatique",
            "licence mathematique",
            "conditions d'acces",
            "prerequis",
            "connaissances en informatique",
            "candidatures venant d'autres formations",
            "bac+3",
        ],
        "Niveau de français": [
            "niveau de francais",
            "langue d'enseignement",
            "francais b2",
            "francais c1",
            "tcf",
            "delf",
            "dalf",
            "niveau d'anglais",
            "anglais b2",
        ],
        "Prérequis techniques": [
            "competences techniques",
            "competences attendues",
            "programmation",
            "reseaux informatiques",
            "systemes d'exploitation",
            "mathematiques appliquees",
            "connaissances techniques",
        ],
        "Frais de scolarité": [
            "frais d'inscription",
            "droits d'inscription",
            "droits de scolarite",
            "tarif pour une inscription",
            "cout de formation",
            "couts de formation",
            "annee universitaire",
            "contribution de vie etudiante",
            "cvec",
            "exoneration",
            "pris en charge par l'employeur",
        ],
        "Modalités de candidature": [
            "modalites de candidature",
            "modalites de selection",
            "examen sur dossier",
            "procedure d'inscription",
            "monmaster",
            "ecandidat",
            "date de candidature",
            "capacite d'accueil",
        ],
        "Documents demandés": [
            "documents a fournir",
            "pieces justificatives",
            "dossier de candidature",
            "releve de notes",
            "lettre de motivation",
            "curriculum vitae",
            "cv demande",
        ],
        "Alternance": [
            "formation en alternance",
            "formation par apprentissage",
            "contrat d'apprentissage",
            "contrat de professionnalisation",
            "rythme de l'alternance",
            "alternance en entreprise",
            "inscrire en alternance",
            "apprenti",
            "employeur",
        ],
    }

    texte = " ".join(texte_page.split())

    # Découper le texte en phrases plutôt que de prendre
    # un grand bloc autour du mot-clé.
    phrases = re.split(r"(?<=[.!?;])\s+", texte)
    phrases = [p.strip() for p in phrases if p.strip()]

    phrases_normalisees = [normaliser(p) for p in phrases]

    preuves = {}

    for theme, mots_cles in THEMES.items():
        termes = list(mots_cles)
        termes.extend(expressions.get(theme, []))
        termes_normalises = [
            normaliser(str(terme).strip())
            for terme in termes
            if len(normaliser(str(terme).strip())) >= 4
        ]

        extraits = []

        for phrase, phrase_norm in zip(
            phrases, phrases_normalisees
        ):
            if any(terme in phrase_norm for terme in termes_normalises):
                # Éviter les doublons.
                if phrase not in extraits:
                    extraits.append(phrase)

            if len(extraits) >= 5:
                break

        preuves[theme] = " | ".join(extraits)

    return preuves


    def normaliser(texte):
        texte = unicodedata.normalize("NFD", texte.lower())
        return "".join(
            caractere
            for caractere in texte
            if unicodedata.category(caractere) != "Mn"
        )

    texte_normalise = normaliser(texte_page)

    expressions_supplementaires = {
        "Prérequis académiques": [
            "diplomes conseilles",
            "licence informatique",
            "licence mathematique",
            "conditions d'acces",
            "prerequis",
            "connaissances en informatique",
            "candidatures venant d'autres formations",
            "bac+3",
        ],
        "Niveau de français": [
            "niveau de francais",
            "niveau de langue",
            "langue d'enseignement",
            "francais niveau",
            "francais b2",
            "francais c1",
            "tcf",
            "delf",
            "dalf",
            "niveau d'anglais",
            "anglais b2",
        ],
        "Prérequis techniques": [
            "competences techniques",
            "connaissances en informatique",
            "programmation",
            "reseaux informatiques",
            "systemes d'exploitation",
            "mathematiques appliquees",
            "competences attendues",
        ],
        "Frais de scolarité": [
            "frais d'inscription",
            "droits d'inscription",
            "droits de scolarite",
            "tarif pour une inscription",
            "cout de formation",
            "annee universitaire",
            "contribution de vie etudiante",
            "cvec",
            "exoneration",
        ],
        "Modalités de candidature": [
            "modalites de candidature",
            "modalites de selection",
            "examen sur dossier",
            "procedure d'inscription",
            "premiere annee de master",
            "monmaster",
            "ecandidat",
            "date de candidature",
            "capacite d'accueil",
        ],
        "Documents demandés": [
            "documents a fournir",
            "pieces justificatives",
            "dossier de candidature",
            "releve de notes",
            "lettre de motivation",
            "curriculum vitae",
            "cv",
            "diplome",
        ],
        "Alternance": [
            "formation en alternance",
            "formation par apprentissage",
            "contrat d'apprentissage",
            "contrat de professionnalisation",
            "rythme de l'alternance",
            "alternance en entreprise",
            "en alternance",
            "employeur",
        ],
    }

    for theme, mots_cles in THEMES.items():
        extraits = []
        termes = list(mots_cles)

        # Ajouter les expressions adaptées à chaque thème.
        termes.extend(expressions_supplementaires.get(theme, []))

        for mot in termes:
            mot_normalise = normaliser(str(mot).strip())

            if len(mot_normalise) < 3:
                continue

            # Chercher toutes les occurrences de l'expression.
            positions = [
                correspondance.start()
                for correspondance in re.finditer(
                    re.escape(mot_normalise),
                    texte_normalise
                )
            ]

            for position in positions:
                debut = max(0, position - 220)
                fin = min(len(texte_page), position + 500)

                extrait = texte_page[debut:fin].strip()

                if not extrait:
                    continue

                # Éviter les extraits identiques ou presque identiques.
                deja_present = any(
                    extrait in existant or existant in extrait
                    for existant in extraits
                )

                if not deja_present:
                    extraits.append(extrait)

                if len(extraits) >= 5:
                    break

            if len(extraits) >= 5:
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
    if SORTIE.exists():
        precedent = pd.read_excel(SORTIE)
        # Combiner les anciennes et les nouvelles données.
        combine = pd.concat(
            [precedent, tableau],
            ignore_index=True
        )
        # Identifier chaque recherche par URL et formation.
        cles = ["URL source", "Formation recherchée"]
        # Préférer les lignes contenant le plus d'informations.
        colonnes_donnees = [
            colonne for colonne in combine.columns
            if colonne not in cles
        ]
        combine["_completude"] = (
            combine[colonnes_donnees]
            .notna()
            .sum(axis=1)
        )
        combine = combine.sort_values(
            "_completude",
            ascending=True
        )
        # La ligne la plus complète est conservée.
        tableau = combine.drop_duplicates(
            subset=cles,
            keep="last"
        ).drop(columns=["_completude"])

    tableau.to_excel(SORTIE, index=False)
    print(f"\nRésultats enregistrés dans : {SORTIE.resolve()}")

    print("\nRecherche terminée.")
    print(
        "Important : les extraits sont des pistes documentaires, "
        "pas des conditions d'admission automatiquement confirmées."
    )


if __name__ == "__main__":
    main()
