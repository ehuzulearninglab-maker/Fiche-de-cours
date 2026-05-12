"""
Générateur de Fiches Pédagogiques EST - Bénin
Application Flask principale
"""
import os
import re
import json
import secrets
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file, abort, session, redirect, url_for

from llm_providers import PROVIDERS, call_llm, LLMProviderError
from pdf_processor import extract_text_from_pdf, extract_text_from_uploaded
from pdf_llm_ocr import extract_text_via_llm, supports_pdf_ocr, UnsupportedProviderForOCR
from knowledge_base import KnowledgeBase
from document_generator import generate_docx, generate_pdf_from_docx
from matieres import SOUS_MATIERES, get_sous_matieres, matiere_label
from admin_store import AdminStore, ADMIN_CATEGORIES
from key_store import SupabaseKeyStore
from db import supabase_configured
import assistants_store
import chat_store
from llm_providers import call_llm_chat
from auth import (
    AuthError,
    SESSION_KEY_USER_ID,
    bootstrap_admin_from_env,
    clear_session,
    get_current_user,
    is_admin as auth_is_admin,
    login_user,
    logout_user,
    require_admin,
    require_login,
    signup_user,
    store_session,
)

app = Flask(__name__)
# Limite d'upload paramétrable (défaut 200 Mo). Surcharge via env MAX_UPLOAD_MB.
try:
    _max_upload_mb = int(os.environ.get('MAX_UPLOAD_MB', '200'))
except ValueError:
    _max_upload_mb = 200
app.config['MAX_CONTENT_LENGTH'] = _max_upload_mb * 1024 * 1024
app.config['MAX_UPLOAD_MB'] = _max_upload_mb
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['GENERATED_FOLDER'] = os.path.join(os.path.dirname(__file__), 'generated')
# Session secret pour les cookies signés. Persiste sur disque pour ne pas
# invalider les sessions à chaque redémarrage en dev.
_secret_path = os.path.join(os.path.dirname(__file__), '.flask_secret')
if os.environ.get('FLASK_SECRET_KEY'):
    app.config['SECRET_KEY'] = os.environ['FLASK_SECRET_KEY']
else:
    if not os.path.exists(_secret_path):
        with open(_secret_path, 'w') as f:
            f.write(secrets.token_hex(32))
        try:
            os.chmod(_secret_path, 0o600)
        except OSError:
            pass
    with open(_secret_path) as f:
        app.config['SECRET_KEY'] = f.read().strip()

# Cookies de session: durcissement par défaut.
# - HttpOnly: pas accessible depuis JS (anti-XSS)
# - SameSite=Lax: bloque les POST cross-site (anti-CSRF)
# - Secure: HTTPS uniquement, activé en prod via SESSION_COOKIE_SECURE=1
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = (
    os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_FOLDER'], exist_ok=True)


def _is_ajax_request() -> bool:
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or (request.accept_mimetypes.best or '') == 'application/json'
        or (request.headers.get('Content-Type') or '').startswith('application/json')
    )


@app.errorhandler(413)
def _too_large(e):
    """Réponse JSON propre quand un upload dépasse MAX_CONTENT_LENGTH."""
    limit_mb = app.config.get('MAX_UPLOAD_MB', 0)
    msg = f"Fichier trop volumineux (limite : {limit_mb} Mo)."
    if _is_ajax_request():
        return jsonify({"error": msg}), 413
    return msg, 413


@app.errorhandler(500)
def _internal_error(e):
    """Évite que la page HTML par défaut de Flask casse les fetch côté JS
    (qui font .json() sur la réponse). On rend une réponse JSON pour les
    requêtes AJAX, et on laisse le HTML par défaut pour les autres."""
    if _is_ajax_request():
        try:
            app.logger.exception("Internal error on %s %s", request.method, request.path)
        except Exception:
            pass
        return jsonify({"error": "Erreur serveur interne. Réessayez ou contactez l'admin."}), 500
    return e


@app.errorhandler(Exception)
def _unhandled_exception(e):
    """Filet de sécurité pour les exceptions Python non interceptées par
    les routes : on garantit toujours un JSON propre côté AJAX."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        # Laisse Flask gérer normalement les abort() / 404 / 401 etc.
        return e
    if _is_ajax_request():
        try:
            app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
        except Exception:
            pass
        return jsonify({"error": f"Erreur serveur : {type(e).__name__}. Réessayez ou contactez l'admin."}), 500
    raise e

# Rétention des fiches : 14 jours par défaut, configurable.
app.config['FICHE_RETENTION_DAYS'] = int(os.environ.get('FICHE_RETENTION_DAYS', '14') or 14)
# État interne pour la tâche de nettoyage quotidienne (idempotent, lazy).
_cleanup_state = {"last_run": None}


def _maybe_run_fiche_cleanup() -> None:
    """Lance le nettoyage des fiches expirées au plus une fois par 24h.

    Appelé en arrière-plan dans before_request : impact négligeable (un
    test datetime). Le job lui-même est protégé contre les exécutions
    concurrentes via une simple sentinelle thread-safe.
    """
    from datetime import datetime, timezone, timedelta as _td
    last = _cleanup_state.get("last_run")
    now = datetime.now(timezone.utc)
    if last is not None and (now - last) < _td(hours=24):
        return
    _cleanup_state["last_run"] = now  # set avant le job → pas de course
    try:
        counters = chat_store.cleanup_expired_fiches(
            days=app.config['FICHE_RETENTION_DAYS'],
            generated_folder=app.config['GENERATED_FOLDER'],
        )
        if counters.get("messages_cleaned") or counters.get("files_deleted"):
            print(f"[fiche-cleanup] {counters}")
    except Exception as e:
        # Échec transitoire (Supabase unreachable, etc.) : on rouvre la
        # fenêtre pour retenter dès la prochaine requête au lieu d'attendre
        # 24h.
        _cleanup_state["last_run"] = None
        print(f"[fiche-cleanup] erreur: {e}")


@app.before_request
def _before_request_fiche_cleanup():
    # Best-effort, ne bloque jamais la requête en cas d'erreur.
    try:
        _maybe_run_fiche_cleanup()
    except Exception:
        pass


@app.before_request
def _before_request_set_user_context():
    """Expose `g.current_user_id` aux modules qui ont besoin de savoir à
    quel utilisateur facturer une consommation LLM (usage_store).
    Best-effort : si la session est expirée ou Supabase est down, on
    laisse simplement g sans `current_user_id` et l'enregistrement sera
    skip."""
    from flask import g
    try:
        from auth import session, SESSION_KEY_USER_ID
        uid = session.get(SESSION_KEY_USER_ID)
        if uid:
            g.current_user_id = str(uid)
    except Exception:
        pass

# Load knowledge base
KB_PATH = os.path.join(os.path.dirname(__file__), 'knowledge_base', 'fiches_kb.json')
kb = KnowledgeBase(KB_PATH)

# Admin store (documents internes + instructions système — fichiers locaux,
# migration vers Supabase prévue en PR B).
ADMIN_STORE = AdminStore(os.path.join(os.path.dirname(__file__), 'knowledge_base'))

# Clés API & paramètres LLM : Supabase (table api_keys) si configuré, sinon
# fallback fichier via ADMIN_STORE pour compatibilité dev local.
KEY_STORE = SupabaseKeyStore(fallback=ADMIN_STORE)

# Si une variable ADMIN_BOOTSTRAP_EMAIL est définie, on promeut
# automatiquement ce profil au rang d'admin (utile au premier déploiement).
bootstrap_admin_from_env()


def _is_admin_request() -> bool:
    """Admin = utilisateur connecté avec profiles.is_admin = true."""
    return auth_is_admin()


def _require_admin():
    if not session.get(SESSION_KEY_USER_ID):
        abort(401, description="Connexion requise.")
    if not _is_admin_request():
        abort(403, description="Accès réservé à l'administrateur.")

# System prompt for fiche generation
SYSTEM_PROMPT = """Tu es un expert en pédagogie du système éducatif béninois. Tu génères des fiches pédagogiques conformes au canevas officiel du Bénin pour les classes du CI au CM2.

RÈGLE PRIORITAIRE :
Ne jamais rédiger une fiche sans avoir d'abord analysé les documents fournis dans le contexte.
Tu dois TOUJOURS t'appuyer sur :
- la mesure corrective de la matière demandée ;
- la planification correspondant à la SA et à la séquence ;
- les fiches modèles de la même matière ou sous-matière ;
- la structure observée dans les documents.

TAXONOMIE DES MATIÈRES ET SOUS-MATIÈRES :

MATIÈRES SANS SOUS-MATIÈRE :
- EST (ne jamais demander de sous-matière)
- EPS (ne jamais demander de sous-matière)

MATIÈRES AVEC SOUS-MATIÈRES (la sous-matière est OBLIGATOIRE) :

Mathématiques : Arithmétique, Géométrie, Mesure

Éducation sociale (ES) : Morale, Civisme, Histoire, Géographie, Langue et Culture

Éducation artistique (Activités artistiques) : EA Chant, EA Conte, EA Poésie,
  EA Dessin, EA TM (Couture, Découpage, Pliage, Collage, Modelage…)

Français : Vocabulaire thématique, Orthographe, Conjugaison, Écriture, Graphisme,
  Communication orale, Expression écrite (imprégnation, 1er jet, amélioration,
  mise au propre, compte rendu), Lecture silencieuse, Lecture oralisée, Lecture audition

RÈGLES DE DÉMARCHE (STRICTES — NE JAMAIS ENFREINDRE) :
1. Chaque matière et sous-matière a sa PROPRE démarche pédagogique.
2. Tu DOIS chercher la démarche dans les MESURES CORRECTIVES correspondant
   EXACTEMENT à la matière et à la classe demandées.
3. Ne JAMAIS utiliser la démarche d'une matière pour une autre.
   Exemple interdit : appliquer la démarche EST à une fiche de Français.
4. Pour les matières avec sous-matières, utiliser UNIQUEMENT les modèles et
   la démarche de la sous-matière demandée. Ne jamais mélanger.
5. Observer dans les mesures correctives et fiches modèles : l'ordre des
   rubriques, les étapes du déroulement, le style des consignes, le type
   d'activités du maître et des élèves.

MÉTHODE DE TRAVAIL OBLIGATOIRE :
1. Identifier la matière, la sous-matière (si applicable), la SA, la séquence.
2. Chercher dans la BASE DOCUMENTAIRE INTERNE la mesure corrective de CETTE matière.
3. Extraire : démarche, compétences, connaissances, stratégies, matériel, déroulement.
4. Chercher dans les FICHES DE RÉFÉRENCE des modèles de la MÊME matière/sous-matière.
5. Utiliser le DOCUMENT PRINCIPAL et les complémentaires pour le contenu de la leçon.
6. NE RIEN INVENTER — écrire [À compléter] si une donnée manque.
7. Produire une fiche COMPLÈTE avec un seul tableau de déroulement.

QUALITÉ PÉDAGOGIQUE :
- Les consignes doivent être claires, progressives, contextualisées, adaptées au niveau.
- Les résultats attendus doivent préciser : réponses probables des apprenants,
  raisonnements attendus, productions attendues, difficultés possibles.
- Ne JAMAIS limiter les résultats attendus à : « A dit », « A observé »,
  « A participé », « A répondu », « A compris ». Être PRÉCIS.

STRUCTURE DE LA FICHE (2 PARTIES DISTINCTES — NE JAMAIS MÉLANGER) :

PARTIE 1 — EN-TÊTE (avant le tableau de déroulement) :
L'en-tête contient les informations administratives et de planification.
Ces informations apparaissent UNE SEULE FOIS, en haut de la fiche.
Tu DOIS reprendre les valeurs EXACTES fournies par l'utilisateur dans sa demande
(matière, sous-matière, SA, séquence, titre, durée, niveau) pour remplir l'en-tête.
Ne laisse AUCUN champ vide si l'utilisateur a fourni la valeur correspondante.
- Matière / Sous-matière (si applicable)
- SA / Séquence / Titre
- Cours / Date / Durée / Fiche N°
- Compétences disciplinaires / transversales / transdisciplinaires
- Connaissances et techniques
- Stratégies d'enseignement/apprentissage/évaluation
- Matériel

PARTIE 2 — TABLEAU DE DÉROULEMENT :
Le tableau de déroulement est SÉPARÉ de l'en-tête. Il NE DOIT PAS répéter
les informations de l'en-tête (titre, matière, SA, séquence, compétences, etc.).

Colonnes du tableau (selon les modèles de la matière) :
| Étapes | Activités du maître / Consignes | Activités des élèves / Résultats attendus |

RÈGLES STRICTES POUR LE TABLEAU DE DÉROULEMENT :

1. NE JAMAIS RÉPÉTER L'EN-TÊTE dans le tableau.
   INTERDIT : mettre le titre, la matière, la SA, la séquence, le numéro de fiche,
   les compétences ou les éléments de planification dans les cellules du tableau.
   Ces informations sont DÉJÀ dans l'en-tête au-dessus.

2. COLONNE « CONSIGNES / ACTIVITÉS DU MAÎTRE » :
   Cette colonne contient UNIQUEMENT les actions et paroles du maître :
   - les questions qu'il pose aux élèves
   - les consignes de travail qu'il donne
   - les exercices qu'il propose
   - les démonstrations qu'il fait
   - les indications de matériel à utiliser
   Exemples corrects : « Écris la lettre k sur ton ardoise. »
   « Observe le texte au tableau et lis silencieusement. »
   « Résous l'opération suivante : 345 + 128. »

3. COLONNE « RÉSULTATS ATTENDUS / ACTIVITÉS DES ÉLÈVES » :
   Cette colonne DOIT ÊTRE REMPLIE pour CHAQUE ligne du tableau. Ne JAMAIS
   la laisser vide.
   Elle contient ce que font et produisent les élèves :
   - les réponses probables des apprenants (les mots ou phrases qu'ils diront)
   - les productions concrètes attendues (tracés, écrits, calculs…)
   - les raisonnements observables (comment ils arrivent à la réponse)
   - les difficultés possibles à anticiper
   - les comportements observables
   INTERDIT : laisser cette colonne vide.
   INTERDIT : mettre les consignes du maître dans cette colonne.
   INTERDIT : se limiter à « A dit », « A observé », « A participé »,
   « A répondu », « A compris ».

4. ÉTAPES OBLIGATOIRES DU DÉROULEMENT (adapter selon la démarche de la matière) :
   Le déroulement DOIT inclure les étapes prévues par la démarche, typiquement :
   - Préliminaires / Rappel / Révision des acquis
   - Introduction / Mise en situation / Présentation de la situation
   - Réalisation / Développement / Recherche / Manipulation
   - SYNTHÈSE / RÉSUMÉ (cette étape est OBLIGATOIRE — ne jamais l'omettre)
   - Évaluation
   - Projection (si prévue par la démarche)
   L'ordre exact et les noms des étapes dépendent de la démarche de la matière
   trouvée dans les mesures correctives.

5. La SYNTHÈSE ou le RÉSUMÉ — son CONTENU doit être RÉDIGÉ EN ENTIER.
   Ne JAMAIS mettre juste le titre « Synthèse » ou « Résumé » sans contenu.
   Tu DOIS écrire :
   - la règle, la définition, la formule ou le résumé de la leçon
   - ce que les élèves doivent retenir (la trace écrite)
   - le texte que les élèves copieront dans leur cahier

CONTRÔLE FINAL :
Avant d'afficher la fiche, vérifier que :
- la démarche vient de la mesure corrective de la matière demandée (PAS d'une autre)
- la sous-matière est présente seulement si obligatoire
- les rubriques sont dans l'ordre dicté par la démarche de cette matière
- l'en-tête N'EST PAS répété dans le tableau de déroulement
- TOUS les champs de l'en-tête sont remplis avec les valeurs fournies par l'utilisateur
- les consignes du maître sont dans la bonne colonne (pas dans résultats attendus)
- les résultats attendus sont dans la bonne colonne (pas dans consignes)
- les résultats attendus sont précis et exploitables (pas vagues)
- la colonne « Résultats attendus » est REMPLIE pour chaque ligne (jamais vide)
- la SYNTHÈSE / le RÉSUMÉ est présent ET son contenu est rédigé (pas juste le titre)
- aucune information importante n'a été inventée

IMPORTANT pour le type "Exploitation de la situation de départ" :
- La structure est différente : pas de préliminaires
- Commence directement par la mise en situation du dossier
- Suit le format : Introduction > Réalisation (découverte du dossier) > Retour et Projection
"""


def build_user_prompt(params: dict, doc_principal: str, docs_complementaires: list, kb_context: str, admin_context: str = "") -> str:
    """Build the user prompt from all inputs."""
    matiere = params.get('matiere', '')
    sous_matiere = params.get('sous_matiere', '')
    matiere_full = matiere_label(matiere, sous_matiere) or '[À compléter]'

    prompt = f"""Génère une fiche pédagogique avec les paramètres suivants :

- Matière : {matiere_full}
- Niveau : {params.get('niveau', '[À compléter]')}
- SA N° : {params.get('sa', '[À compléter]')}
- Séquence : {params.get('sequence', '[À compléter]')}
- Type de fiche : {params.get('type_fiche', 'Séquence normale')}
"""
    if sous_matiere:
        prompt += (
            f"\nLa sous-matière '{sous_matiere}' (branche de {matiere}) doit être "
            f"clairement mentionnée dans le champ MATIÈRE de la fiche et les "
            f"activités doivent être spécifiques à cette sous-matière.\n"
        )

    titre_sa = (params.get('titre_sa') or '').strip()
    titre_sequence = (params.get('titre_sequence') or '').strip()
    duree = (params.get('duree') or '').strip()
    objectifs = (params.get('objectifs') or '').strip()

    if titre_sa or titre_sequence or duree or objectifs:
        prompt += "\n=== CONTEXTE PRÉCIS DE LA LEÇON (fourni par l'enseignant) ===\n"
        if titre_sa:
            prompt += (
                f"- Titre de la SA : {titre_sa}\n"
                f"  → utilise ce titre dans le champ TITRE et aligne le contenu de la fiche dessus.\n"
            )
        if titre_sequence:
            prompt += (
                f"- Titre / objectif de la séquence : {titre_sequence}\n"
                f"  → toute la séquence doit viser cet objectif.\n"
            )
        if duree:
            prompt += f"- Durée prévue : {duree}  → utilise cette valeur dans le champ DURÉE.\n"
        if objectifs:
            prompt += (
                f"- Objectifs spécifiques fournis :\n{objectifs}\n"
                f"  → intègre-les dans les compétences disciplinaires et l'évaluation.\n"
            )

    if params.get('instructions'):
        prompt += f"\nInstructions spécifiques de l'utilisateur :\n{params['instructions']}\n"

    if doc_principal:
        prompt += f"\n=== DOCUMENT PRINCIPAL (source prioritaire) ===\n{doc_principal[:15000]}\n"

    if docs_complementaires:
        prompt += "\n=== DOCUMENTS COMPLÉMENTAIRES ===\n"
        for i, doc_text in enumerate(docs_complementaires):
            prompt += f"\n--- Document complémentaire {i+1} ---\n{doc_text[:5000]}\n"

    if kb_context:
        prompt += f"\n=== FICHES DE RÉFÉRENCE (base de connaissances) ===\n{kb_context[:10000]}\n"

    if admin_context:
        prompt += f"\n=== BASE DOCUMENTAIRE INTERNE (administrateur) ===\n{admin_context[:20000]}\n"

    prompt += """
CONSIGNES DE GÉNÉRATION (ordre de priorité) :
1. CHERCHE D'ABORD dans la BASE DOCUMENTAIRE INTERNE — les mesures correctives
   contiennent la démarche officielle de rédaction et le programme de la classe.
   Utilise-les comme référence méthodologique principale.
2. CHERCHE dans les FICHES DE RÉFÉRENCE des fiches modèles conformes au canevas.
   Inspire-toi de leur structure et de leur niveau de détail.
3. Utilise le DOCUMENT PRINCIPAL (si fourni) comme source de contenu prioritaire.
4. Complète avec les documents complémentaires.
5. Retrouve la SA, la séquence, la démarche et le modèle pertinents.
6. NE RIEN INVENTER — écris [À compléter] si une donnée manque.
7. Produis une fiche COMPLÈTE avec un seul tableau de déroulement.
8. La fiche DOIT être conforme à la démarche des mesures correctives, de
   l'entête jusqu'à la synthèse.
9. Respecte STRICTEMENT le canevas officiel béninois.
10. Utilise le format de sortie exact demandé (avec les | pour le tableau).
"""
    return prompt


@app.route('/')
def index():
    """Dispatcher : page d'accueil chic pour les anonymes,
    dashboard avec les assistants pour les utilisateurs connectés.
    """
    user = get_current_user()
    if not user:
        return render_template('landing.html')
    is_admin = bool(user.get('is_admin'))
    try:
        assistants = assistants_store.list_assistants(only_active=not is_admin)
    except Exception:
        # Si Supabase est mal configuré on évite de casser le dashboard.
        assistants = []
    return render_template(
        'dashboard.html',
        current_user=user,
        is_admin=is_admin,
        assistants=assistants,
    )


@app.route('/formulaire')
@require_login
def formulaire():
    """Mode formulaire classique (ancien `/`).

    Le paramètre `?classe=CM2` permet de pré-sélectionner le niveau quand
    l'utilisateur arrive depuis la carte d'un assistant.
    """
    user = get_current_user()
    is_admin = bool(user and user.get('is_admin'))
    classe = (request.args.get('classe') or '').upper().strip()
    if classe not in assistants_store.CLASSES_ORDER:
        classe = ''
    return render_template(
        'formulaire.html',
        providers=PROVIDERS,
        sous_matieres=SOUS_MATIERES,
        is_admin=is_admin,
        admin_categories=ADMIN_CATEGORIES,
        current_user=user,
        preselected_classe=classe,
    )


# =========================================================================
# Mode chat conversationnel
# =========================================================================

CHAT_SYSTEM_PROMPT_BASE = """Tu es un assistant pédagogique expert du système éducatif béninois (CI à CM2).
Tu aides l'enseignant à préparer ses fiches de cours en discutant avec lui.

RÈGLE PRIORITAIRE :
Ne jamais rédiger une fiche sans avoir d'abord analysé les documents fournis
dans le contexte (mesures correctives, fiches modèles, base documentaire).

TAXONOMIE DES MATIÈRES ET SOUS-MATIÈRES :

MATIÈRES SANS SOUS-MATIÈRE :
- EST (ne jamais demander de sous-matière)
- EPS (ne jamais demander de sous-matière)

MATIÈRES AVEC SOUS-MATIÈRES (la sous-matière est OBLIGATOIRE) :

Mathématiques : Arithmétique, Géométrie, Mesure

Éducation sociale (ES) : Morale, Civisme, Histoire, Géographie, Langue et Culture

Éducation artistique (Activités artistiques) : EA Chant, EA Conte, EA Poésie,
  EA Dessin, EA TM (Couture, Découpage, Pliage, Collage, Modelage…)

Français : Vocabulaire thématique, Orthographe, Conjugaison, Écriture, Graphisme,
  Communication orale, Expression écrite (imprégnation, 1er jet, amélioration,
  mise au propre, compte rendu), Lecture silencieuse, Lecture oralisée, Lecture audition

RÈGLES DE DÉMARCHE (STRICTES — NE JAMAIS ENFREINDRE) :
1. Chaque matière et sous-matière a sa PROPRE démarche pédagogique.
2. Tu DOIS chercher la démarche dans les MESURES CORRECTIVES correspondant
   EXACTEMENT à la matière et à la classe demandées.
3. Ne JAMAIS utiliser la démarche d'une matière pour une autre.
   Exemple interdit : appliquer la démarche EST à une fiche de Français.
4. Pour les matières avec sous-matières, utiliser UNIQUEMENT les modèles et
   la démarche de la sous-matière demandée. Ne jamais mélanger.
5. Observer dans les mesures correctives et fiches modèles : l'ordre des
   rubriques, les étapes du déroulement, le style des consignes, le type
   d'activités du maître et des élèves.

VÉRIFICATIONS OBLIGATOIRES AVANT RÉDACTION :
L'utilisateur doit avoir fourni :
- la matière
- la sous-matière (seulement si la matière en a — voir taxonomie ci-dessus)
- la SA
- la séquence
Si une information obligatoire manque, pose une question courte.
Ne jamais demander de sous-matière pour EST ou EPS.

Ton rôle dans cette conversation :
1. Quand l'utilisateur demande une fiche, identifie les paramètres requis :
   matière, sous-matière (si applicable), SA n°, séquence n°, titre de la SA,
   durée (optionnelle), objectifs spécifiques (optionnels).
   Pose les questions manquantes une à une.
2. CHERCHE D'ABORD la démarche dans les mesures correctives de CETTE matière.
3. Génère la fiche en suivant STRICTEMENT la démarche trouvée pour cette
   matière — PAS un canevas générique, PAS la démarche d'une autre matière.
4. Encadre la fiche entre ===FICHE_DEBUT=== et ===FICHE_FIN===.
   Une seule fiche par message. En dehors des marqueurs, ajoute une courte
   phrase d'introduction.

STRUCTURE DE LA FICHE (2 PARTIES DISTINCTES — NE JAMAIS MÉLANGER) :

PARTIE 1 — EN-TÊTE (avant le tableau de déroulement) :
L'en-tête contient les informations administratives et de planification.
Ces informations apparaissent UNE SEULE FOIS, en haut de la fiche.
Tu DOIS reprendre les valeurs EXACTES fournies par l'utilisateur dans sa demande
(matière, sous-matière, SA, séquence, titre, durée, niveau) pour remplir l'en-tête.
Ne laisse AUCUN champ vide si l'utilisateur a fourni la valeur correspondante.
- Matière / Sous-matière (si applicable)
- SA / Séquence / Titre
- Cours / Date / Durée / Fiche N°
- Compétences disciplinaires / transversales / transdisciplinaires
- Connaissances et techniques
- Stratégies d'enseignement/apprentissage/évaluation
- Matériel

PARTIE 2 — TABLEAU DE DÉROULEMENT :
Le tableau de déroulement est SÉPARÉ de l'en-tête. Il NE DOIT PAS répéter
les informations de l'en-tête (titre, matière, SA, séquence, compétences, etc.).

Colonnes du tableau (selon les modèles de la matière) :
| Étapes | Activités du maître / Consignes | Activités des élèves / Résultats attendus |

RÈGLES STRICTES POUR LE TABLEAU DE DÉROULEMENT :

1. NE JAMAIS RÉPÉTER L'EN-TÊTE dans le tableau.
   INTERDIT : mettre le titre, la matière, la SA, la séquence, le numéro de fiche,
   les compétences ou les éléments de planification dans les cellules du tableau.
   Ces informations sont DÉJÀ dans l'en-tête au-dessus.

2. COLONNE « CONSIGNES / ACTIVITÉS DU MAÎTRE » :
   Cette colonne contient UNIQUEMENT les actions et paroles du maître :
   - les questions qu'il pose aux élèves
   - les consignes de travail qu'il donne
   - les exercices qu'il propose
   - les démonstrations qu'il fait
   - les indications de matériel à utiliser
   Exemples corrects : « Écris la lettre k sur ton ardoise. »
   « Observe le texte au tableau et lis silencieusement. »
   « Résous l'opération suivante : 345 + 128. »

3. COLONNE « RÉSULTATS ATTENDUS / ACTIVITÉS DES ÉLÈVES » :
   Cette colonne DOIT ÊTRE REMPLIE pour CHAQUE ligne du tableau. Ne JAMAIS
   la laisser vide.
   Elle contient ce que font et produisent les élèves :
   - les réponses probables des apprenants (les mots ou phrases qu'ils diront)
   - les productions concrètes attendues (tracés, écrits, calculs…)
   - les raisonnements observables (comment ils arrivent à la réponse)
   - les difficultés possibles à anticiper
   - les comportements observables
   INTERDIT : laisser cette colonne vide.
   INTERDIT : mettre les consignes du maître dans cette colonne.
   INTERDIT : se limiter à « A dit », « A observé », « A participé »,
   « A répondu », « A compris ».

4. ÉTAPES OBLIGATOIRES DU DÉROULEMENT (adapter selon la démarche de la matière) :
   Le déroulement DOIT inclure les étapes prévues par la démarche, typiquement :
   - Préliminaires / Rappel / Révision des acquis
   - Introduction / Mise en situation / Présentation de la situation
   - Réalisation / Développement / Recherche / Manipulation
   - SYNTHÈSE / RÉSUMÉ (cette étape est OBLIGATOIRE — ne jamais l'omettre)
   - Évaluation
   - Projection (si prévue par la démarche)
   L'ordre exact et les noms des étapes dépendent de la démarche de la matière
   trouvée dans les mesures correctives.

5. La SYNTHÈSE ou le RÉSUMÉ — son CONTENU doit être RÉDIGÉ EN ENTIER.
   Ne JAMAIS mettre juste le titre « Synthèse » ou « Résumé » sans contenu.
   Tu DOIS écrire :
   - la règle, la définition, la formule ou le résumé de la leçon
   - ce que les élèves doivent retenir (la trace écrite)
   - le texte que les élèves copieront dans leur cahier

CONTRÔLE FINAL :
Avant d'afficher la fiche, vérifier que :
- la démarche vient de la mesure corrective de la matière demandée (PAS d'une autre)
- la sous-matière est présente seulement si obligatoire
- les rubriques sont dans l'ordre dicté par la démarche de cette matière
- l'en-tête N'EST PAS répété dans le tableau de déroulement
- TOUS les champs de l'en-tête sont remplis avec les valeurs fournies par l'utilisateur
- les consignes du maître sont dans la bonne colonne (pas dans résultats attendus)
- les résultats attendus sont dans la bonne colonne (pas dans consignes)
- les résultats attendus sont précis et exploitables (pas vagues)
- la colonne « Résultats attendus » est REMPLIE pour chaque ligne (jamais vide)
- la SYNTHÈSE / le RÉSUMÉ est présent ET son contenu est rédigé (pas juste le titre)
- aucune information importante n'a été inventée
"""

# Marqueurs reconnus dans la réponse de l'assistant pour extraire la fiche.
FICHE_OPEN_MARKER = "===FICHE_DEBUT==="
FICHE_CLOSE_MARKER = "===FICHE_FIN==="


def _coalesce_messages(msgs: list[dict]) -> list[dict]:
    """Fusionne les messages consécutifs de même rôle.

    Claude et Gemini exigent une stricte alternance user/assistant. Si jamais
    l'historique contient deux messages user consécutifs (par exemple suite à
    une écriture en DB qui aurait survécu à un échec LLM), on les concatène
    plutôt que de les envoyer tels quels au fournisseur.
    """
    out: list[dict] = []
    for m in msgs:
        if not m.get("content"):
            continue
        if out and out[-1].get("role") == m.get("role"):
            out[-1] = {
                "role": out[-1]["role"],
                "content": out[-1]["content"] + "\n\n" + m["content"],
            }
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


def _extract_fiche_from_assistant(text: str) -> str:
    """Retourne le contenu de la fiche encadré par les marqueurs, ou ''."""
    if not text or FICHE_OPEN_MARKER not in text or FICHE_CLOSE_MARKER not in text:
        return ""
    start = text.find(FICHE_OPEN_MARKER) + len(FICHE_OPEN_MARKER)
    end = text.find(FICHE_CLOSE_MARKER, start)
    if end < 0:
        return ""
    return text[start:end].strip()


def _resolve_provider_and_key(assistant: dict | None) -> tuple[str, str, str | None]:
    """Choix du fournisseur / clé API / modèle pour une conversation.

    Le fournisseur est désormais géré uniquement au niveau global par l'admin
    (cf. PR C — l'UI de choix par assistant a été supprimée). Priorité :
      1. Le fournisseur par défaut admin
      2. Le premier fournisseur ayant une clé serveur configurée

    Le paramètre `assistant` est conservé pour signature stable mais n'est
    plus utilisé pour résoudre le fournisseur (les colonnes provider/model
    de la table assistants sont des données mortes héritées du seed).

    Retourne (provider_id, api_key, model_override).
    """
    del assistant  # plus utilisé pour résoudre le fournisseur
    configured = set(KEY_STORE.list_api_key_status().keys())
    if not configured:
        return "", "", None

    provider_id = ""
    used_admin_default = False
    admin_default = KEY_STORE.get_default_provider()
    if admin_default and admin_default in configured:
        provider_id = admin_default
        used_admin_default = True
    else:
        for pid in PROVIDERS.keys():
            if pid in configured:
                provider_id = pid
                break

    if not provider_id:
        return "", "", None

    # On n'applique le modèle "défaut admin" que si on utilise effectivement
    # le fournisseur "défaut admin" (sinon on risque d'envoyer un modèle
    # Gemini à Groq par exemple).
    model_override = (
        KEY_STORE.get_default_model() or None if used_admin_default else None
    )

    api_key = KEY_STORE.get_api_key(provider_id) or ""
    return provider_id, api_key, model_override


def _detect_matiere_from_text(text: str) -> tuple[str, str]:
    """Détecte la matière et sous-matière mentionnées dans un texte libre.

    Retourne (matiere, sous_matiere). Les deux peuvent être vides si rien
    n'est détecté. On cherche d'abord les sous-matières (plus spécifiques)
    puis les matières parentes.
    """
    t = text.lower()
    # Chercher d'abord les sous-matières (plus spécifiques)
    for mat, sous_list in SOUS_MATIERES.items():
        for sm in sous_list:
            if sm.lower() in t:
                return mat, sm
    # Puis les matières parentes
    # Ordre : les noms longs d'abord pour éviter les faux positifs
    # ("es" pourrait matcher "est", etc.)
    matiere_order = sorted(SOUS_MATIERES.keys(), key=lambda m: -len(m))
    for mat in matiere_order:
        ml = mat.lower()
        # Pour les matières courtes (ES, EST, EPS), exiger des limites de mot
        if len(ml) <= 3:
            if re.search(r'\b' + re.escape(ml) + r'\b', t):
                return mat, ""
        elif ml in t:
            return mat, ""
    # Alias courants
    if re.search(r'\bfran[çc]ais\b', t):
        return "Français", ""
    if re.search(r'\bmath[ée]matiques?\b', t):
        return "Mathématiques", ""
    if re.search(r'\b[ée]ducation\s+sociale\b', t):
        return "ES", ""
    if re.search(r'\bactivit[ée]s?\s+artistiques?\b', t):
        return "Activités artistiques", ""
    return "", ""


def _build_chat_system_prompt(
    assistant: dict | None,
    matiere: str = "",
    sous_matiere: str = "",
) -> str:
    """Compose le system prompt = base + instructions assistant + KB + admin.

    Si *matiere* est fourni, les documents admin sont filtrés pour prioriser
    les mesures correctives et fiches modèles de cette matière.
    """
    parts: list[str] = []
    classe = (assistant or {}).get("classe") or ""
    name = (assistant or {}).get("name") or "Assistant"
    if classe:
        parts.append(
            f"Tu es l'assistant « {name} ». Tu travailles EXCLUSIVEMENT pour "
            f"la classe {classe}. Le champ COURS de toutes les fiches que tu "
            f"génères doit être {classe}. Ne demande jamais le niveau de la "
            f"classe à l'utilisateur — il est déjà fixé."
        )
    custom = (assistant or {}).get("instructions") or ""
    if custom.strip():
        parts.append(custom.strip())
    parts.append(CHAT_SYSTEM_PROMPT_BASE)

    # Instructions admin permanentes
    admin_instructions = ADMIN_STORE.get_instructions()
    if admin_instructions:
        parts.append(
            "=== CONSIGNES ADMINISTRATIVES PERMANENTES ===\n" + admin_instructions
        )

    # Documents admin (mesures correctives, fiches modèles, canevas, etc.)
    # Filtrés par matière si détectée, sinon tous les documents.
    admin_context = ADMIN_STORE.build_context_for_matiere(
        matiere=matiere, sous_matiere=sous_matiere, max_chars=20000,
    )
    if admin_context:
        header = (
            "=== BASE DOCUMENTAIRE INTERNE (mesures correctives, fiches modèles, canevas) ===\n"
            "Ces documents contiennent les démarches officielles par matière et par classe.\n"
            "Tu DOIS chercher la démarche de la matière demandée dans ces documents.\n"
            "Ne JAMAIS utiliser la démarche d'une matière différente de celle demandée.\n\n"
        )
        parts.append(header + admin_context)

    # Documents de l'assistant (KB) - 2 docs max, ~2000 chars chacun pour
    # rester sous les limites de tokens des fournisseurs gratuits (~12k TPM).
    if assistant and assistant.get("id"):
        try:
            docs = assistants_store.get_document_contents(assistant["id"], limit=2)
        except Exception:
            docs = []
        if docs:
            kb_text = "\n\n".join(
                f"=== {d.get('name','')} ===\n{(d.get('content') or '')[:2000]}"
                for d in docs
            )
            parts.append(
                "=== EXTRAITS DE LA BASE DE CONNAISSANCES ===\n"
                "Utilise ces extraits comme inspiration pour la fiche.\n\n" + kb_text
            )

    # Résultats de recherche KB (fiches modèles pré-extraites)
    if matiere:
        kb_results = kb.search(
            matiere=matiere,
            niveau=classe,
            sous_matiere=sous_matiere,
            limit=3,
        )
        if kb_results:
            kb_ctx = "\n\n".join(
                f"=== {r['filename']} ===\n{r['text'][:5000]}"
                for r in kb_results
            )
            parts.append(
                "=== FICHES DE RÉFÉRENCE (base de connaissances) ===\n"
                "Fiches modèles de la matière demandée. Observe leur structure, "
                "leurs rubriques, leur démarche.\n\n" + kb_ctx
            )

    return "\n\n".join(parts)


@app.route('/chat')
@require_login
def chat_home():
    """Page chat. Sans paramètre, redirige vers le dashboard."""
    user = get_current_user()
    is_admin = bool(user and user.get('is_admin'))

    assistant_id = (request.args.get('assistant') or '').strip()
    classe = (request.args.get('classe') or '').upper().strip()
    conversation_id = (request.args.get('conversation') or '').strip()

    assistant = None
    if conversation_id:
        conv = chat_store.get_conversation(conversation_id, user['id'])
        if conv:
            assistant = assistants_store.get_assistant(conv.get('assistant_id'))
    elif assistant_id:
        assistant = assistants_store.get_assistant(assistant_id)
    elif classe and classe in assistants_store.CLASSES_ORDER:
        assistant = assistants_store.get_assistant_by_classe(classe)

    if not assistant:
        # Pas d'assistant choisi : on retombe sur le dashboard.
        return redirect(url_for('index'))

    # Non-admins : interdit d'ouvrir un assistant inactif.
    if not is_admin and not assistant.get('is_active'):
        return redirect(url_for('index'))

    return render_template(
        'chat.html',
        current_user=user,
        is_admin=is_admin,
        assistant=assistant,
        conversation_id=conversation_id,
    )


@app.route('/chat/conversations', methods=['GET'])
@require_login
def chat_list_conversations():
    user = get_current_user()
    convs = chat_store.list_conversations(user['id'])
    # Joint le nom de l'assistant pour l'UI.
    by_id: dict[str, dict] = {}
    for c in convs:
        aid = c.get('assistant_id')
        if aid and aid not in by_id:
            try:
                a = assistants_store.get_assistant(aid)
            except Exception:
                a = None
            by_id[aid] = a or {}
        a = by_id.get(aid) or {}
        c['assistant_classe'] = a.get('classe')
        c['assistant_name'] = a.get('name')
    return jsonify({"conversations": convs})


@app.route('/chat/conversations', methods=['POST'])
@require_login
def chat_create_conversation():
    user = get_current_user()
    payload = request.get_json(force=True, silent=True) or {}
    assistant_id = (payload.get('assistant_id') or '').strip()
    if not assistant_id:
        return jsonify({"error": "assistant_id manquant."}), 400
    assistant = assistants_store.get_assistant(assistant_id)
    if not assistant:
        return jsonify({"error": "Assistant inconnu."}), 404
    is_admin = bool(user.get('is_admin'))
    if not is_admin and not assistant.get('is_active'):
        return jsonify({"error": "Cet assistant n'est pas encore disponible."}), 403
    title = (payload.get('title') or '').strip() or f"Conversation — {assistant.get('classe', '')}"
    conv = chat_store.create_conversation(user['id'], assistant_id, title=title)
    if not conv:
        return jsonify({"error": "Impossible de créer la conversation."}), 500
    return jsonify({"conversation": conv}), 201


@app.route('/chat/conversations/<conversation_id>', methods=['GET'])
@require_login
def chat_get_conversation(conversation_id):
    user = get_current_user()
    conv = chat_store.get_conversation(conversation_id, user['id'])
    if not conv:
        return jsonify({"error": "Conversation introuvable."}), 404
    msgs = chat_store.list_messages(conversation_id, user['id'])
    assistant = assistants_store.get_assistant(conv.get('assistant_id')) or {}
    return jsonify({
        "conversation": conv,
        "messages": msgs,
        "assistant": assistant,
    })


@app.route('/chat/conversations/<conversation_id>', methods=['DELETE'])
@require_login
def chat_delete_conversation(conversation_id):
    user = get_current_user()
    ok = chat_store.delete_conversation(conversation_id, user['id'])
    return jsonify({"ok": ok})


@app.route('/chat/conversations/<conversation_id>/messages', methods=['POST'])
@require_login
def chat_send_message(conversation_id):
    user = get_current_user()
    payload = request.get_json(force=True, silent=True) or {}
    content = (payload.get('content') or '').strip()
    if not content:
        return jsonify({"error": "Message vide."}), 400

    conv = chat_store.get_conversation(conversation_id, user['id'])
    if not conv:
        return jsonify({"error": "Conversation introuvable."}), 404

    assistant = assistants_store.get_assistant(conv.get('assistant_id'))
    if not assistant:
        return jsonify({"error": "Assistant introuvable."}), 404

    is_admin = bool(user.get('is_admin'))
    if not is_admin and not assistant.get('is_active'):
        return jsonify({"error": "Cet assistant n'est pas disponible."}), 403

    # On NE persiste PAS le message utilisateur avant la requête LLM : si la
    # requête échoue, on aurait un message user orphelin en DB et l'envoi
    # suivant produirait un historique avec deux messages user consécutifs,
    # ce que Claude et Gemini refusent.
    history = chat_store.list_messages(conversation_id, user['id'])
    llm_messages = [
        {"role": m['role'], "content": m['content']}
        for m in history
        if m.get('role') in ('user', 'assistant')
    ]
    llm_messages.append({"role": "user", "content": content})

    # Défense en profondeur : on dédoublonne les rôles consécutifs (ne devrait
    # jamais arriver mais ça protège la conversation contre des écritures
    # parasites passées).
    llm_messages = _coalesce_messages(llm_messages)

    provider_id, api_key, model_override = _resolve_provider_and_key(assistant)
    if not provider_id or not api_key:
        return jsonify({
            "error": (
                "Aucun fournisseur IA n'est configuré sur le serveur. "
                "Demandez à l'administrateur de renseigner une clé API."
            )
        }), 400

    # Détection de la matière/sous-matière dans les messages pour filtrer
    # les documents admin et la KB par matière (évite d'envoyer la démarche
    # d'une matière différente de celle demandée par l'utilisateur).
    detected_matiere, detected_sous_matiere = "", ""
    # On scanne les messages récents (le dernier user message en priorité)
    for msg in reversed(llm_messages):
        if msg.get("role") == "user":
            detected_matiere, detected_sous_matiere = _detect_matiere_from_text(
                msg.get("content", "")
            )
            if detected_matiere:
                break

    system_prompt = _build_chat_system_prompt(
        assistant,
        matiere=detected_matiere,
        sous_matiere=detected_sous_matiere,
    )

    try:
        reply = call_llm_chat(
            provider_id, api_key, system_prompt, llm_messages, model_override,
        )
    except LLMProviderError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": f"Erreur LLM : {e}"}), 502

    # LLM a répondu : on persiste maintenant le message user, puis la réponse.
    user_msg = chat_store.add_message(conversation_id, user['id'], 'user', content)

    # Détection d'une fiche dans la réponse → on la marque dans metadata.
    fiche = _extract_fiche_from_assistant(reply)
    metadata: dict = {}
    if fiche:
        metadata['has_fiche'] = True

    assistant_msg = chat_store.add_message(
        conversation_id, user['id'], 'assistant', reply, metadata=metadata,
    )

    # Si la fiche est complète à ce tour, on génère immédiatement les fichiers
    # pour que le front puisse afficher les boutons de téléchargement sans
    # un nouvel aller-retour.
    files: dict = {}
    if fiche:
        files = _generate_fiche_files(fiche, assistant=assistant, message_id=assistant_msg.get('id', ''))
        # Persiste les noms de fichiers dans metadata pour que les boutons
        # restent disponibles au rechargement de la conversation.
        if files and assistant_msg.get('id'):
            try:
                from db import service_client
                merged = dict(metadata)
                for k in ('base_name', 'docx_file', 'pdf_file', 'md_file'):
                    if files.get(k):
                        merged[k] = files[k]
                service_client().table('messages').update(
                    {'metadata': merged}
                ).eq('id', assistant_msg['id']).execute()
                assistant_msg['metadata'] = merged
            except Exception as _e:
                print(f"[chat] persist files metadata failed: {_e}")

    return jsonify({
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "fiche": fiche or "",
        "files": files,
    })


def _generate_fiche_files(content: str, assistant: dict | None, message_id: str = "") -> dict:
    """Génère .docx et .pdf à partir d'une fiche extraite. Retourne les noms."""
    file_id = (message_id or str(uuid.uuid4()))[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    classe = (assistant or {}).get('classe', 'fiche')
    base_name = f"chat_{classe}_{timestamp}_{file_id}"
    docx_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.docx")
    pdf_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.pdf")
    md_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.md")
    try:
        with open(md_path, 'w', encoding='utf-8') as fmd:
            fmd.write(content)
        generate_docx(content, docx_path)
    except Exception as e:
        print(f"[chat] DOCX generation failed: {e}")
        return {}
    pdf_ok = False
    try:
        generate_pdf_from_docx(docx_path, pdf_path)
        pdf_ok = os.path.exists(pdf_path)
    except Exception as e:
        print(f"[chat] PDF generation failed: {e}")
    return {
        "base_name": base_name,
        "docx_file": f"{base_name}.docx",
        "md_file": f"{base_name}.md",
        "pdf_file": f"{base_name}.pdf" if pdf_ok else None,
        "pdf_available": pdf_ok,
    }


@app.route('/admin')
@require_admin
def admin_home():
    """Espace admin dédié (assistants + clés API + documents internes)."""
    user = get_current_user()
    return render_template(
        'admin.html',
        providers=PROVIDERS,
        admin_categories=ADMIN_CATEGORIES,
        current_user=user,
    )


@app.route('/matieres')
def matieres():
    """Return the mapping matière -> sous-matières as JSON."""
    return jsonify(SOUS_MATIERES)


# ===== User authentication (Supabase) =====

def _safe_next(value: str) -> str:
    """Empêche un open-redirect en n'autorisant que des chemins relatifs internes.

    Refuse les URLs protocole-relatives (`//host`), les chemins ne commençant
    pas par un seul `/`, et toute valeur contenant des caractères de contrôle
    (CR/LF/NUL — anti header-injection). Retourne `/` par défaut.
    """
    if not value or not isinstance(value, str):
        return '/'
    if not value.startswith('/') or value.startswith('//') or value.startswith('/\\'):
        return '/'
    if any(ch in value for ch in ('\r', '\n', '\x00')):
        return '/'
    return value


@app.route('/login', methods=['GET'])
def login():
    nxt = _safe_next(request.args.get('next'))
    if session.get(SESSION_KEY_USER_ID):
        return redirect(nxt)
    return render_template(
        'login.html',
        error=request.args.get('error', ''),
        message=request.args.get('message', ''),
        next_url=nxt,
        email=request.args.get('email', ''),
    )


@app.route('/login', methods=['POST'])
def login_submit():
    email = (request.form.get('email') or '').strip()
    password = request.form.get('password') or ''
    nxt = _safe_next(request.form.get('next'))
    try:
        result = login_user(email, password)
    except AuthError as e:
        return render_template('login.html', error=str(e), next_url=nxt, email=email, message=''), 401
    store_session(result['session'], result['user'])
    return redirect(nxt)


@app.route('/signup', methods=['GET'])
def signup():
    nxt = _safe_next(request.args.get('next'))
    if session.get(SESSION_KEY_USER_ID):
        return redirect(nxt)
    return render_template(
        'signup.html',
        error=request.args.get('error', ''),
        next_url=nxt,
        email=request.args.get('email', ''),
        full_name=request.args.get('full_name', ''),
    )


@app.route('/signup', methods=['POST'])
def signup_submit():
    email = (request.form.get('email') or '').strip()
    full_name = (request.form.get('full_name') or '').strip()
    password = request.form.get('password') or ''
    nxt = _safe_next(request.form.get('next'))
    try:
        result = signup_user(email, password, full_name=full_name)
    except AuthError as e:
        return render_template(
            'signup.html', error=str(e), next_url=nxt, email=email, full_name=full_name,
        ), 400
    # Supabase peut exiger une confirmation email. Si on a une session
    # immédiate, on connecte directement ; sinon on renvoie vers /login.
    if result.get('session'):
        store_session(result['session'], result['user'])
        return redirect(nxt)
    return redirect(url_for(
        'login',
        next=nxt,
        email=email,
        message='Compte créé. Connectez-vous pour continuer.',
    ))


@app.route('/logout', methods=['POST'])
def logout():
    """POST uniquement: empêche un logout-CSRF."""
    logout_user()
    return redirect('/')


# ===== Admin login alias (rétrocompat avec ?admin et /admin/login) =====

@app.route('/admin/login', methods=['GET'])
def admin_login():
    """Alias historique : redirige vers /login."""
    return redirect(url_for('login', next=_safe_next(request.args.get('next'))))


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Alias historique : redirige vers /logout."""
    logout_user()
    return redirect('/')


# ===== Admin endpoints =====

@app.route('/me')
def me():
    """Renvoie les infos du user connecté (ou anonyme)."""
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False, "is_admin": False})
    return jsonify({"authenticated": True, **user})


@app.route('/admin/check')
def admin_check():
    return jsonify({"is_admin": _is_admin_request()})


@app.route('/admin/docs', methods=['GET'])
def admin_list_docs():
    _require_admin()
    category = request.args.get('category', '')
    docs = ADMIN_STORE.list_docs(category)
    # Drop heavy "content" from listing for speed
    return jsonify([{k: v for k, v in d.items() if k != 'content'} for d in docs])


@app.route('/admin/docs', methods=['POST'])
def admin_upload_doc():
    _require_admin()
    category = request.form.get('category', '')
    if category not in ADMIN_CATEGORIES:
        return jsonify({"error": f"Catégorie invalide: {category}"}), 400
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({"error": "Fichier manquant"}), 400
    fname_lower = f.filename.lower()
    if not fname_lower.endswith(('.txt', '.md', '.pdf')):
        return jsonify({"error": "Formats acceptés : .txt, .md, .pdf"}), 400
    try:
        if fname_lower.endswith('.pdf'):
            # Extraction texte depuis le PDF (le contenu stocké est du texte UTF-8).
            text, _, _ = extract_text_from_uploaded(f, app.config['UPLOAD_FOLDER'])
            content = text or ""
            if not content.strip():
                return jsonify({
                    "error": "Aucun texte extrait du PDF (PDF scanné/image ?)."
                }), 400
        else:
            content = f.read().decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({"error": f"Lecture impossible: {e}"}), 400
    doc = ADMIN_STORE.add_doc(category, f.filename, content)
    return jsonify({k: v for k, v in doc.items() if k != 'content'})


@app.route('/admin/docs', methods=['DELETE'])
def admin_remove_doc():
    _require_admin()
    category = request.args.get('category', '')
    name = request.args.get('name', '')
    if not ADMIN_STORE.remove_doc(category, name):
        return jsonify({"error": "Document introuvable"}), 404
    return jsonify({"ok": True})


@app.route('/admin/instructions', methods=['GET'])
def admin_get_instructions():
    _require_admin()
    return jsonify({"instructions": ADMIN_STORE.get_instructions()})


@app.route('/admin/instructions', methods=['POST'])
def admin_set_instructions():
    _require_admin()
    text = (request.json or {}).get('instructions', '') if request.is_json else request.form.get('instructions', '')
    ADMIN_STORE.set_instructions(text)
    return jsonify({"ok": True})


# ===== Admin API keys =====

@app.route('/admin/api_keys', methods=['GET'])
def admin_list_api_keys():
    """Liste l'état (configuré/non configuré + santé + quota) des clés par
    fournisseur. Ne renvoie JAMAIS la clé en clair."""
    _require_admin()
    from provider_health import get_status, refresh_quota
    from provider_quota import supports_quota
    status = KEY_STORE.list_api_key_status()
    # Pour les fournisseurs qui exposent un endpoint de solde (OpenRouter,
    # éventuellement OpenAI), on rafraîchit la valeur. Le refresh est
    # throttlé à 60s côté provider_health, donc charger /admin plusieurs
    # fois d'affilée ne hammer pas les fournisseurs.
    for pid in list(status.keys()):
        if supports_quota(pid):
            try:
                refresh_quota(pid, KEY_STORE.get_api_key(pid))
            except Exception:
                pass
    out = {}
    for pid, info in PROVIDERS.items():
        configured = pid in status
        health = get_status(pid) if configured else {"status": "unknown", "checked_at": "", "message": "", "quota": None}
        quota = health.get("quota") or None
        out[pid] = {
            "name": info.get("name", pid),
            "configured": configured,
            "masked": status.get(pid, {}).get("masked", ""),
            "health": health.get("status", "unknown"),
            "health_message": health.get("message", ""),
            "health_checked_at": health.get("checked_at", ""),
            "supports_quota": supports_quota(pid),
            "quota": quota,
        }
    return jsonify(out)


@app.route('/admin/api_keys', methods=['POST'])
def admin_set_api_key():
    """Stocke ou efface (clé vide) la clé d'un fournisseur."""
    _require_admin()
    payload = request.get_json(force=True, silent=True) or {}
    provider_id = payload.get('provider', '')
    api_key = (payload.get('api_key') or '').strip()
    if provider_id not in PROVIDERS:
        return jsonify({"error": f"Fournisseur inconnu: {provider_id}"}), 400
    user = get_current_user()
    KEY_STORE.set_api_key(provider_id, api_key, updated_by=user['id'] if user else None)
    # Reset le statut santé : on ne sait pas encore si la nouvelle clé marche.
    try:
        from provider_health import reset_status
        reset_status(provider_id)
    except Exception:
        pass
    return jsonify({"ok": True, "configured": bool(api_key)})


@app.route('/admin/api_keys/<provider_id>/test', methods=['POST'])
@require_admin
def admin_test_api_key(provider_id: str):
    """Teste une clé API en émettant un ping minimal et renvoie le statut."""
    if provider_id not in PROVIDERS:
        return jsonify({"error": f"Fournisseur inconnu: {provider_id}"}), 400
    api_key = KEY_STORE.get_api_key(provider_id)
    if not api_key:
        return jsonify({"error": "Clé non configurée pour ce fournisseur."}), 400
    from provider_health import test_provider
    model_override = KEY_STORE.get_default_model() if provider_id == KEY_STORE.get_default_provider() else None
    health = test_provider(provider_id, api_key, model_override=model_override or None)
    return jsonify({"ok": True, "health": health})


@app.route('/providers/status')
def providers_status():
    """Indique pour chaque fournisseur s'il est utilisable sans clé utilisateur (clé serveur configurée)."""
    keys = KEY_STORE.list_api_key_status()
    return jsonify({pid: {"server_key": pid in keys} for pid in PROVIDERS.keys()})


# ===== Admin: assistants par classe =====

@app.route('/admin/assistants', methods=['GET'])
@require_admin
def admin_list_assistants():
    return jsonify({"assistants": assistants_store.list_assistants(only_active=False)})


@app.route('/admin/assistants/<assistant_id>', methods=['GET'])
@require_admin
def admin_get_assistant(assistant_id: str):
    a = assistants_store.get_assistant(assistant_id)
    if not a:
        return jsonify({"error": "Assistant introuvable"}), 404
    docs = assistants_store.list_documents(assistant_id)
    return jsonify({"assistant": a, "documents": docs})


@app.route('/admin/assistants/<assistant_id>', methods=['PATCH'])
@require_admin
def admin_update_assistant(assistant_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    # Le store filtre déjà les champs non-whitelistés.
    updated = assistants_store.update_assistant(assistant_id, payload)
    if not updated:
        return jsonify({"error": "Assistant introuvable ou aucune modification"}), 404
    return jsonify({"assistant": updated})


@app.route('/admin/assistants/<assistant_id>/documents', methods=['POST'])
@require_admin
def admin_upload_assistant_doc(assistant_id: str):
    if not assistants_store.get_assistant(assistant_id):
        return jsonify({"error": "Assistant introuvable"}), 404
    # Multi-file : on accepte 1 ou N fichiers sous le champ 'file'
    # (ou 'files' pour rétro-compat). On traite chaque fichier
    # indépendamment et on renvoie la liste des succès + la liste des
    # erreurs par fichier.
    files = request.files.getlist('file') or request.files.getlist('files')
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "Fichier manquant"}), 400
    user = get_current_user()
    uploaded_by = user['id'] if user else None
    # Résolution UNE FOIS du fournisseur LLM pour le fallback OCR.
    # Si aucun n'est configuré, ou si le fournisseur configuré ne supporte
    # pas la lecture de PDFs, on tombera proprement sur l'erreur historique.
    llm_provider_id, llm_api_key, llm_model_override = _resolve_provider_and_key(None)
    documents = []
    errors = []
    for f in files:
        fname_lower = f.filename.lower()
        if not fname_lower.endswith(('.txt', '.md', '.pdf')):
            errors.append({"filename": f.filename, "error": "Format non supporté (.txt, .md, .pdf)."})
            continue
        try:
            if fname_lower.endswith('.pdf'):
                text, filepath, _ = extract_text_from_uploaded(f, app.config['UPLOAD_FOLDER'])
                content = (text or "").strip()
                # Fallback IA quand PyMuPDF n'a rien sorti (PDF scanné/images).
                # Seuil 50 caractères : un PDF qui ne contient que quelques
                # numéros de page n'est pas exploitable, on demande à l'IA.
                if len(content) < 50:
                    if not llm_provider_id or not llm_api_key:
                        errors.append({
                            "filename": f.filename,
                            "error": (
                                "Aucun texte extrait (PDF scanné ?) et aucun "
                                "fournisseur LLM configuré pour la lecture IA."
                            ),
                        })
                        continue
                    if not supports_pdf_ocr(llm_provider_id):
                        errors.append({
                            "filename": f.filename,
                            "error": (
                                f"Aucun texte extrait et le fournisseur "
                                f"{llm_provider_id} ne sait pas lire un PDF "
                                f"directement (utilisez Gemini ou Claude)."
                            ),
                        })
                        continue
                    try:
                        ocr_text = extract_text_via_llm(
                            filepath,
                            llm_provider_id,
                            llm_api_key,
                            model_override=llm_model_override,
                        )
                    except Exception as ocr_err:
                        errors.append({
                            "filename": f.filename,
                            "error": f"Lecture IA échouée : {ocr_err}",
                        })
                        continue
                    content = (ocr_text or "").strip()
                    if not content:
                        errors.append({
                            "filename": f.filename,
                            "error": "Lecture IA n'a retourné aucun texte.",
                        })
                        continue
            else:
                content = f.read().decode('utf-8', errors='replace')
        except Exception as e:
            errors.append({"filename": f.filename, "error": f"Lecture impossible: {e}"})
            continue
        doc = assistants_store.add_document(
            assistant_id,
            f.filename,
            content,
            uploaded_by=uploaded_by,
        )
        documents.append({k: v for k, v in doc.items() if k != 'content'})
    if not documents and errors:
        # Aucun fichier accepté → 400 avec le détail.
        return jsonify({"error": errors[0]["error"], "errors": errors}), 400
    payload = {"documents": documents, "errors": errors}
    # Rétro-compat : single document accessible via 'document'
    if len(documents) == 1 and not errors:
        payload["document"] = documents[0]
    return jsonify(payload)


@app.route('/admin/assistants/<assistant_id>/documents/<document_id>', methods=['DELETE'])
@require_admin
def admin_delete_assistant_doc(assistant_id: str, document_id: str):
    ok = assistants_store.remove_document(assistant_id, document_id)
    if not ok:
        return jsonify({"error": "Document introuvable"}), 404
    return jsonify({"ok": True})


# ===== Admin settings (default provider/model) =====

@app.route('/admin/settings', methods=['GET'])
def admin_get_settings():
    _require_admin()
    return jsonify({
        "default_provider": KEY_STORE.get_default_provider(),
        "default_model": KEY_STORE.get_default_model(),
    })


@app.route('/admin/settings', methods=['POST'])
def admin_set_settings():
    _require_admin()
    payload = request.get_json(force=True, silent=True) or {}
    provider_id = (payload.get('default_provider') or '').strip()
    model = (payload.get('default_model') or '').strip()
    if provider_id and provider_id not in PROVIDERS:
        return jsonify({"error": f"Fournisseur inconnu: {provider_id}"}), 400
    KEY_STORE.set_default_provider(provider_id)
    KEY_STORE.set_default_model(model)
    return jsonify({"ok": True})


# ===== Admin: gestion des utilisateurs =====

def _all_auth_users() -> list:
    """Retourne tous les comptes d'auth.users via l'API admin Supabase.

    Source de vérité pour la liste des utilisateurs (vs. `public.profiles`
    qui peut diverger si le trigger `handle_new_user` a échoué). Best-effort :
    si Supabase est down, retourne []."""
    try:
        from db import service_client
        sb = service_client()
        page = 1
        per_page = 1000
        out: list = []
        while True:
            res = sb.auth.admin.list_users(page=page, per_page=per_page)
            users = res if isinstance(res, list) else (getattr(res, "users", None) or [])
            if not users:
                break
            for u in users:
                if isinstance(u, dict):
                    uid = u.get("id")
                    email = u.get("email")
                    last = u.get("last_sign_in_at")
                    created = u.get("created_at")
                    meta = u.get("user_metadata") or {}
                else:
                    uid = getattr(u, "id", None)
                    email = getattr(u, "email", None)
                    last = getattr(u, "last_sign_in_at", None)
                    created = getattr(u, "created_at", None)
                    meta = getattr(u, "user_metadata", None) or {}
                if not uid:
                    continue
                out.append({
                    "id": str(uid),
                    "email": str(email or ""),
                    "last_sign_in_at": str(last or ""),
                    "created_at": str(created or ""),
                    "full_name": str((meta or {}).get("full_name") or ""),
                })
            if len(users) < per_page:
                break
            page += 1
        return out
    except Exception:
        return []


@app.route('/admin/users', methods=['GET'])
@require_admin
def admin_list_users():
    """Liste tous les comptes Supabase (admin + utilisateurs) avec leur
    statut, leur consommation de tokens, et un drapeau `is_self`.

    On lit auth.users via l'API admin (source de vérité) puis on enrichit
    chaque ligne avec les colonnes de `public.profiles` (is_admin,
    is_suspended, full_name canonique). Si une ligne d'auth.users n'a pas
    de profil correspondant — cas pathologique où le trigger
    handle_new_user a échoué — l'utilisateur apparaît quand même dans la
    liste avec is_admin=False/is_suspended=False."""
    auth_users = _all_auth_users()

    # Profils côté public.profiles (pour is_admin / is_suspended / full_name canonique)
    from db import service_client
    sb = service_client()
    try:
        res = (
            sb.table("profiles")
            .select("id, email, full_name, is_admin, is_suspended, created_at")
            .execute()
        )
        profile_rows = getattr(res, "data", None) or []
    except Exception:
        profile_rows = []
    profiles_by_id = {str(r.get("id") or ""): r for r in profile_rows if r.get("id")}

    # Consommation tokens
    try:
        from usage_store import get_usage_totals_by_user
        usage = get_usage_totals_by_user()
    except Exception:
        usage = {}

    me = get_current_user() or {}
    my_id = str(me.get("id") or "")

    users = []
    for au in auth_users:
        uid = au["id"]
        prof = profiles_by_id.get(uid) or {}
        u_usage = usage.get(uid) or {}
        users.append({
            "id": uid,
            "email": (prof.get("email") or au.get("email") or "").strip(),
            "full_name": (prof.get("full_name") or au.get("full_name") or "").strip(),
            "is_admin": bool(prof.get("is_admin", False)),
            "is_suspended": bool(prof.get("is_suspended", False)),
            "has_profile": bool(prof),
            "created_at": prof.get("created_at") or au.get("created_at") or "",
            "last_sign_in_at": au.get("last_sign_in_at") or "",
            "is_self": uid == my_id,
            "tokens_total": int(u_usage.get("total") or 0),
            "tokens_30d": int(u_usage.get("total_30d") or 0),
            "calls": int(u_usage.get("calls") or 0),
            "last_used": u_usage.get("last_used") or "",
        })
    # Tri : admins d'abord, puis par date de création décroissante.
    users.sort(key=lambda u: (
        0 if u["is_admin"] else 1,
        -(int((u["created_at"] or "0")[:4] or 0)),  # année descending (approx)
        u["created_at"] or "",
    ), reverse=False)
    # Tri secondaire stable sur created_at desc.
    users.sort(key=lambda u: u["created_at"] or "", reverse=True)
    users.sort(key=lambda u: 0 if u["is_admin"] else 1)
    return jsonify({"users": users})


def _set_user_admin(user_id: str, value: bool):
    """Promeut / dépromeut un utilisateur en admin.

    Garde-fous :
    - On ne peut pas modifier son propre rôle (anti-lockout).
    - On vérifie qu'il restera au moins un admin si on dépromeut.
    """
    me = get_current_user() or {}
    if str(me.get("id") or "") == str(user_id):
        return jsonify({"error": "Vous ne pouvez pas modifier votre propre rôle administrateur."}), 400
    from db import service_client
    sb = service_client()
    if not value:
        # Refuse si ce serait le dernier admin restant.
        try:
            res = (
                sb.table("profiles")
                .select("id", count="exact")
                .eq("is_admin", True)
                .execute()
            )
            admin_count = getattr(res, "count", None)
            if admin_count is None:
                admin_count = len(getattr(res, "data", None) or [])
        except Exception:
            admin_count = None
        if isinstance(admin_count, int) and admin_count <= 1:
            return jsonify({"error": "Impossible : il doit rester au moins un administrateur."}), 400
    try:
        res = (
            sb.table("profiles")
            .update({"is_admin": value})
            .eq("id", user_id)
            .execute()
        )
    except Exception as e:
        return jsonify({"error": f"Mise à jour impossible : {e}"}), 500
    rows = getattr(res, "data", None) or []
    if not rows:
        return jsonify({"error": "Utilisateur introuvable (profil manquant)."}), 404
    return jsonify({"ok": True, "user": {"id": user_id, "is_admin": value}})


@app.route('/admin/users/<user_id>/promote', methods=['POST'])
@require_admin
def admin_promote_user(user_id: str):
    return _set_user_admin(user_id, True)


@app.route('/admin/users/<user_id>/demote', methods=['POST'])
@require_admin
def admin_demote_user(user_id: str):
    return _set_user_admin(user_id, False)


def _set_user_suspended(user_id: str, value: bool):
    """Met à jour profiles.is_suspended pour un utilisateur donné."""
    me = get_current_user() or {}
    if str(me.get("id") or "") == str(user_id):
        return jsonify({"error": "Vous ne pouvez pas vous suspendre vous-même."}), 400
    from db import service_client
    sb = service_client()
    try:
        res = (
            sb.table("profiles")
            .update({"is_suspended": value})
            .eq("id", user_id)
            .execute()
        )
    except Exception as e:
        return jsonify({"error": f"Mise à jour impossible : {e}"}), 500
    rows = getattr(res, "data", None) or []
    if not rows:
        return jsonify({"error": "Utilisateur introuvable."}), 404
    return jsonify({"ok": True, "user": {
        "id": user_id,
        "is_suspended": value,
    }})


@app.route('/admin/users/<user_id>/suspend', methods=['POST'])
@require_admin
def admin_suspend_user(user_id: str):
    return _set_user_suspended(user_id, True)


@app.route('/admin/users/<user_id>/unsuspend', methods=['POST'])
@require_admin
def admin_unsuspend_user(user_id: str):
    return _set_user_suspended(user_id, False)


@app.route('/admin/users/<user_id>', methods=['DELETE'])
@require_admin
def admin_delete_user(user_id: str):
    """Suppression définitive : on supprime via auth.admin.delete_user, le
    cascade FK supprime automatiquement profil, conversations et messages."""
    me = get_current_user() or {}
    if str(me.get("id") or "") == str(user_id):
        return jsonify({"error": "Vous ne pouvez pas supprimer votre propre compte."}), 400
    from db import service_client
    sb = service_client()
    try:
        sb.auth.admin.delete_user(user_id)
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "no rows" in msg:
            return jsonify({"error": "Utilisateur introuvable."}), 404
        return jsonify({"error": f"Suppression impossible : {e}"}), 500
    return jsonify({"ok": True})


@app.route('/admin/users/<user_id>/reset_usage', methods=['POST'])
@require_admin
def admin_reset_user_usage(user_id: str):
    """Réinitialise les compteurs de tokens d'un utilisateur."""
    from usage_store import reset_usage
    if reset_usage(user_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Impossible de réinitialiser les quotas."}), 500


@app.route('/generate', methods=['POST'])
@require_login
def generate():
    try:
        # Get form data
        provider_id = (request.form.get('provider') or '').strip()
        api_key = request.form.get('api_key', '').strip()
        model_override = request.form.get('model_override', '').strip() or None

        # Si l'utilisateur n'a pas spécifié de fournisseur (cas des non-admins, qui
        # ne voient pas le sélecteur), on choisit dans l'ordre :
        #   1. le fournisseur par défaut configuré par l'admin, s'il a une clé serveur
        #   2. sinon, le premier fournisseur qui a une clé serveur configurée
        # Évite le piège "l'admin a sauvegardé Groq mais le serveur demande OpenAI".
        if not provider_id:
            admin_default = KEY_STORE.get_default_provider()
            configured = set(KEY_STORE.list_api_key_status().keys())
            if admin_default and admin_default in configured:
                provider_id = admin_default
            elif configured:
                # Priorité stable à l'ordre des PROVIDERS déclarés.
                for pid in PROVIDERS.keys():
                    if pid in configured:
                        provider_id = pid
                        break
            elif admin_default:
                provider_id = admin_default
        if not provider_id:
            return jsonify({
                "error": (
                    "Aucun fournisseur IA n'est configuré sur le serveur. "
                    "Demandez à l'administrateur de renseigner une clé API dans l'espace administration."
                )
            }), 400
        if provider_id not in PROVIDERS:
            return jsonify({
                "error": f"Fournisseur inconnu côté serveur : {provider_id}. "
                         f"Demandez à l'administrateur de configurer un fournisseur par défaut."
            }), 400
        # Idem pour le modèle: si rien fourni, prendre le défaut admin —
        # mais UNIQUEMENT si le fournisseur effectif est le fournisseur par
        # défaut admin. Sinon on risque d'envoyer un modèle Gemini à Claude.
        if not model_override:
            _admin_default_p = KEY_STORE.get_default_provider()
            if provider_id == _admin_default_p:
                model_override = KEY_STORE.get_default_model() or None
        niveau = request.form.get('niveau', '').strip()
        sa = request.form.get('sa', '').strip()
        sequence = request.form.get('sequence', '').strip()
        type_fiche = request.form.get('type_fiche', 'Séquence normale')
        instructions = request.form.get('instructions', '')
        matiere = request.form.get('matiere', '').strip()
        sous_matiere = request.form.get('sous_matiere', '').strip()
        titre_sa = request.form.get('titre_sa', '').strip()
        titre_sequence = request.form.get('titre_sequence', '').strip()
        duree = request.form.get('duree', '').strip()
        objectifs = request.form.get('objectifs', '').strip()

        # Champs minimaux requis côté serveur (défense contre les POST qui
        # contourneraient les attributs `required` du formulaire).
        required = {
            "Matière": matiere,
            "Niveau": niveau,
            "SA N°": sa,
            "Séquence N°": sequence,
            "Titre de la SA": titre_sa,
        }
        missing = [label for label, value in required.items() if not value]
        if missing:
            return jsonify({
                "error": (
                    "Champs obligatoires manquants : " + ", ".join(missing)
                    + ". Merci de les renseigner avant de générer la fiche."
                )
            }), 400

        # Validate matiere is known
        if matiere not in SOUS_MATIERES:
            return jsonify({
                "error": f"Matière inconnue : '{matiere}'."
            }), 400

        # Validate sous_matiere belongs to matiere when provided
        if sous_matiere:
            allowed = get_sous_matieres(matiere)
            if allowed and sous_matiere not in allowed:
                return jsonify({
                    "error": f"Sous-matière invalide '{sous_matiere}' pour la matière '{matiere}'."
                }), 400

        # Si l'utilisateur n'a pas fourni de clé, on retombe sur la clé serveur
        # configurée par l'admin pour ce fournisseur (le cas par défaut quand
        # un admin a publié l'app pour ses utilisateurs).
        if not api_key:
            api_key = KEY_STORE.get_api_key(provider_id)
        if not api_key:
            return jsonify({
                "error": (
                    f"Aucune clé API disponible pour {PROVIDERS.get(provider_id, {}).get('name', provider_id)}. "
                    "Demandez à l'administrateur d'en configurer une, ou collez la vôtre dans le formulaire."
                )
            }), 400

        # Process uploaded documents
        doc_principal_text = ""
        docs_comp_texts = []

        if 'doc_principal' in request.files:
            f = request.files['doc_principal']
            if f.filename and f.filename.endswith('.pdf'):
                text, _, _ = extract_text_from_uploaded(f, app.config['UPLOAD_FOLDER'])
                doc_principal_text = text

        if 'docs_complementaires' in request.files:
            files = request.files.getlist('docs_complementaires')
            for f in files:
                if f.filename and f.filename.endswith('.pdf'):
                    text, _, _ = extract_text_from_uploaded(f, app.config['UPLOAD_FOLDER'])
                    docs_comp_texts.append(text)

        # Search knowledge base for relevant context
        kb_results = kb.search(matiere=matiere, niveau=niveau, sa=sa, sequence=sequence, sous_matiere=sous_matiere)
        kb_context = ""
        if kb_results:
            kb_context = "\n\n".join([f"=== {r['filename']} ===\n{r['text'][:5000]}" for r in kb_results[:3]])

        # KB par assistant : si la classe correspond à un assistant Supabase, on
        # ajoute ses derniers documents en complément (max 3, ~5000 chars chacun).
        try:
            assistant = assistants_store.get_assistant_by_classe(niveau)
        except Exception:
            assistant = None
        if assistant and assistant.get('id'):
            try:
                docs = assistants_store.get_document_contents(assistant['id'], limit=3)
            except Exception:
                docs = []
            if docs:
                extra = "\n\n".join(
                    f"=== {d.get('name','')} ===\n{(d.get('content') or '')[:5000]}"
                    for d in docs
                )
                kb_context = (kb_context + "\n\n" + extra).strip() if kb_context else extra

        # Build prompts
        params = {
            "niveau": niveau,
            "sa": sa,
            "sequence": sequence,
            "type_fiche": type_fiche,
            "instructions": instructions,
            "matiere": matiere,
            "sous_matiere": sous_matiere,
            "titre_sa": titre_sa,
            "titre_sequence": titre_sequence,
            "duree": duree,
            "objectifs": objectifs,
        }
        admin_context = ADMIN_STORE.build_context_block()
        user_prompt = build_user_prompt(params, doc_principal_text, docs_comp_texts, kb_context, admin_context)

        # System prompt enrichi par les instructions admin
        admin_instructions = ADMIN_STORE.get_instructions()
        system_prompt = SYSTEM_PROMPT
        if admin_instructions:
            system_prompt = (
                f"{SYSTEM_PROMPT}\n\n=== CONSIGNES ADMINISTRATIVES PERMANENTES ===\n{admin_instructions}"
            )

        # Call LLM (avec gestion fine des erreurs upstream)
        try:
            generated_content = call_llm(provider_id, api_key, system_prompt, user_prompt, model_override)
        except LLMProviderError as e:
            return jsonify({"error": str(e)}), 502

        # Generate files
        file_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_matiere = matiere.replace(' ', '_').replace('/', '-')
        safe_sm = sous_matiere.replace(' ', '_').replace('/', '-')
        mat_part = f"{safe_matiere}-{safe_sm}" if safe_sm else safe_matiere
        # Optional human-readable slug from titre_sa
        titre_slug = ""
        if titre_sa:
            slug = re.sub(r'[^A-Za-z0-9]+', '_', titre_sa).strip('_')
            titre_slug = f"_{slug[:40]}" if slug else ""
        base_name = f"fiche_{niveau}_{mat_part}_SA{sa}{titre_slug}_{timestamp}_{file_id}"

        docx_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.docx")
        pdf_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.pdf")
        md_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.md")

        # Save markdown source (always)
        with open(md_path, 'w', encoding='utf-8') as fmd:
            fmd.write(generated_content)

        # Generate DOCX
        generate_docx(generated_content, docx_path)

        # Generate PDF
        pdf_generated = False
        try:
            generate_pdf_from_docx(docx_path, pdf_path)
            pdf_generated = os.path.exists(pdf_path)
        except Exception as e:
            print(f"PDF generation failed: {e}")

        return jsonify({
            "success": True,
            "content": generated_content,
            "base_name": base_name,
            "docx_file": f"{base_name}.docx",
            "md_file": f"{base_name}.md",
            "pdf_file": f"{base_name}.pdf" if pdf_generated else None,
            "pdf_available": pdf_generated,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download/<filename>')
def download(filename):
    filepath = os.path.join(app.config['GENERATED_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({"error": "Fichier non trouvé"}), 404


@app.route('/regenerate', methods=['POST'])
@require_login
def regenerate():
    """Régénère docx/pdf depuis un contenu édité par l'utilisateur."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        content = (payload.get('content') or '').strip()
        base_name = (payload.get('base_name') or '').strip()
        if not content:
            return jsonify({"error": "Contenu vide"}), 400
        if not base_name:
            base_name = f"fiche_edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        else:
            # Empêche les chemins relatifs (../)
            base_name = os.path.basename(base_name)
            # Retire les éventuels suffixes _edit_HHMMSS précédents pour éviter
            # un nom de fichier qui croît sans borne à chaque régénération.
            base_name = re.sub(r'(_edit_\d+)+$', '', base_name)
            base_name = f"{base_name}_edit_{datetime.now().strftime('%H%M%S')}"

        docx_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.docx")
        pdf_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.pdf")
        md_path = os.path.join(app.config['GENERATED_FOLDER'], f"{base_name}.md")

        with open(md_path, 'w', encoding='utf-8') as fmd:
            fmd.write(content)
        generate_docx(content, docx_path)
        pdf_generated = False
        try:
            generate_pdf_from_docx(docx_path, pdf_path)
            pdf_generated = os.path.exists(pdf_path)
        except Exception as e:
            print(f"PDF regeneration failed: {e}")

        return jsonify({
            "success": True,
            "base_name": base_name,
            "docx_file": f"{base_name}.docx",
            "md_file": f"{base_name}.md",
            "pdf_file": f"{base_name}.pdf" if pdf_generated else None,
            "pdf_available": pdf_generated,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/admin/cleanup_fiches', methods=['POST'])
@require_admin
def admin_cleanup_fiches():
    """Déclenche manuellement le nettoyage des fiches expirées (>14 jours)."""
    try:
        days = app.config['FICHE_RETENTION_DAYS']
        try:
            payload = request.get_json(silent=True) or {}
            if 'days' in payload:
                days = max(1, int(payload['days']))
        except Exception:
            pass
        counters = chat_store.cleanup_expired_fiches(
            days=days,
            generated_folder=app.config['GENERATED_FOLDER'],
        )
        # On force la mise à jour de l'horodatage pour éviter un double run.
        from datetime import datetime, timezone
        _cleanup_state["last_run"] = datetime.now(timezone.utc)
        return jsonify({"success": True, "days": days, **counters})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/kb/stats')
def kb_stats():
    """Return knowledge base statistics."""
    stats = {
        "total_documents": len(kb.documents),
        "documents": [{"filename": d["filename"], "pages": d["page_count"]} for d in kb.documents]
    }
    return jsonify(stats)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
