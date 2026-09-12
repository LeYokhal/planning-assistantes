"""Vues du planning : page du mois, lecture historique, copie autonome, API, erreurs.

Les logs de ce module ne portent que le mois, un numéro de version, un nombre
de violations ou un nom de classe d'erreur JS : jamais un nom de personne,
jamais un type d'absence.
"""

import datetime
import json
import logging
from pathlib import Path

from django.contrib.staticfiles import finders
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from absences.models import AbsenceSalariee
from comptes.acces import role_requis
from comptes.models import Compte, Personne
from comptes.noms import JOURS_FR, normaliser
from presences.fenetres import libelle_mois, mois_precedent, mois_suivant, plage_mois
from presences.models import ImportPresences
from regles.chargeur import charger, couleur_hex, jours_ouverture, resoudre
from socle.debit import limite_par_ip
from socle.feries import feries_entre

from . import donnees, espace_salariee, services

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
    precedent, suivant = mois_precedent(mois), mois_suivant(mois)
    return {
        "mois": mois,
        "libelle": libelle_mois(mois),
        "precedent": precedent,
        "suivant": suivant,
        # Brique 6d : les mois voisins de l'en-tête (« ‹ » / « › »), servis en
        # valeurs à `_corps.html` — partagé avec la copie autonome, ce gabarit ne
        # porte aucune URL de l'application ; la copie est rendue sans `nav_mois`.
        "nav_mois": {"precedent": _lien_mois(precedent), "suivant": _lien_mois(suivant)},
        "peut_importer": request.user.role == CABINET,
    }


def _lien_mois(mois):
    return {"url": reverse("planning:mois", kwargs={"mois": mois}), "libelle": libelle_mois(mois)}


def _meta(mois, numero, autonome, publiee=0, donnees_du=None):
    """`{mois, numero, autonome, publiee, urls, donnees_du}` : `publiee` = numéro de la
    version publiée courante, 0 sinon ; `urls.publier` n'existe que s'il y a une version ;
    `donnees_du` = date locale (« AAAA-MM-JJ ») du dernier import Doctolib retenu, ou
    None (brique 6d, pastille « Données Doctolib du … »)."""
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
        "donnees_du": donnees_du.isoformat() if donnees_du else None,
    }


def _numero_publie(mois):
    publiee = services.version_publiee(mois)
    return publiee.numero if publiee else 0


def _donnees_du(data):
    """Date locale du dernier import retenu pour le mois, ou None.

    Les imports retenus sont ceux de `DATA.meta.imports` (identifiants et
    empreintes, rien d'autre) : une requête d'agrégat, `donnees.py` intouché.
    """
    ids = [import_["id"] for import_ in data["meta"]["imports"]]
    if not ids:
        return None
    valeur = ImportPresences.objects.filter(pk__in=ids).aggregate(Max("importe_le"))
    dernier = valeur["importe_le__max"]
    return timezone.localdate(dernier) if dernier else None


# Brique 6d (E4) : le suffixe des alertes de collision de code s'adresse au cabinet,
# seul rôle à voir l'administration ; la principale le signale.
SUFFIXE_CABINET = " — à saisir dans l'administration"
SUFFIXE_PRINCIPALE = " — à signaler au cabinet"


def _alertes_pour(alertes, role):
    """Les alertes de `DATA.meta` reformulées pour le rôle : nouvelle liste, même contrat."""
    if role != PRINCIPALE:
        return list(alertes)
    return [alerte.replace(SUFFIXE_CABINET, SUFFIXE_PRINCIPALE) for alerte in alertes]


def _data_pour(request, mois):
    """`DATA` du mois, ses alertes reformulées pour le rôle du compte."""
    data = donnees.construire(mois)
    data["meta"]["alertes"] = _alertes_pour(data["meta"]["alertes"], request.user.role)
    return data


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
        # Brique 7b : un mois de 2026 repris par l'import historique n'a pas de
        # présences et n'en aura pas ; l'écran renvoie vers sa page de lecture.
        publiee = services.version_publiee(mois)
        if publiee is not None and services.est_historique(publiee):
            contexte["historique"] = publiee
        return render(request, "planning/sans_import.html", contexte)

    derniere = services.derniere_version(mois)
    numero = derniere.numero if derniere else 0
    data = _data_pour(request, mois)
    contexte.update(
        {
            "data": data,
            "state": derniere.state if derniere else services.etat_vide(),
            "meta": _meta(
                mois, numero, autonome=False, publiee=_numero_publie(mois), donnees_du=_donnees_du(data)
            ),
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
    # Brique 7b (D6) : sans présences, `DATA.jours` est vide et la copie sortirait
    # un document au moteur muet — un fichier durable et trompeur. La lecture d'un
    # mois historique passe par `planning_historique`.
    if services.est_historique(derniere):
        raise Http404("mois historique : pas de copie autonome")

    data = _data_pour(request, mois)
    contexte = {
        "mois": mois,
        "libelle": libelle_mois(mois),
        "data": data,
        "state": derniere.state,
        "meta": _meta(
            mois, derniere.numero, autonome=True, publiee=_numero_publie(mois), donnees_du=_donnees_du(data)
        ),
    }
    contexte.update({cle: _statique(chemin) for cle, chemin in STATIQUES.items()})
    html = render_to_string("planning/copie.html", contexte, request=request)

    reponse = HttpResponse(html, content_type="text/html; charset=utf-8")
    reponse["Content-Disposition"] = (
        f'attachment; filename="planning-assistantes_{mois}_v{derniere.numero}.html"'
    )
    return reponse


# --- Lecture d'un mois historique (brique 7b) -------------------------------------

# Rang de tri des colonnes : les praticiens d'abord, les cases hors praticien
# ensuite, les slots que plus aucune fiche ne porte en dernier (décision D9).
RANG_PRATICIEN, RANG_MISC, RANG_INCONNU = 0, 1, 2


def _horodatage(valeur):
    """Un ISO 8601 relu en `datetime`, ou None si la valeur manque ou ment."""
    try:
        return datetime.datetime.fromisoformat(str(valeur))
    except (TypeError, ValueError):
        return None


def _praticiens_a_part(regles, personnes):
    """Les `pk` des praticiens que les règles mettent en fin de liste.

    Même résolution des noms que `donnees.construire` : `regles.chargeur.resoudre`,
    puis `normaliser`. Un nom que la fiche ne porte pas est simplement absent.
    """
    resolus = resoudre(regles, personnes)
    return {
        resolus[cle].pk
        for cle in (normaliser(a.nom) for a in regles.praticiens_a_part)
        if cle in resolus
    }


def _colonnes_historiques(affectations, regles):
    """Les colonnes du tableau, dans l'ordre de la décision D9.

    ⚠️ Les codes sont résolus **sans filtre `actif` ni `planifiee`** (C7.4) : une
    fiche de praticien fermée, sans agenda Doctolib, garde sa colonne — c'est
    l'inverse de `donnees.construire`, et c'est voulu.
    """
    connues = {
        p.code: p for p in Personne.objects.exclude(code=None).exclude(code="")
    }
    a_part = _praticiens_a_part(regles, connues.values())
    rangs_misc = {slot: rang for rang, slot in enumerate(services.LIBELLES_MISC)}
    defaut = list(couleur_hex("", regles))

    colonnes = {}
    for slots in affectations.values():
        if not isinstance(slots, dict):
            continue
        for slot, briques in slots.items():
            if not briques or slot in colonnes:
                continue
            if slot in services.LIBELLES_MISC:
                colonnes[slot] = {
                    "slot": slot,
                    "libelle": services.LIBELLES_MISC[slot],
                    "fiche_close": False,
                    "couleur": defaut,
                    "tri": (RANG_MISC, rangs_misc[slot], "", ""),
                }
                continue
            personne = connues.get(slot)
            if personne is None:
                colonnes[slot] = {
                    "slot": slot,
                    "libelle": slot,
                    "fiche_close": False,
                    "couleur": defaut,
                    "tri": (RANG_INCONNU, 0, slot, ""),
                }
                continue
            colonnes[slot] = {
                "slot": slot,
                "libelle": str(personne),
                "fiche_close": not personne.actif,
                "couleur": list(couleur_hex(personne.couleur, regles)),
                "tri": (
                    RANG_PRATICIEN,
                    int(personne.pk in a_part),
                    personne.nom,
                    personne.prenom,
                ),
            }
    return sorted(colonnes.values(), key=lambda c: c["tri"]), connues


def _lignes_historiques(plage, state, colonnes, connues, regles):
    """Une ligne par journée retenue, avec ses cellules.

    Une journée est retenue si le cabinet **ouvre** ce jour-là — au régime daté
    de `regles.json`, par `regles.chargeur.jours_ouverture` (C3.2, la règle du
    calcul de paie, jamais réécrite) — **ou** si elle porte au moins une brique.
    Un jour retenu par ses seules briques est marqué « hors jours d'ouverture ».

    Les fériés viennent de `socle.feries.feries_entre`, comme `donnees.construire` :
    les fichiers repris portent un `feries` vide. La combinaison reprend celle du
    moteur (`isFerie`) : un férié du calendrier rouvert par `feries_off` ne compte
    plus, un férié posé dans la page compte toujours.
    """
    affectations = state.get("affectations") or {}
    feries_calendrier = {
        jour.isoformat(): nom
        for jour, nom in feries_entre(plage.debut, plage.fin).items()
    }
    feries_page = state.get("feries") or {}
    feries_off = set(state.get("feries_off") or [])

    lignes = []
    jour = plage.debut
    while jour <= plage.fin:
        iso = jour.isoformat()
        slots = affectations.get(iso) or {}
        porte_une_brique = any(slots.get(c["slot"]) for c in colonnes)
        ouvert = JOURS_FR[jour.weekday()] in jours_ouverture(jour, regles)
        if not ouvert and not porte_une_brique:
            jour += datetime.timedelta(days=1)
            continue

        ferie = feries_page.get(iso) or (
            feries_calendrier.get(iso) if iso not in feries_off else None
        )
        lignes.append(
            {
                "date": jour,
                "jour_fr": JOURS_FR[jour.weekday()],
                "hors_ouverture": not ouvert,
                "ferie": ferie,
                "cellules": [
                    _cellule(slots.get(colonne["slot"]), connues) for colonne in colonnes
                ],
            }
        )
        jour += datetime.timedelta(days=1)
    return lignes


def _cellule(briques, connues):
    """Les briques d'une case : le libellé de la personne, `t` et `x` bruts.

    Un code que plus aucune fiche ne porte reste affiché tel quel — c'est ce que
    fait déjà « Mes jours » d'un slot introuvable.
    """
    if not isinstance(briques, list):
        return []
    rendu = []
    for brique in briques:
        if not isinstance(brique, dict):
            continue
        code = brique.get("s")
        personne = connues.get(code)
        rendu.append(
            {
                "libelle": str(personne) if personne else str(code),
                "t": brique.get("t"),
                "x": bool(brique.get("x")),
            }
        )
    return rendu


@role_requis(CABINET, PRINCIPALE)
def planning_historique(request, mois):
    """Lecture d'un mois repris par l'import historique (brique 7b, décision D3).

    Page **serveur**, bâtie sur le `state` de la version publiée et sur les
    personnes — jamais `DATA`, jamais `STATE`, jamais le moteur, comme
    « Mes jours » (§ 11.3 de `docs/PLANNING.md`). Ces mois n'ont aucune présence
    Doctolib : `donnees.construire` ne dessinerait aucune colonne de praticien et
    passerait tout le planning en « hors présence ».

    404 si le mois n'a pas de version publiée, ou si sa version publiée n'est pas
    historique : une version ordinaire se lit sur la page normale.

    Aucune absence n'est lue : le `state` n'en porte pas, et la page n'interroge
    ni `absences`, ni `DATA`.
    """
    plage = _plage_ou_404(mois)
    version = services.version_publiee(mois)
    if version is None or not services.est_historique(version):
        raise Http404("aucun planning historique publié pour ce mois")

    regles = charger()
    state = version.state or {}
    affectations = state.get("affectations") or {}
    colonnes, connues = _colonnes_historiques(affectations, regles)
    lignes = _lignes_historiques(plage, state, colonnes, connues, regles)
    notes = sorted(
        (iso, textes)
        for iso, textes in (state.get("notes") or {}).items()
        if textes
    )

    logger.info(
        "planning %s : historique v%s lu (%s jours)", mois, version.numero, len(lignes)
    )
    return render(
        request,
        "planning/historique.html",
        {
            "mois": mois,
            "libelle": libelle_mois(mois),
            "precedent": mois_precedent(mois),
            "suivant": mois_suivant(mois),
            "version": version,
            "importe_le": _horodatage((version.verifications or {}).get("importe_le")),
            "colonnes": colonnes,
            "lignes": lignes,
            "notes": notes,
        },
    )


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

    Brique 6b (C6.8) : en grille du mois, avec ses absences, les fériés du
    calendrier et les marqueurs d'effectif de la version publiée (C6.9) ; la
    grille est un calcul pur (`espace_salariee`). Un compte sans personne
    rattachée (décision H) voit un message, pas un 500. Le log ne porte que le
    mois et un comptage.
    """
    plage = _plage_ou_404(mois)
    personne = request.user.personne
    resultat = services.jours_publies(personne, mois) if personne is not None else None
    grille = None
    if resultat is not None:
        # Ses absences seulement : une requête, filtrée sur la personne du compte,
        # jamais sur un identifiant venu de l'URL.
        statuts = (
            AbsenceSalariee.Statut.EN_ATTENTE,
            AbsenceSalariee.Statut.VALIDEE,
            AbsenceSalariee.Statut.DECLAREE,
        )
        absences = list(
            AbsenceSalariee.objects.filter(
                personne=personne,
                date_debut__lte=plage.fin,
                date_fin__gte=plage.debut,
                statut__in=statuts,
            )
            .select_related("type")
            .order_by("date_debut")
        )
        feries = {
            jour.isoformat(): nom for jour, nom in feries_entre(plage.debut, plage.fin).items()
        }
        grille = espace_salariee.construire_grille(
            resultat, absences, feries, mois, timezone.localdate()
        )
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
            "grille": grille,
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
