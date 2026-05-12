# Déploiement

Cette application est un **serveur Flask** (Python) qui utilise `pymupdf` et
`libreoffice` pour l'extraction et la conversion PDF. Elle nécessite donc
un hébergement capable d'exécuter Python + des binaires système — ce que
Cloudflare Pages seul ne permet pas (Pages sert uniquement des sites
statiques / Workers).

La recette recommandée est : **héberger le backend sur un provider
Python (Fly.io / Render / Railway) puis mettre Cloudflare devant** (DNS,
cache, certificats, protection) via un CNAME ou un Tunnel Cloudflare.

---

## Option 1 — Fly.io (recommandée, gratuit possible)

Pré-requis : installer `flyctl` et se connecter (`flyctl auth login`).

```bash
# Depuis la racine du repo
flyctl launch --no-deploy --copy-config --name fiche-de-cour
flyctl deploy
```

L'app sera accessible sur `https://fiche-de-cour.fly.dev`.

### Mettre Cloudflare devant l'app Fly.io

1. Dans Cloudflare, ajoute un enregistrement **CNAME** :
   `app.tondomaine.com → fiche-de-cour.fly.dev` (proxy "orange cloud" activé).
2. Sur Fly.io, associe le domaine : `flyctl certs add app.tondomaine.com`.
3. Cloudflare émet automatiquement un certificat Universal SSL.

C'est la façon la plus simple d'avoir "Cloudflare devant" une app Python.

---

## Option 2 — Cloudflare Tunnel (tu héberges l'app, Cloudflare la publie)

Cloudflare Tunnel permet d'exposer un serveur local (sur ton PC, un VPS,
une VM) via ton domaine Cloudflare, sans ouvrir de port.

```bash
# 1. Démarrer le serveur localement (ou sur le VPS)
docker build -t fiche-de-cour .
docker run -p 8080:8080 fiche-de-cour

# 2. Installer cloudflared et créer un tunnel
cloudflared tunnel login
cloudflared tunnel create fiche-de-cour
cloudflared tunnel route dns fiche-de-cour app.tondomaine.com
cloudflared tunnel run --url http://localhost:8080 fiche-de-cour
```

L'app devient accessible sur `https://app.tondomaine.com` via Cloudflare.

---

## Option 3 — Render (très simple, clic-bouton)

1. Connecte ton repo GitHub sur https://render.com.
2. "New → Web Service", pointe sur ce repo.
3. Render détecte le `Dockerfile` et déploie automatiquement.
4. Facultatif : CNAME Cloudflare vers `<service>.onrender.com`.

---

## Lancer localement

```bash
pip install -r requirements.txt
python app.py
# http://localhost:3000
```

Ou avec Docker :

```bash
docker build -t fiche-de-cour .
docker run -p 8080:8080 fiche-de-cour
# http://localhost:8080
```
