import pandas as pd
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

SOURCE = "formations_cybersecurite_2027.xlsx"
OUTPUT = "formations_cybersecurite_filtrees_2027.xlsx"

if not Path(SOURCE).exists():
    print(f"Fichier introuvable : {SOURCE}")
    raise SystemExit(1)

df = pd.read_excel(SOURCE, sheet_name="Formations")

# Éliminer les colonnes dupliquées et réinitialiser les index.
df = df.loc[:, ~df.columns.duplicated()].copy()
df.columns = [str(c).strip() for c in df.columns]
df = df.loc[:, ~pd.Index(df.columns).duplicated()].copy()
df = df.reset_index(drop=True)

if "Titre" not in df.columns or "URL" not in df.columns:
    print("Colonnes disponibles :", list(df.columns))
    raise SystemExit("Le fichier Excel doit contenir les colonnes Titre et URL.")

if "Résumé" not in df.columns:
    df["Résumé"] = ""

# Supprimer les anciennes colonnes calculées si elles existent déjà.
colonnes_calculees = [
    "Score indicatif",
    "Priorité",
    "Source institutionnelle probable",
    "Type de source",
    "Vérifié le",
]
df = df.drop(columns=colonnes_calculees, errors="ignore")
df = df.reset_index(drop=True)

keywords = {
    "cybersecurite": 5,
    "cybersécurité": 5,
    "securite des systemes": 4,
    "sécurité des systèmes": 4,
    "securite informatique": 4,
    "sécurité informatique": 4,
    "securite des reseaux": 4,
    "sécurité des réseaux": 4,
    "cloud": 2,
    "administration des reseaux": 3,
    "réseaux et télécommunication": 3,
    "reseaux et telecommunication": 3,
    "informatique": 1,
}

def analyse(row):
    titre = str(row.get("Titre", ""))
    resume = str(row.get("Résumé", ""))
    url = str(row.get("URL", ""))
    texte = f"{titre} {resume} {url}".lower()
    domaine = urlparse(url).netloc.lower()

    score = sum(points for mot, points in keywords.items() if mot in texte)

    institutionnel = (
        domaine.endswith(".gouv.fr")
        or any(mot in domaine for mot in [
            "univ-", ".univ", "universite", "université",
            "sorbonne", "unicaen", "unilim", "u-pec.fr",
            "paris8.fr", "u-paris.fr"
        ])
    )

    secondaire = any(mot in domaine for mot in [
        "scribd.com", "mastersportal.com",
        "globaladmissions.com", "jedha.co",
        "meilleurs-masters.com", "studentum.",
        "unifac.net", "askai."
    ])

    if institutionnel:
        score += 2
    if secondaire:
        score -= 3

    if score >= 7:
        priorite = "Priorité élevée à vérifier"
    elif score >= 4:
        priorite = "À examiner"
    else:
        priorite = "Priorité faible"

    return {
        "Score indicatif": score,
        "Priorité": priorite,
        "Source institutionnelle probable":
            "Oui, à confirmer" if institutionnel else "Non confirmée",
        "Type de source":
            "Agrégateur ou source secondaire" if secondaire else "À vérifier",
        "Vérifié le": datetime.now().strftime("%Y-%m-%d"),
    }

resultats = pd.DataFrame([analyse(row) for _, row in df.iterrows()])
df = pd.concat([df, resultats], axis=1)

df = df.sort_values(
    by=["Score indicatif", "Titre"],
    ascending=[False, True]
).reset_index(drop=True)

prioritaires = df.loc[
    df["Priorité"] == "Priorité élevée à vérifier"
].copy()

a_examiner = df.loc[
    df["Priorité"] == "À examiner"
].copy()

masque = (
    df["Priorité"].eq("Priorité faible")
    | df["Source institutionnelle probable"].ne("Oui, à confirmer")
)
a_verifier = df.loc[masque].copy()

with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
    df.to_excel(writer, sheet_name="Toutes les pages", index=False)
    prioritaires.to_excel(writer, sheet_name="Priorité élevée", index=False)
    a_examiner.to_excel(writer, sheet_name="À examiner", index=False)
    a_verifier.to_excel(writer, sheet_name="À vérifier", index=False)

print("\nFiltrage terminé !")
print(f"Pages analysées : {len(df)}")
print(f"Priorité élevée : {len(prioritaires)}")
print(f"À examiner : {len(a_examiner)}")
print(f"À vérifier : {len(a_verifier)}")
print(f"Fichier créé : {Path(OUTPUT).resolve()}")
print("Attention : le score ne représente pas une probabilité d'admission.")
