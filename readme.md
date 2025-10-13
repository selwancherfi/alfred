# Alfred – Version 2.1 (Mémoire stable)

Assistant personnel IA basé sur Streamlit, GPT-4 et Google Drive.

---

## 🚀 Fonctionnalités principales
- Mémoire persistante (RAM + Google Drive JSON)
- Journalisation quotidienne automatique
- Suppression des souvenirs avec confirmation visuelle
- Analyse de fichiers uploadés (TXT, PDF, DOCX, CSV)
- Interface sécurisée avec mot de passe

---

## 🧠 Fichiers principaux
- `alfred.py` → Interface utilisateur Streamlit
- `memoire_alfred.py` → Mémoire persistante et logs
- `router.py` → Routage des intentions utilisateur
- `interpreteur.py` → Interprétation naturelle des commandes
- `connexiongoogledrive.py` → Authentification compte de service
- `requirements.txt` → Liste des dépendances

---

## 🔧 Lancement local
```powershell
cd "C:\Users\Selwan\Documents\Alfred\git_project\alfred"
.\venv\Scripts\activate
streamlit run alfred.py

---

## 📄 Licence
Projet privé © 2025 Selwan Cherfi – Tous droits réservés.

