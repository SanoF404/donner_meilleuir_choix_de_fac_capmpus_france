import unittest
from unittest.mock import patch

import moteur_recherche


class ChercherPagesTests(unittest.TestCase):
    def moteur_simule(self, resultats=None, erreur=None):
        moteur = patch.object(moteur_recherche, "DDGS").start()
        self.addCleanup(patch.stopall)
        instance = moteur.return_value.__enter__.return_value
        if erreur:
            instance.text.side_effect = erreur
        else:
            instance.text.side_effect = resultats or []
        return instance

    def test_recherche_web_garde_les_sources_et_dedoublonne(self):
        pages = [
            {
                "href": "https://www.unicaen.fr/formations/master-cyber",
                "title": "Master Cybersécurité — Université de Caen",
                "body": "Admission et prérequis du Master cybersécurité.",
            },
            {
                "href": "https://www.unicaen.fr/formations/master-cyber",
                "title": "Copie du même résultat",
                "body": "Master cybersécurité admission.",
            },
            {
                "href": "https://example.com/master-cyber",
                "title": "Master cybersécurité",
                "body": "Formation et admission.",
            },
        ]
        moteur = self.moteur_simule(resultats=[pages, [], []])

        resultats = moteur_recherche.chercher_pages(
            "Cybersécurité", "Master", maximum=8
        )

        self.assertEqual(len(resultats), 2)
        self.assertTrue(resultats[0]["Source institutionnelle probable"])
        self.assertEqual(
            resultats[0]["Mode de découverte"],
            "Recherche Web multi-moteur",
        )
        self.assertIn("Admission", resultats[0]["Extrait du moteur de recherche"])
        self.assertEqual(moteur.text.call_args.kwargs["backend"], "auto")

    def test_panne_web_utilise_le_catalogue_sans_fausse_preuve(self):
        self.moteur_simule(erreur=RuntimeError("panne simulée"))

        resultats = moteur_recherche.chercher_pages(
            "Cybersécurité", "Master", maximum=8
        )

        self.assertEqual(len(resultats), 4)
        self.assertTrue(all(
            page["Mode de découverte"].startswith("Catalogue local")
            for page in resultats
        ))
        self.assertTrue(all(
            not page["Extrait du moteur de recherche"]
            and page["Description catalogue (non vérifiée)"]
            for page in resultats
        ))
        self.assertTrue(all(page["Erreurs recherche"] for page in resultats))

    def test_catalogue_secours_ne_couvre_pas_les_autres_domaines(self):
        self.moteur_simule(erreur=RuntimeError("panne simulée"))

        resultats = moteur_recherche.chercher_pages(
            "Data Science", "Licence", maximum=8
        )

        self.assertEqual(resultats, [])


if __name__ == "__main__":
    unittest.main()
