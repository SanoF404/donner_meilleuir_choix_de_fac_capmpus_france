
from ddgs import DDGS
import pandas as pd
import time
from datetime import datetime
from urllib.parse import urlparse

QUERIES = [
    "master cybersécurité université publique France",
    "master sécurité informatique université France admission",
    "master réseaux systèmes sécurité université France",
    "master administration sécurité réseaux ASR université",
    "master informatique parcours cybersécurité université",
    "master cybersécurité étudiant international France",
    "site:univ-lille.fr cybersécurité master informatique",
    "site:sorbonne-universite.fr cybersécurité master",
    "site:univ-reims.fr master sécurité réseaux",
    "site:univ-lorraine.fr master cybersécurité",
    "site:univ-rouen.fr master sécurité systèmes information",
    "site:univ-tlse3.fr master sécurité systèmes réseaux",
]

OFFICIAL_DOMAINS = (
    ".gouv.fr",
    ".fr",
    ".univ.fr",
    ".edu",
)

results = []
errors = []
seen_urls = set()

print("Recherche de formations en cybersécurité")
print("Rentrée visée : septembre 2027\n")

for query in QUERIES:
    print(f"Recherche : {query}")
    success = False

    for attempt in range(2):
        try:
            with DDGS() as engine:
                pages = list(
                    engine.text(query, max_results=10)
                )

            for page in pages:
                url = page.get("href", "").strip()
                title = page.get("title", "").strip()
                snippet = page.get("body", "").strip()

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                domain = urlparse(url).netloc.lower()
                official = (
                    domain.endswith(OFFICIAL_DOMAINS)
                    or domain.endswith(".gouv.fr")
                )

                results.append({
                    "Recherche": query,
                    "Titre": title,
                    "URL": url,
                    "Domaine": domain,
                    "Source institutionnelle probable": (
                        "À vérifier" if official else "Non confirmée"
                    ),
                    "Résumé": snippet,
                    "Vérification humaine": "À faire",
                    "Admission des Tunisiens": "À confirmer",
                    "TCF B2 accepté": "À confirmer",
                    "Notes requises": "À confirmer",
                    "Rentrée": "Septembre 2027",
                    "Date de collecte": datetime.now().strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                })

            success = True
            print(f"  Résultats reçus : {len(pages)}")
            break

        except Exception as exc:
            if attempt == 0:
                print("  Nouvelle tentative...")
                time.sleep(2)
            else:
                errors.append({
                    "Recherche": query,
                    "Erreur": str(exc),
                })
                print(f"  Échec : {exc}")

    time.sleep(1)

output_file = "formations_cybersecurite_2027.xlsx"

# Toujours créer un nouveau rapport :
# aucune ancienne donnée ne sera présentée comme un résultat récent.
with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    columns = [
        "Recherche", "Titre", "URL", "Domaine",
        "Source institutionnelle probable", "Résumé",
        "Vérification humaine", "Admission des Tunisiens",
        "TCF B2 accepté", "Notes requises", "Rentrée",
        "Date de collecte",
    ]

    pd.DataFrame(results, columns=columns).to_excel(
        writer, sheet_name="Formations", index=False
    )

    pd.DataFrame(
        errors, columns=["Recherche", "Erreur"]
    ).to_excel(writer, sheet_name="Erreurs", index=False)

print("\n--- BILAN ---")
print(f"Pages uniques collectées : {len(results)}")
print(f"Requêtes en erreur : {len(errors)}")
print(f"Rapport créé : {output_file}")

if not results:
    print(
        "Aucune page collectée. Consulte l'onglet Erreurs "
        "et vérifie ta connexion."
    )
else:
    print(
        "Les résultats sont des pistes de recherche, "
        "pas des admissions confirmées."
    )
