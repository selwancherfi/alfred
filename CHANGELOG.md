\# 🧠 Alfred – Journal de versions


## v2.4 – Pilotage mémoire interactif + feedback utilisateur (17/10/2025)
- Ajout d’un **pilotage mémoire complet** : Alfred affiche désormais les souvenirs utilisés dans la réponse.
- Introduction d’un système de **feedback interactif** :
  - 👍 / 👎 pour ajuster la pertinence perçue d’un souvenir (influence durable sur les futurs scores).
  - 📌 pour forcer un souvenir dans la prochaine réponse.
  - 🙈 pour masquer un souvenir temporairement.
- Mise en place d’un **score pondéré dynamique** intégrant récence, similarité, importance et feedback.
- Sidebar enrichie : affichage du score, de la source (catégorie/domaine/libre), et filtres mémoire actifs.
- Compatibilité avec les futures **règles de classification automatique** (par domaine et catégorie).
- Suppression des fichiers de test (`alfred - Copie.py`, `memoire_alfred - Copie.py`) pour nettoyage du dépôt.
- Stabilité confirmée : toutes les fonctions mémoire, raisonnement et interface testées avec succès.
- Tag Git : `v2.4-stable`



\## v2.3 – Mémoire contextuelle pondérée + catégories actives (17/10/2025)

\- Ajout du raisonnement pondéré par contexte (recherche des souvenirs les plus pertinents selon le prompt)

\- Conservation et utilisation cohérente des catégories de souvenirs

\- Pondération par récence et correspondance sémantique

\- Interface améliorée : affichage des souvenirs utilisés dans la réponse

\- Stabilité confirmée : zéro erreur, cohérence des données mémoire

\- Tag Git : `v2.3-stable`



\## v2.2 – Raisonnement + souvenirs (16/10/2025)

\- Alfred peut désormais utiliser ses souvenirs dans ses réponses

\- Mémoire persistante fonctionnelle

\- Correction des imports et erreurs de modules



\## v2.1 – Mémoire persistante + modèle configurable (15/10/2025)

\- Création de la mémoire persistante JSON

\- Sélecteur de modèle GPT (3.5 / 4 / 5)

\- Base stable pour les futures extensions



