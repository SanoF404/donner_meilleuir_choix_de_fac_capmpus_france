from assistant_gemini import generer_reponse
from pathlib import Path
from urllib.parse import urlparse
import re

import pandas as pd
import streamlit as st

DOSSIER = Path(__file__).resolve().parent
FICHIER = DOSSIER / "formations_cybersecurite_2027.xlsx"
FICHIER_FILTRE = DOSSIER / "formations_cybersecurite_filtrees_2027.xlsx"

st.set_page_config(
    page_title="Campus France Advisor",
    page_icon="🎓",
    layout="wide"
)


def texte(valeur):
    if valeur is None:
        return ""
    try:
        if pd.isna(valeur):
            return ""
    except (TypeError, ValueError):
        pass
    return str(valeur).strip()


def determiner_niveau(ligne):
    contenu = " ".join(
        texte(ligne.get(c, ""))
        for c in ["Recherche", "Titre", "Résumé", "Niveau recherché"]
    ).lower()

    if re.search(r"\bdoctorat\b|\bdoctorate\b|\bphd\b", contenu):
        return "Doctorat"
    if re.search(r"\bmaster\b|\bmsc\b|\bm2\b|\bm1\b", contenu):
        return "Master"
    if re.search(r"\blicence\b|\bbachelor\b|\bl3\b|\bl2\b|\bl1\b", contenu):
        return "Licence"
    if re.search(r"\bbut\b|\bbts\b|\bdut\b", contenu):
        return "BTS / BUT"
    return "Autre / à vérifier"


def determiner_type(ligne):
    domaine = urlparse(texte(ligne.get("URL", ""))).netloc.lower()
    contenu = " ".join(
        texte(ligne.get(c, ""))
        for c in ["Titre", "Domaine", "URL"]
    ).lower()

    prives = [
        "epitech", "epita", "esiea", "efrei", "esilv",
        "ynov", "supinfo", "guardia", "hetic"
    ]
    if any(nom in contenu for nom in prives):
        return "Privé (à confirmer)"

    publics = [
        "université", "universite", "univ-", "u-paris.fr",
        "sorbonne-universite.fr", "ip-paris.fr", "ensicaen.fr"
    ]
    if any(nom in contenu for nom in publics):
        return "Public probable"

    if domaine.endswith(".gouv.fr"):
        return "Public probable"

    return "À vérifier"


def obtenir_texte(ligne, *colonnes):
    for colonne in colonnes:
        valeur = texte(ligne.get(colonne, ""))
        if valeur:
            return valeur
    return ""


def termes_recherche(valeur):
    return [
        terme.lower()
        for terme in re.findall(r"[\wÀ-ÿ+.-]+", texte(valeur))
        if len(terme) > 2
    ]


@st.cache_data
def charger_donnees():
    for chemin in [FICHIER, FICHIER_FILTRE]:
        if chemin.exists():
            try:
                df = pd.read_excel(chemin).fillna("")
                df = df.rename(columns={
                    colonne: colonne.replace("�", "é")
                    for colonne in df.columns
                    if "�" in colonne
                })
                if "Titre" in df.columns and "URL" in df.columns:
                    df = df.drop_duplicates(subset=["URL"], keep="first")
                    if "Résumé" not in df.columns:
                        df["Résumé"] = ""
                    if "Recherche" not in df.columns:
                        df["Recherche"] = ""
                    df["Niveau détecté"] = df.apply(
                        determiner_niveau, axis=1
                    )
                    df["Type détecté"] = df.apply(
                        determiner_type, axis=1
                    )
                    return df
            except Exception:
                continue
    return pd.DataFrame()


def rechercher_formations(df, formation, niveau):
    resultats = df.copy()

    mots = termes_recherche(formation)
    if mots:
        colonnes = [
            c for c in ["Recherche", "Titre", "Domaine", "Résumé"]
            if c in resultats.columns
        ]
        texte_recherche = resultats[colonnes].astype(str).agg(" ".join, axis=1)
        masque = pd.Series(False, index=resultats.index)
        for mot in mots:
            masque |= texte_recherche.str.contains(
                re.escape(mot), case=False, na=False
            )
        resultats = resultats[masque]

    if niveau != "Tous les niveaux":
        resultats = resultats[
            resultats["Niveau détecté"] == niveau
        ]

    return resultats.copy()


def repondre_assistant(question, df, profil=None):
    profil = profil or {}
    question_bas = texte(question).lower()
    projet = texte(profil.get("formation"))
    niveau = texte(profil.get("niveau")) or "Tous les niveaux"
    recherche = projet or question
    candidats = rechercher_formations(df, recherche, niveau)

    if profil:
        resume_profil = []
        if profil.get("diplome"):
            resume_profil.append(f"diplôme : {profil['diplome']}")
        if profil.get("specialite"):
            resume_profil.append(f"spécialité : {profil['specialite']}")
        if profil.get("francais") not in (None, "", "Non renseigné"):
            resume_profil.append(f"français : {profil['francais']}")
        intro = (
            "Je m'appuie sur ton profil de cette session"
            + (f" ({'; '.join(resume_profil)})" if resume_profil else "")
            + "."
        )
    else:
        intro = (
            "Je n'ai pas encore de profil enregistré. Je peux déjà consulter "
            "le catalogue local, ou tu peux remplir l'onglet « Mon profil »."
        )

    if candidats.empty:
        return (
            intro + " Je ne trouve pas de formation correspondante dans les "
            "fichiers locaux pour cette demande. Le catalogue n'est pas exhaustif."
        )

    lignes = [intro]
    if any(mot in question_bas for mot in ("compétence", "competence", "projet", "stage", "certification")):
        competences = texte(profil.get("competences"))
        certifications = texte(profil.get("certifications"))
        if competences or certifications:
            lignes.append(
                "Dans ton profil, les éléments déclarés sont : "
                + "; ".join(
                    valeur for valeur in [
                        f"compétences/projets : {competences}" if competences else "",
                        f"certifications : {certifications}" if certifications else "",
                    ]
                    if valeur
                )
                + "."
            )
        else:
            lignes.append(
                "Aucune compétence, expérience ou certification n'est encore "
                "renseignée dans ton profil. Tu peux les ajouter dans l'onglet profil."
            )

    if any(mot in question_bas for mot in ("note", "moyenne", "résultat", "resultat")):
        notes = [
            f"{nom} : {valeur}"
            for nom, valeur in [
                ("L1", profil.get("moyenne_l1")),
                ("L2", profil.get("moyenne_l2")),
                ("L3", profil.get("moyenne_l3")),
                ("Dernière moyenne semestrielle", profil.get("moyenne_s1")),
                ("Moyenne générale", profil.get("moyenne_generale")),
            ]
            if texte(valeur)
        ]
        lignes.append(
            ("Notes renseignées : " + "; ".join(notes) + ". ")
            if notes else "Aucune moyenne n'est renseignée dans ton profil. "
            + "Les données locales ne permettent pas de déduire une admission à partir des notes."
        )

    if any(mot in question_bas for mot in ("frais", "coût", "cout", "budget")):
        champs_frais = [
            colonne for colonne in ["Frais de scolarité", "Frais", "Droits d'inscription"]
            if colonne in candidats.columns
        ]
        if not champs_frais:
            lignes.append(
                "Les fichiers locaux ne contiennent pas de montant de frais "
                "fiable pour ces résultats. Vérifie les tarifs sur chaque site officiel."
            )

    faits_demandes = []
    if any(mot in question_bas for mot in ("français", "francais", "langue", "tcf", "delf")):
        faits_demandes.append(("TCF B2 accepté", "Français / TCF B2"))
    if any(mot in question_bas for mot in ("rentrée", "rentree", "année universitaire", "annee universitaire")):
        faits_demandes.append(("Rentrée", "Rentrée indiquée"))
    if any(mot in question_bas for mot in ("notes", "moyenne", "résultat", "resultat")):
        faits_demandes.append(("Notes requises", "Notes requises"))

    for champ, libelle in faits_demandes:
        if champ in candidats.columns:
            valeurs = []
            for _, ligne in candidats.head(3).iterrows():
                valeur = texte(ligne.get(champ)) or "Information absente"
                valeurs.append(f"{texte(ligne.get('Titre'))} : {valeur}")
            lignes.append(f"{libelle} — " + "; ".join(valeurs))
        else:
            lignes.append(
                f"{libelle} : cette information n'est pas structurée dans "
                "les fichiers locaux et reste à confirmer auprès de l'établissement."
            )

    if any(mot in question_bas for mot in ("prérequis", "prerequis", "admission", "candidature")):
        lignes.append(
            "Les conditions d'admission peuvent dépendre du parcours et de la "
            "campagne. Les informations non présentes ou non vérifiées restent à confirmer."
        )

    lignes.append("Formations repérées dans le catalogue local :")
    for _, ligne in candidats.head(3).iterrows():
        titre = texte(ligne.get("Titre")) or "Formation sans titre"
        url = texte(ligne.get("URL"))
        source = f" — {url}" if url.startswith("https://") else ""
        lignes.append(f"• {titre}{source}")

    lignes.append(
        "Ces résultats sont des pistes à vérifier ; ils ne garantissent ni "
        "l'ouverture de la formation pour la rentrée visée ni l'admission."
    )
    return "\n\n".join(lignes)


def afficher_formations(df):
    if df.empty:
        st.info(
            "Aucun résultat correspondant dans les fichiers actuels. "
            "Cela ne signifie pas qu'aucune formation de ce type n'existe."
        )
        return

    for rang, (_, ligne) in enumerate(df.iterrows(), start=1):
        titre = texte(ligne.get("Titre")) or "Formation sans titre"

        with st.container(border=True):
            entete, statut = st.columns([4, 1])
            entete.subheader(f"{rang}. {titre}")
            statut.caption(texte(ligne.get("Type détecté")) or "Statut à vérifier")

            resume = obtenir_texte(ligne, "Résumé", "R�sum�")
            if resume:
                st.write(resume[:700] + ("…" if len(resume) > 700 else ""))

            infos = st.columns(3)
            infos[0].caption(f"🎓 {texte(ligne.get('Niveau détecté')) or 'Niveau à vérifier'}")
            infos[1].caption(f"🏛️ {obtenir_texte(ligne, 'Domaine') or 'Établissement à vérifier'}")
            infos[2].caption(f"📅 {obtenir_texte(ligne, 'Rentrée') or 'Rentrée à confirmer'}")

            with st.expander("Prérequis, coûts et candidature"):
                for champ, libelle, variantes in [
                    ("Prérequis académiques", "Prérequis académiques", ()),
                    ("Niveau de français", "Français", ("TCF B2 accepté",)),
                    ("Niveau d'anglais", "Anglais", ()),
                    ("Frais de scolarité", "Frais", ()),
                    ("Modalités de candidature", "Candidature", ()),
                    ("Documents demandés", "Documents", ()),
                    ("Alternance", "Alternance", ()),
                    ("Vérification humaine", "Vérification", ()),
                ]:
                    valeur = obtenir_texte(ligne, champ, *variantes)
                    st.write(f"**{libelle} :** {valeur or 'À vérifier sur le site officiel'}")

            url = obtenir_texte(ligne, "URL")
            if url.startswith(("https://", "http://")):
                st.link_button("Ouvrir la source officielle", url)


st.title("Campus France Advisor")
st.write(
    "Recherche de formations en France et préparation personnalisée "
    "du dossier de candidature."
)

st.info(
    "Prototype : vérifie toujours les conditions d'admission, les frais "
    "et les dates sur le site officiel de chaque établissement."
)

donnees = charger_donnees()

if donnees.empty:
    st.error(
        "Aucun fichier Excel exploitable n'a été trouvé dans le dossier du projet."
    )
    st.stop()

onglet_recherche, onglet_profil, onglet_assistant = st.tabs([
    "Rechercher une formation",
    "Mon profil et mes 7 choix",
    "Assistant d'orientation"
])

with onglet_recherche:
    st.header("Explorer les formations")

    with st.form("form_recherche"):
        recherche = st.text_input(
            "Quelle formation recherches-tu ?",
            value="Cybersécurité",
            placeholder="Ex. : Data Science, MIAGE, droit..."
        )
        niveau_recherche = st.selectbox(
            "Niveau d'études",
            [
                "Tous les niveaux", "BTS / BUT", "Licence",
                "Master", "Doctorat", "Autre / à vérifier"
            ],
            index=3
        )
        type_recherche = st.radio(
            "Type d'établissement",
            ["Public et privé", "Public uniquement", "Privé uniquement"],
            horizontal=True
        )
        lancer_recherche = st.form_submit_button("Rechercher")

    if "recherche_active" not in st.session_state:
        st.session_state.recherche_active = "Cybersécurité"
        st.session_state.niveau_actif = "Master"
        st.session_state.type_actif = "Public et privé"

    if lancer_recherche:
        st.session_state.recherche_active = recherche
        st.session_state.niveau_actif = niveau_recherche
        st.session_state.type_actif = type_recherche

    resultats = rechercher_formations(
        donnees,
        st.session_state.recherche_active,
        st.session_state.niveau_actif
    )

    type_actif = st.session_state.type_actif
    if type_actif == "Public uniquement":
        resultats = resultats[
            resultats["Type détecté"].str.startswith("Public")
        ]
    elif type_actif == "Privé uniquement":
        resultats = resultats[
            resultats["Type détecté"].str.startswith("Privé")
        ]

    publics = resultats[
        resultats["Type détecté"].str.startswith("Public")
    ]
    prives = resultats[
        resultats["Type détecté"].str.startswith("Privé")
    ]
    incertains = resultats[
        resultats["Type détecté"] == "À vérifier"
    ]

    c1, c2, c3 = st.columns(3)
    c1.metric("Résultats", len(resultats))
    c2.metric("Publics probables", len(publics))
    c3.metric("Privés à confirmer", len(prives))

    if st.session_state.niveau_actif == "Master":
        st.subheader("Masters correspondant à la recherche")
        st.caption(
            "La liste vient des fichiers locaux du projet. Les conditions, "
            "frais et dates restent à confirmer sur les pages officielles."
        )
        if not resultats.empty:
            colonne_tri = st.selectbox(
                "Trier les résultats",
                ["Établissement", "Titre", "Rentrée"],
                key="tri_masters"
            )
            colonnes_tri = {
                "Établissement": "Domaine",
                "Titre": "Titre",
                "Rentrée": "Rentrée",
            }
            colonne = colonnes_tri[colonne_tri]
            if colonne in resultats.columns:
                resultats = resultats.sort_values(
                    colonne, key=lambda serie: serie.astype(str).str.lower()
                )
            colonnes_comparaison = [
                colonne for colonne in [
                    "Titre", "Domaine", "Rentrée", "TCF B2 accepté",
                    "Notes requises", "Vérification humaine",
                    "Source institutionnelle probable"
                ]
                if colonne in resultats.columns
            ]
            if colonnes_comparaison:
                st.dataframe(
                    resultats[colonnes_comparaison],
                    hide_index=True,
                    width="stretch"
                )
        afficher_formations(resultats)
    else:
        tab_public, tab_prive, tab_incertain = st.tabs([
            "Établissements publics",
            "Établissements privés",
            "Statut à vérifier"
        ])

        with tab_public:
            afficher_formations(publics)
        with tab_prive:
            afficher_formations(prives)
        with tab_incertain:
            afficher_formations(incertains)


with onglet_profil:
    st.header("Mon profil étudiant")
    st.write(
        "Renseigne ton dossier pour préparer une sélection personnalisée."
    )

    with st.form("profil_etudiant"):
        st.subheader("Projet d'études")

        formation_visee = st.text_input(
            "Formation recherchée",
            value="Cybersécurité"
        )
        niveau_vise = st.selectbox(
            "Niveau souhaité",
            [
                "BTS / BUT", "Licence", "Master", "Doctorat",
                "Autre / à vérifier"
            ],
            index=2
        )
        type_vise = st.selectbox(
            "Établissements préférés",
            ["Public et privé", "Public uniquement", "Privé uniquement"]
        )
        c_projet1, c_projet2 = st.columns(2)
        pays_residence = c_projet1.text_input("Pays de résidence (facultatif)")
        nationalite = c_projet2.text_input("Nationalité (facultatif)")
        niveau_actuel = st.selectbox(
            "Niveau d'études actuel",
            ["Non renseigné", "Baccalauréat", "Bac+1", "Bac+2", "Bac+3", "Bac+4", "Bac+5 ou plus"]
        )
        diplome = st.text_input(
            "Diplôme actuel ou préparé",
            placeholder="Ex. : Licence Informatique de gestion"
        )
        c_projet3, c_projet4 = st.columns(2)
        specialite = c_projet3.text_input(
            "Domaine ou spécialité",
            placeholder="Ex. : réseaux, développement, mathématiques"
        )
        etablissement_actuel = c_projet4.text_input(
            "Établissement actuel (facultatif)"
        )
        c_projet5, c_projet6 = st.columns(2)
        pays_etudes = c_projet5.text_input("Pays des études actuelles")
        annee_diplome = c_projet6.text_input(
            "Année d'obtention ou prévue", placeholder="Ex. : 2027"
        )

        st.subheader("Préférences de formation")
        villes_preferees = st.text_input(
            "Villes ou régions souhaitées (facultatif)",
            placeholder="Ex. : Caen, Paris, Bretagne"
        )
        c_pref1, c_pref2 = st.columns(2)
        modalite = c_pref1.selectbox(
            "Modalité souhaitée",
            ["Indifférent", "Formation initiale", "Alternance"]
        )
        rentree_visee = c_pref2.text_input(
            "Rentrée visée", placeholder="Ex. : septembre 2027"
        )
        budget = st.text_input(
            "Budget annuel maximal (facultatif)",
            placeholder="Montant et devise, ex. : 5 000 €"
        )

        st.subheader("Moyennes générales")

        c1, c2, c3 = st.columns(3)
        moyenne_l1 = c1.text_input("Moyenne L1")
        moyenne_l2 = c2.text_input("Moyenne L2")
        moyenne_l3 = c3.text_input("Moyenne L3")

        c4, c5 = st.columns(2)
        moyenne_s1 = c4.text_input("Dernière moyenne semestrielle")
        moyenne_generale = c5.text_input("Moyenne générale actuelle")

        st.subheader("Notes par matière")
        st.caption(
            "Ajoute les matières pertinentes. Les notes restent facultatives ; "
            "indique l'échelle utilisée si elle n'est pas sur 20. "
            "Tu peux modifier les exemples ou ajouter des lignes."
        )
        echelle_notes = st.text_input(
            "Échelle de notation (facultatif)", value="Sur 20"
        )

        notes_initiales = pd.DataFrame([
            {"Matière": "Algorithmique", "Note": None, "Année": "L1"},
            {"Matière": "Programmation", "Note": None, "Année": "L1"},
            {"Matière": "Réseaux", "Note": None, "Année": "L2"},
            {"Matière": "Systèmes", "Note": None, "Année": "L2"},
            {"Matière": "Mathématiques", "Note": None, "Année": "L1/L2"},
        ])

        notes_matieres = st.data_editor(
            notes_initiales,
            num_rows="dynamic",
            width="stretch",
            key="notes_matieres"
        )

        st.subheader("Certifications et compétences")
        certifications = st.text_area(
            "Certifications obtenues",
            placeholder="Ex. : nom, organisme, date, résultat..."
        )
        competences = st.text_area(
            "Compétences et projets pertinents",
            placeholder="Ex. : Python, Linux, projets GitHub..."
        )

        st.subheader("Langues")
        c6, c7 = st.columns(2)
        francais = c6.selectbox(
            "Niveau de français",
            ["Non renseigné", "A1", "A2", "B1", "B2", "C1", "C2"]
        )
        anglais = c7.selectbox(
            "Niveau d'anglais",
            ["Non renseigné", "A1", "A2", "B1", "B2", "C1", "C2"]
        )
        autres_langues = st.text_input(
            "Autres langues (facultatif)",
            placeholder="Ex. : arabe courant, allemand B1"
        )

        profil_valide = st.form_submit_button(
            "Trouver mes 7 meilleures formations"
        )

    if profil_valide:
        st.session_state.profil = {
            "formation": formation_visee,
            "niveau": niveau_vise,
            "type": type_vise,
            "pays_residence": pays_residence,
            "nationalite": nationalite,
            "niveau_actuel": niveau_actuel,
            "diplome": diplome,
            "specialite": specialite,
            "etablissement_actuel": etablissement_actuel,
            "pays_etudes": pays_etudes,
            "annee_diplome": annee_diplome,
            "villes_preferees": villes_preferees,
            "modalite": modalite,
            "rentree": rentree_visee,
            "budget": budget,
            "moyenne_l1": moyenne_l1,
            "moyenne_l2": moyenne_l2,
            "moyenne_l3": moyenne_l3,
            "moyenne_s1": moyenne_s1,
            "moyenne_generale": moyenne_generale,
            "notes": notes_matieres.to_dict(orient="records"),
            "echelle_notes": echelle_notes,
            "certifications": certifications,
            "competences": competences,
            "francais": francais,
            "anglais": anglais,
            "autres_langues": autres_langues,
        }
        st.session_state.pop("choix_formations", None)

    if "profil" in st.session_state:
        profil = st.session_state.profil
        st.success("Profil enregistré pour cette session.")
        with st.expander("Résumé du profil utilisé pour cette sélection"):
            st.write(
                f"**Projet :** {profil.get('formation') or 'Non renseigné'} "
                f"— {profil.get('niveau') or 'niveau non renseigné'}"
            )
            st.write(
                f"**Diplôme et spécialité :** "
                f"{profil.get('diplome') or 'Non renseigné'}"
                + (f" — {profil['specialite']}" if profil.get("specialite") else "")
            )
            st.write(
                f"**Préférences :** {profil.get('type')} ; "
                f"{profil.get('modalite')} ; "
                f"villes/régions : {profil.get('villes_preferees') or 'indifférent'} ; "
                f"rentrée : {profil.get('rentree') or 'à préciser'}"
            )
            st.caption(
                "Les notes, le budget, la langue et la localisation sont "
                "collectés pour compléter le profil ; les données locales ne "
                "permettent pas encore de les comparer de façon fiable pour toutes les formations."
            )

        candidats = rechercher_formations(
            donnees, profil["formation"], profil["niveau"]
        )

        if profil["type"] == "Public uniquement":
            candidats = candidats[
                candidats["Type détecté"].str.startswith("Public")
            ]
        elif profil["type"] == "Privé uniquement":
            candidats = candidats[
                candidats["Type détecté"].str.startswith("Privé")
            ]

        # Classement textuel indicatif, sans interprétation comme probabilité.
        def score_provisoire(ligne):
            score = 0
            corpus = " ".join(
                obtenir_texte(ligne, colonne)
                for colonne in ["Titre", "Recherche", "Domaine", "Résumé"]
            ).lower()
            mots_projet = termes_recherche(profil["formation"])
            mots_profil = termes_recherche(
                " ".join([
                    profil.get("diplome", ""),
                    profil.get("specialite", ""),
                    profil.get("competences", ""),
                    profil.get("certifications", ""),
                ])
            )
            score += 2 * sum(1 for mot in set(mots_projet) if mot in corpus)
            score += sum(1 for mot in set(mots_profil) if mot in corpus)
            if texte(ligne.get("URL")).startswith("https://"):
                score += 1
            return score

        if not candidats.empty:
            candidats = candidats.copy()
            candidats["Pertinence provisoire"] = candidats.apply(
                score_provisoire, axis=1
            )
            candidats = candidats.sort_values(
                ["Pertinence provisoire", "Titre"],
                ascending=[False, True]
            ).head(7)

            st.subheader("Tes formations les plus pertinentes dans le catalogue")
            st.warning(
                "Ce classement compare les mots du projet, du diplôme et des "
                "compétences aux données locales. Il ne prédit pas une admission ; "
                "les prérequis et les notes doivent être vérifiés formation par formation."
            )
            afficher_formations(candidats)

            urls = [texte(url) for url in candidats["URL"] if texte(url)]
            titres = {
                texte(ligne["URL"]): texte(ligne["Titre"])
                for _, ligne in candidats.iterrows()
            }
            if "choix_formations" not in st.session_state:
                st.session_state.choix_formations = urls[:7]
            else:
                st.session_state.choix_formations = [
                    url for url in st.session_state.choix_formations
                    if url in urls
                ]
            choix = st.multiselect(
                "Confirme ou modifie ta sélection personnelle (7 au maximum)",
                options=urls,
                format_func=lambda url: titres.get(url, url),
                max_selections=7,
                key="choix_formations"
            )
            st.caption(f"{len(choix)} formation(s) retenue(s). La sélection reste dans cette session.")
            retenues = candidats[candidats["URL"].isin(choix)]
            if not retenues.empty:
                st.subheader("Ma sélection")
                afficher_formations(retenues)
        else:
            st.warning(
                "Aucune formation correspondante dans le catalogue local. "
                "Élargis le domaine ou le niveau, ou ajoute des sources adaptées."
            )

        st.caption(
            "Les informations du profil sont conservées uniquement dans "
            "la session actuelle. Elles ne sont pas encore enregistrées "
            "dans une base de données."
        )



with onglet_assistant:
    st.header("Assistant d'orientation")

    st.info(
        "Cet assistant utilise Gemini et les formations disponibles dans "
        "le catalogue local. Les informations manquantes doivent être "
        "vérifiées sur les sites officiels."
    )

    st.warning(
        "Lorsque tu acceptes ci-dessous, ta question, les champs utiles "
        "de ton profil et les données des formations sélectionnées sont "
        "envoyés à Google Gemini pour générer la réponse. Pour ce prototype, "
        "utilise des données fictives et évite les informations sensibles."
    )

    consentement = st.checkbox(
        "J'accepte l'envoi de ces données à Gemini pour obtenir une réponse.",
        key="consentement_gemini"
    )

    if "messages_assistant" not in st.session_state:
        st.session_state.messages_assistant = [{
            "role": "assistant",
            "content": (
                "Bonjour ! Je suis l'assistant de Campus France Advisor. "
                "Je peux t'aider à comprendre les formations, comparer "
                "les critères et préparer tes candidatures. "
                "Pour commencer, renseigne ton profil dans l'onglet "
                "« Mon profil et mes 7 choix »."
            )
        }]

    for message in st.session_state.messages_assistant:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input(
        "Ex. : Quelles formations correspondent à mon profil ?",
        key="question_assistant",
        disabled=not consentement
    )

    if question:
        historique = st.session_state.messages_assistant[-8:].copy()

        st.session_state.messages_assistant.append({
            "role": "user",
            "content": question
        })

        with st.chat_message("user"):
            st.markdown(question)

        profil = st.session_state.get("profil", {})

        recherche = (
            profil.get("formation")
            or question
        )
        niveau = (
            profil.get("niveau")
            or "Tous les niveaux"
        )

        candidats = rechercher_formations(
            donnees,
            recherche,
            niveau
        )

        if profil.get("type") == "Public uniquement":
            candidats = candidats[
                candidats["Type détecté"].str.startswith("Public")
            ]
        elif profil.get("type") == "Privé uniquement":
            candidats = candidats[
                candidats["Type détecté"].str.startswith("Privé")
            ]

        with st.chat_message("assistant"):
            with st.spinner("Gemini analyse ta question et les formations..."):
                try:
                    reponse = generer_reponse(
                        question=question,
                        formations=candidats,
                        profil=profil,
                        historique=historique
                    )
                except Exception as erreur:
                    st.error(f"Erreur Gemini : {type(erreur).__name__}")
                    st.code(str(erreur))
                    reponse = (
                        "La génération a échoué. Consulte le détail technique "
                        "affiché ci-dessus pour identifier la cause."
                    )

            st.markdown(reponse)

        st.session_state.messages_assistant.append({
            "role": "assistant",
            "content": reponse
        })
st.divider()
st.caption(
    "Campus France Advisor — prototype. Les statuts, critères d'admission "
    "et scores sont indicatifs tant qu'ils ne sont pas confirmés par "
    "les établissements."
)
