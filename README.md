# Générateur de Fiches Pédagogiques - Bénin

Générateur intelligent de fiches pédagogiques conformes au système éducatif béninois (CI au CM2).

## Fonctionnalités

- Génération de fiches pédagogiques respectant le canevas officiel béninois
- Support multi-provider IA : OpenAI, Claude, Gemini, Groq, OpenRouter, Cerebras, GLM
- **Sous-matières** : ex. Français → Conjugaison, Orthographe, Lecture, Vocabulaire thématique, Communication orale… (voir `matieres.py`)
- **Mode édition** : modifier la fiche générée et régénérer les .docx / .pdf
- **Espace administration** (`?admin=<token>`) :
  - Documents internes catégorisés (canevas, fiches de référence, mesures correctives, règles par niveau, règles par matière) injectés au prompt
  - Instructions système permanentes (prompt admin)
- Base de connaissances pré-chargée (19 documents, 332 pages)
- Upload de documents PDF (principal + complémentaires)
- Export Markdown / Word (.docx) / PDF
- Dockerfile + fly.toml prêts pour un déploiement (voir [DEPLOY.md](DEPLOY.md))

## Installation

```bash
pip install flask python-docx reportlab pymupdf requests
```

Pour la conversion PDF, installer LibreOffice :
```bash
sudo apt-get install libreoffice-writer-nogui
```

## Lancement

```bash
python app.py
```

L'application sera accessible sur `http://localhost:3000`.

### Comptes utilisateur (Supabase Auth)

L'authentification s'appuie désormais sur **Supabase Auth**. Configure ces variables d'environnement :

```bash
export SUPABASE_URL="https://<projet>.supabase.co"
export SUPABASE_ANON_KEY="..."          # clé publique
export SUPABASE_SERVICE_ROLE_KEY="..."  # clé serveur (secret)
export SUPABASE_DB_URL="postgresql://..."  # facultatif, pour les migrations
```

Applique le schéma initial (idempotent) :

```bash
psql "$SUPABASE_DB_URL" -f migrations/001_initial_schema.sql
```

Démarre l'app, puis :

1. Crée un compte via **`/signup`** (email + mot de passe)
2. Promeus ce compte au rang d'admin :

   ```bash
   python scripts/promote_admin.py mon-email@example.com
   ```

   Tu peux aussi définir `ADMIN_BOOTSTRAP_EMAIL=mon-email@example.com` au démarrage : le profil sera promu automatiquement au prochain boot.

3. Reconnecte-toi via **`/login`**. Les onglets « Espace Administration » s'affichent quand `is_admin = true`.

## Utilisation

1. Choisir le fournisseur IA et entrer la clé API
2. Renseigner les paramètres (matière, niveau, SA, séquence, type de fiche)
3. Uploader un PDF principal et/ou des documents complémentaires
4. Ajouter des instructions métier si nécessaire
5. Cliquer "Générer la fiche"
6. Télécharger en Word ou PDF

## Structure

```
├── app.py                  # Application Flask principale
├── llm_providers.py        # Abstraction multi-provider IA
├── pdf_processor.py        # Extraction de texte PDF
├── knowledge_base.py       # Recherche dans la base de connaissances
├── document_generator.py   # Génération Word/PDF
├── templates/
│   └── index.html          # Interface web
├── static/
│   ├── style.css           # Styles
│   └── app.js              # JavaScript frontend
├── knowledge_base/         # Base de connaissances pré-extraite
├── uploads/                # Documents uploadés
└── generated/              # Fiches générées
```
