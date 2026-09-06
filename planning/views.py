"""Vues du planning : page du mois, copie autonome, API des versions, erreurs.

Les logs de ce module ne portent que le mois, un numéro de version, un nombre
de violations ou un nom de classe d'erreur JS : jamais un nom de personne,
jamais un type d'absence.
"""

import json
import logging
from pathlib import Path

from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from comptes.acces import role_requis
from comptes.models import Compte
from presences.fenetres import libelle_mois, mois_precedent, mois_suivant, plage_mois
from socle.debit import limite_par_ip

from . import donnees, services

logger = logging.getLogger(__name__)

CABINET = Compte.Role.CABINET
PRINCIPALE = Compte.Role.PRINCIPALE
SALARIEE = Compte.Role.SALARIEE

# Plafond applicatif du corps de l'API des versions, en plus de
# `DATA_UPLOAD_MAX_MEMORY_SIZE` (2,5 Mo par défaut).
CORPS_MAX_OCTETS = 1024 * 1024
# Longueur maximale des champs du rapport d'erreurs.
LONGUEUR_MAX_ERREUR = 80
# Plafond par défaut du rapport d'erreurs, si le réglage manque.
DEBIT_ERREURS_DEFAUT = (30, 60)

STATIQUES = {
    "styles_css": "planning/styles.css",
    "moteur_js": "planning/moteur.js",
    "page_js": "planning/page.js",
}


def _plage_ou_404(mois):
    try:
        return plage_mois(mois)
    except ValueError:
        raise Http404("mois invalide") from None


def _contexte_mois(request, mois):
    return {
        "mois": mois,
        "libelle": libelle_mois(mois),
        "precedent": mois_precedent(mois),
        "suivant": mois_suivant(mois),
        "peut_importer": request.user.role == CABINET,
    }


def _meta(mois, numero, autonome, publiee=0):
    """`{mois, numero, autonome, publiee, urls}` : `publiee` = numéro de la version
    publiée courante, 0 sinon ; `urls.publier` n'existe que s'il y a une version."""
    urls = {}
    if not autonome:
        urls = {
            "versions": reverse("planning:versions", kwargs={"mois": mois}),
            "erreurs": reverse("planning:erreurs"),
            "copie": reverse("planning:copie", kwargs={"mois": mois}),
        }
        if numero > 0:
            urls["publier"] = reverse(
                "planning:publier", kwargs={"mois": mois, "numero": numero}
            )
    return {
        "mois": mois,
        "numero": numero,
        "autonome": autonome,
        "publiee": publiee,
        "urls": urls,
    }


def _numero_publie(mois):
    publiee = services.version_publiee(mois)
    return publiee.numero if publiee else 0


# --- Pages ---------------------------------------------------------------------


@role_requis(CABINET, PRINCIPALE)
def planning_courant(request):
    """`/planning/` → le mois en cours (fuseau Europe/Paris)."""
    return redirect("planning:mois", mois=timezone.localdate().strftime("%Y-%m"))


@role_requis(CABINET, PRINCIPALE)
def planning_mois(request, mois):
    """La page du mois : `DATA` calculé, `STATE` de la dernière version.

    Sans aucun import réussi sur la plage, la page n'a rien à planifier : un
    écran dédié renvoie vers l'import des présences, et le moteur ne démarre
    pas. La décision de proposer revient à la page, sur `meta.numero === 0`.
    """
    plage = _plage_ou_404(mois)
    contexte = _contexte_mois(request, mois)
    if not donnees.mois_couvert(plage):
        return render(request, "planning/sans_import.html", contexte)

    derniere = services.derniere_version(mois)
    numero = derniere.numero if derniere else 0
    contexte.update(
        {
            "data": donnees.construire(mois),
            "state": derniere.state if derniere else services.etat_vide(),
            "meta": _meta(mois, numero, autonome=False, publiee=_numero_publie(mois)),
            "numero": numero,
        }
    )
    return render(request, "planning/page.html", contexte)


def _statique(chemin):
    """Texte d'un fichier statique de l'app, lu à la source (`finders`).

    Pas l'URL hachée du manifeste : la copie inline le contenu. Un fichier qui
    contiendrait la séquence de fermeture d'un script casserait la page
    autonome : c'est refusé net plutôt que servi cassé.
    """
    fichier = finders.find(chemin)
    if not fichier:
        raise FileNotFoundError(chemin)
    texte = Path(fichier).read_text(encoding="utf-8")
    if "</script" in texte.lower() or "</style" in texte.lower():
        raise ValueError(f"{chemin} : séquence de fermeture interdite dans un fichier inliné")
    return mark_safe(texte)


@role_requis(CABINET, PRINCIPALE)
def copie(request, mois):
    """Copie HTML autonome de la dernière version enregistrée du mois."""
    _plage_ou_404(mois)
    derniere = services.derniere_version(mois)
    if derniere is None:
        raise Http404("aucune version enregistrée pour ce mois")

    contexte = {
        "mois": mois,
        "libelle": libelle_mois(mois),
        "data": donnees.construire(mois),
        "state": derniere.state,
        "meta": _meta(mois, derniere.numero, autonome=True, publiee=_numero_publie(mois)),
    }
    contexte.update({cle: _statique(chemin) for cle, chemin in STATIQUES.items()})
    html = render_to_string("planning/copie.html", contexte, request=request)

    reponse = HttpResponse(html, content_type="text/html; charset=utf-8")
    reponse["Content-Disposition"] = (
        f'attachment; filename="planning-assistantes_{mois}_v{derniere.numero}.html"'
    )
    return reponse


# --- API -----------------------------------------------------------------------


def _json_405():
    return JsonResponse({"erreur": "methode_non_autorisee"}, status=405)


def _corps_json(request):
    """Le corps décodé, ou None s'il n'est pas un objet JSON."""
    try:
        corps = json.loads(request.body or b"")
    except ValueError:
        return None
    return corps if isinstance(corps, dict) else None


@role_requis(CABINET, PRINCIPALE)
def api_versions(request, mois):
    """`POST {version_de_base, state}` → 201 `{numero}`, 409 `{derniere}`, 422 `{violations}`."""
    if request.method != "POST":
        return _json_405()
    try:
        plage_mois(mois)
    except ValueError:
        return JsonResponse({"erreur": "mois_invalide"}, status=400)

    try:
        taille = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        taille = 0
    if taille > CORPS_MAX_OCTETS:
        return JsonResponse({"erreur": "corps_trop_volumineux"}, status=413)

    corps = _corps_json(request)
    if corps is None:
        return JsonResponse({"erreur": "corps_invalide"}, status=400)
    base = corps.get("version_de_base")
    if isinstance(base, bool) or not isinstance(base, int) or base < 0:
        return JsonResponse({"erreur": "version_de_base_invalide"}, status=400)

    try:
        version = services.enregistrer(mois, base, corps.get("state"), request.user)
    except services.Conflit as conflit:
        logger.info("planning %s : conflit de version (derniere %s)", mois, conflit.derniere)
        return JsonResponse({"derniere": conflit.derniere}, status=409)
    except services.Invalide as invalide:
        logger.info(
            "planning %s : enregistrement refuse, %s violation(s)",
            mois,
            len(invalide.violations),
        )
        return JsonResponse(
            {"violations": [v.en_dict() for v in invalide.violations]}, status=422
        )

    return JsonResponse({"numero": version.numero}, status=201)


@role_requis(CABINET, PRINCIPALE)
def api_publier(request, mois, numero):
    """`POST` → 200 `{numero, publie_le}` ou `{numero, deja_publiee}`, 409 `{derniere}`, 422 `{violations}`.

    Le numéro est dans l'URL, le corps est ignoré. Même session et même CSRF
    que l'enregistrement.
    """
    if request.method != "POST":
        return _json_405()
    try:
        plage_mois(mois)
    except ValueError:
        return JsonResponse({"erreur": "mois_invalide"}, status=400)
    numero = int(numero)
    if numero == 0:
        return JsonResponse({"erreur": "numero_invalide"}, status=400)

    try:
        version = services.publier(mois, numero, request.user)
    except services.Conflit as conflit:
        logger.info(
            "planning %s : publication refusee, la version %s n'est plus la derniere (%s)",
            mois,
            numero,
            conflit.derniere,
        )
        return JsonResponse({"derniere": conflit.derniere}, status=409)
    except services.DejaPubliee:
        return JsonResponse({"numero": numero, "deja_publiee": True}, status=200)
    except services.Invalide as invalide:
        logger.info(
            "planning %s : publication refusee, %s violation(s)",
            mois,
            len(invalide.violations),
        )
        return JsonResponse(
            {"violations": [v.en_dict() for v in invalide.violations]}, status=422
        )

    return JsonResponse(
        {"numero": version.numero, "publie_le": version.publie_le.isoformat()},
        status=200,
    )


# --- Mes jours (brique 4b) --------------------------------------------------------


@role_requis(SALARIEE, PRINCIPALE)
def mes_jours_courant(request):
    """`/mes-jours/` → le mois en cours (fuseau Europe/Paris)."""
    return redirect("planning:mes_jours", mois=timezone.localdate().strftime("%Y-%m"))


@role_requis(SALARIEE, PRINCIPALE)
def mes_jours(request, mois):
    """« Mes jours » : les jours de la salariée dans le planning publié, sans `DATA`.

    Un compte sans personne rattachée (décision H) voit un message, pas un 500.
    Le log ne porte que le mois et un comptage.
    """
    _plage_ou_404(mois)
    personne = request.user.personne
    resultat = services.jours_publies(personne, mois) if personne is not None else None
    logger.info("mes jours %s : %s jour(s)", mois, len(resultat["jours"]) if resultat else 0)
    return render(
        request,
        "planning/mes_jours.html",
        {
            "mois": mois,
            "libelle": libelle_mois(mois),
            "precedent": mois_precedent(mois),
            "suivant": mois_suivant(mois),
            "personne": personne,
            "sans_personne": personne is None,
            "resultat": resultat,
        },
    )


def _reponse_429(request):
    return JsonResponse({"erreur": "trop_de_demandes"}, status=429)


# Le plafond par IP s'applique AVANT le contrôle de rôle (patron de
# `demander_lien`) : un appelant qui martèle la route ne la fait pas travailler.
@limite_par_ip("erreurs", "DEBIT_ERREURS_IP", reponse=_reponse_429, defaut=DEBIT_ERREURS_DEFAUT)
@role_requis(CABINET, PRINCIPALE)
def api_erreurs(request):
    """Rapport d'une erreur JS de la page : journalisé, jamais stocké.

    Le corps n'est lu que pour quatre champs courts (`nom`, `source`, `ligne`,
    `mois`). Un `message` éventuel est ignoré : il pourrait porter un fragment
    de donnée.
    """
    if request.method != "POST":
        return _json_405()
    corps = _corps_json(request) or {}
    champs = {
        cle: str(corps.get(cle, ""))[:LONGUEUR_MAX_ERREUR]
        for cle in ("nom", "source", "ligne", "mois")
    }
    logger.error(
        "page planning : erreur %s (%s:%s, mois %s)",
        champs["nom"],
        champs["source"],
        champs["ligne"],
        champs["mois"],
    )
    return JsonResponse({"recu": True}, status=202)
