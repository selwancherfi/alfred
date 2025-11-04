🧠 Alfred – Journal de versions
v2.4 – Consolidation complète et stabilité majeure (23/10/2025)

Tag Git : v2.4-stable

🔧 Objectif

Stabiliser l’ensemble du système après plusieurs refactorings successifs.
L’enjeu était de restaurer la cohérence entre briques (mémoire, routeur, drive, interface) tout en ajoutant la suppression confirmée des souvenirs et en sécurisant les commandes sensibles.

🧩 Changements majeurs
🔹 Architecture et cohérence

Recentrage du routage des commandes :

Le router.py ne gère que les actions liées au Drive.

Toutes les commandes mémoire reviennent dans memoire_alfred.py.

Retour clair None / dict selon la gestion ou non d’une action (→ évite les erreurs et doublons).

Consolidation du pare-feu mémoire/drive pour éviter les confusions de contexte.

Réintégration propre du hook de raisonnement avec souvenirs (answer_with_memories).

🔹 Mémoire

Rétablissement complet des capacités :

Ajout, rappel, liste, filtrage par catégorie, suppression sécurisée.

NLU enrichie et tolérante (variantes “oublie”, “efface”, “supprime le souvenir sur…”).

Payload de confirmation → bannière dans Streamlit avec boutons “Confirmer / Annuler”.

Amélioration du formatage de la liste des souvenirs (datés et ordonnés).

Réintroduction de la prise en compte contextuelle dans les réponses du LLM.

Compatibilité multi-retour (tuples à 2/3/4 valeurs pour éviter les erreurs unpacking).

🔹 Drive

Suppression confirmée par nom (plus fiable que par ID).

Confirmation obligatoire avant toute opération destructive.

Meilleure gestion des erreurs API (error / warning / info / success).

Intégration avec le routeur harmonisée avec la logique mémoire.

🔹 Interface (Streamlit)

Réintroduction du prompt interactif après refactor (barre de saisie restaurée).

Bannière de confirmation pour les suppressions (souvenirs et Drive).

Restauration du fil du chat pour conserver le contexte complet (commandes et réponses).

Sidebar allégée (les souvenirs ne sont plus affichés en permanence, seulement sur demande).

🧠 Résultat

Alfred retrouve une stabilité complète et un comportement cohérent entre mémoire, raisonnement et interface.

Les suppressions (Drive et souvenirs) sont désormais fiables, sécurisées et confirmées.

Le raisonnement est à nouveau contextualisé par les souvenirs pertinents.

L’architecture redevient proprement modulaire, conformément à la philosophie d’Alfred v2.

v2.3 – Mémoire contextuelle pondérée + catégories actives (17/10/2025)

Ajout du raisonnement pondéré par contexte (sélection automatique des souvenirs les plus pertinents).

Conservation et exploitation cohérente des catégories.

Pondération par récence et correspondance lexicale.

Interface : affichage des souvenirs utilisés dans la réponse.

Stabilité confirmée (aucune erreur mémoire).
Tag Git : v2.3-stable

v2.2 – Raisonnement + souvenirs (16/10/2025)

Intégration du raisonnement mémoire dans les réponses.

Mémoire persistante fonctionnelle.

Correction des imports et dépendances.

v2.1 – Mémoire persistante + modèle configurable (15/10/2025)

Création de la mémoire persistante locale (JSON).

Sélecteur de modèle GPT (3.5 / 4 / 5).

Base stable pour extensions futures.

v2.0 – Architecture modulaire initiale (14/10/2025)

Passage officiel à Alfred v2 : architecture modulaire orchestrée via Streamlit.

Séparation en briques indépendantes :

LLM

Lecture fichiers

Drive

Interpréteur

Routeur

Mémoire

Création d’un pare-feu logique entre les briques et introduction du système de feedback utilisateur.

🧩 Prochaine étape : v2.5 (prévue)

Sauvegarde des souvenirs sur Drive (persistance cloud).

Édition inline des souvenirs.

Navigation Drive par chemin complet.

Sélecteur d’éléments en cas d’homonymes.

Préparation à l’intégration du module de notifications (brique N8N).