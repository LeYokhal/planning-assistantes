"""Construction de `DATA`, les données servies à la page planning (brique 4a).

Port section par section de `reference/skill-v1/scripts/build_planning.py`
(l.97-320, `main`), à partir des tables de l'application au lieu des fichiers
de travail du skill (`fiche.json`, `conges.json`, `s7_*.json`). Le contrat
`DATA` est celui que le gabarit lit ; les seules clés nouvelles sont
`meta.non_couverts`, `meta.alertes` et `attentes`, que l'ancien code ignore.

Différences assumées avec le skill, toutes signalées dans `meta.alertes` :

* le skill s'arrêtait (`sys.exit`) sur un praticien sans agenda ni jours fixes
  ou sur des heures sans gabarit ; ici la personne est exclue et signalée ;
* le skill supposait 39 h à une salariée sans heures ; ici elle est exclue et
  signalée (`heures_supposees` reste dans le contrat, toujours faux) ;
* les cours des étudiantes viennent des absences de type « Ecole » sur la
  personne, plus du titre d'une entrée Notion.

⚠️ `conges[].type` porte le libellé du type d'absence (décision C4.1) : il est
servi aux rôles cabinet et principale, à l'écran et dans la copie HTML, jamais
dans le `state`, l'audit, les logs ou l'export JSON. Toute la mise en forme du
type passe par `libelle_conge()` : revenir à un code neutre tient en une ligne.

Rien n'est écrit ici : le module lit les tables et rend un dictionnaire.
"""

import collections
import datetime

from django.utils import timezone

from absences.models import AbsenceSalariee
from absences.services import absences_du_mois
from comptes.models import Personne
from comptes.noms import JOURS_FR, code_pour, jour_canonique, normaliser
from presences.fenetres import libelle_mois, plage_mois
from presences.lecture import VERDICT_NON_PLANIFIE
from presences.services import imports_par_date, jour_brut
from regles.chargeur import charger, couleur_hex, resoudre
from socle.feries import feries_entre

SEUILS_DEFAUT = {"courte_h": 4.0, "presence_h": 5.0}
LIBELLE_ECOLE = "Ecole"
SOURCE = "app"

SALARIEES = (Personne.RoleMetier.ASSISTANTE, Personne.RoleMetier.SECRETAIRE)


# --- Petites briques -----------------------------------------------------------


def identifiant(personne):
    """Identifiant stable d'une personne dans `DATA` : `Personne.code`.

    Si le code est nul (collision, `Personne.save`), repli déterministe
    `code_pour(prenom, nom) + pk`, calculé à chaque rendu et jamais écrit en
    base (décision D). `construire` pose une alerte quand le repli sert.
    """
    if personne.code:
        return personne.code
    return f"{code_pour(personne.prenom, personne.nom)}{personne.pk}"


def libelle_conge(absence):
    """Le libellé du type porté dans `conges[].type` (décision C4.1, une ligne)."""
    return absence.type.libelle


def _nom(personne):
    return f"{personne.nom} {personne.prenom}"


def _jours_fixes(personne):
    """Jours fixes en entiers 0-6 (lundi = 0), ordre de la fiche, illisibles ignorés."""
    jours = []
    for brut in personne.jours_fixes or ():
        canonique = jour_canonique(brut) if isinstance(brut, str) else None
        if canonique is None:
            continue
        rang = JOURS_FR.index(canonique)
        if rang not in jours:
            jours.append(rang)
    return jours


def _creneaux(bruts):
    """Créneaux compactés `[[debut, fin], …]`, depuis `creneaux` (pas les effectifs).

    Le payload réel porte des objets `{debut, fin}` (skill l.243) ; la fabrique
    de test des présences porte des couples. Les deux formes sont lues.
    """
    creneaux = []
    for creneau in bruts or ():
        if isinstance(creneau, dict) and "debut" in creneau and "fin" in creneau:
            creneaux.append([str(creneau["debut"]), str(creneau["fin"])])
        elif isinstance(creneau, (list, tuple)) and len(creneau) == 2:
            creneaux.append([str(creneau[0]), str(creneau[1])])
    return creneaux


def _dates(absence, plage):
    """Dates ISO d'une absence, bornées à la plage."""
    debut = max(absence.date_debut, plage.debut)
    fin = min(absence.date_fin, plage.fin)
    return [
        (debut + datetime.timedelta(days=n)).isoformat()
        for n in range((fin - debut).days + 1)
    ]


def _nombre(valeur, defaut):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return float(valeur)


# --- Couverture ----------------------------------------------------------------


def mois_couvert(plage):
    """Vrai si au moins un jour de la plage est couvert par un import réussi."""
    return bool(imports_par_date(plage.debut, plage.fin))


# --- Construction ---------------------------------------------------------------


def construire(mois, regles=None):
    """Rend le dictionnaire `DATA` du mois « AAAA-MM ».

    `regles` permet aux tests d'injecter un jeu fictif ; par défaut, les règles
    du dépôt, déjà chargées au démarrage.
    """
    regles = regles or charger()
    plage = plage_mois(mois)
    alertes = []
    signalees = set()

    def alerter(message):
        if message not in signalees:
            signalees.add(message)
            alertes.append(message)

    personnes = list(Personne.objects.filter(planifiee=True, actif=True))
    par_pk = {p.pk: p for p in personnes}

    # --- 3. praticiens et salariées (skill l.135-186)
    praticiens, salaries = [], []
    prat_par_pk, sal_par_pk = {}, {}
    for personne in personnes:
        if personne.role_metier == Personne.RoleMetier.PRATICIEN:
            agenda = (personne.agenda_doctolib or "").strip() or None
            fixes = _jours_fixes(personne)
            if agenda is None and not fixes:
                alerter(
                    f"{_nom(personne)} : praticien planifié sans agenda Doctolib "
                    "ni jours fixes, exclu du planning"
                )
                continue
            entree = {
                "id": identifiant(personne),
                "label": personne.prenom,
                "nom": _nom(personne),
                "agenda": agenda,
                "couleur": list(couleur_hex(personne.couleur, regles)),
                "fixes": fixes,
                "attendues": 1,
                "exclusif": False,
                "binomes": [],
                "a_part": False,
                "etiquette": None,
            }
            praticiens.append(entree)
            prat_par_pk[personne.pk] = entree
        elif personne.role_metier in SALARIEES:
            heures = personne.heures_hebdo
            fixes = _jours_fixes(personne)
            heures_fixes = False
            if heures:
                gabarit = regles.gabarits.get(int(heures))
                if gabarit is None:
                    alerter(
                        f"{_nom(personne)} : heures {heures} hors gabarits "
                        f"({', '.join(str(h) for h in sorted(regles.gabarits))}), "
                        "exclue du planning"
                    )
                    continue
                gabarit = list(gabarit)
            elif personne.role_metier == Personne.RoleMetier.SECRETAIRE and fixes:
                # Règle du skill (l.171-174) : ses jours fixes FONT son contrat.
                heures = round(len(fixes) * regles.heures_par_brique["J"], 2)
                gabarit = ["J"] * len(fixes)
                heures_fixes = True
            else:
                alerter(
                    f"{_nom(personne)} : ni heures hebdomadaires ni jours fixes, "
                    "exclue du planning"
                )
                continue
            entree = {
                "id": identifiant(personne),
                "label": personne.prenom,
                "nom": _nom(personne),
                "role": str(personne.role_metier),
                "heures": heures,
                "heures_supposees": False,
                "heures_fixes": heures_fixes,
                "gabarit": gabarit,
                "fixes": fixes,
                "couleur": list(couleur_hex(personne.couleur, regles)),
                "binomes": [],
                "exclusif": False,
                "admin": None,
            }
            salaries.append(entree)
            sal_par_pk[personne.pk] = entree

    for pk, entree in list(prat_par_pk.items()) + list(sal_par_pk.items()):
        if not par_pk[pk].code:
            alerter(
                f"{_nom(par_pk[pk])} : code en collision, identifiant provisoire "
                f"« {entree['id']} » — à saisir dans l'administration"
            )

    # --- 3b. règles (skill l.188-225), noms résolus en personnes
    resolus = resoudre(regles, personnes)

    def salariee(nom, quoi):
        personne = resolus.get(normaliser(nom))
        entree = sal_par_pk.get(personne.pk) if personne else None
        if entree is None:
            alerter(f"règle ignorée : {quoi} « {nom} » absente des personnes planifiées")
        return entree

    def praticien(nom, quoi):
        personne = resolus.get(normaliser(nom))
        entree = prat_par_pk.get(personne.pk) if personne else None
        if entree is None:
            alerter(f"règle ignorée : {quoi} « {nom} » absent des personnes planifiées")
        return entree

    for binome in regles.binomes:
        s = salariee(binome.assistante, "assistante")
        p = praticien(binome.praticien, "praticien")
        if s and p:
            s["binomes"].append(p["id"])
            p["binomes"].append(s["id"])
            if binome.exclusif:
                s["exclusif"] = True
    for nom in regles.praticiens_exclusifs:
        p = praticien(nom, "praticien exclusif")
        if p:
            p["exclusif"] = True
            p["attendues"] = max(1, len(p["binomes"]))
    for a_part in regles.praticiens_a_part:
        p = praticien(a_part.nom, "praticien à part")
        if p:
            p["a_part"] = True
            p["etiquette"] = a_part.etiquette
    # Les praticiens à part passent en fin de liste (tri stable, skill l.209).
    praticiens.sort(key=lambda p: p["a_part"])
    etudiantes = set()
    for etudiante in regles.etudiantes:
        s = salariee(etudiante.nom, "étudiante")
        if s:
            s["etudiante"] = True
            s["gabarit"] = list(etudiante.gabarit_sans_cours)
            etudiantes.add(s["id"])
    for creneau in regles.creneaux_administratifs:
        s = salariee(creneau.salariee, "salariée")
        if s:
            s["admin"] = creneau.brique

    # --- libellés : prénom, ou prénom + initiale du nom si doublon (skill l.140-143)
    inclus = [par_pk[pk] for pk in list(prat_par_pk) + list(sal_par_pk)]
    prenoms = collections.Counter(p.prenom for p in inclus)
    for pk, entree in list(prat_par_pk.items()) + list(sal_par_pk.items()):
        personne = par_pk[pk]
        if prenoms[personne.prenom] > 1:
            entree["label"] = f"{personne.prenom} {personne.nom[:1]}"

    # --- 4. présence compacte depuis les imports (skill l.227-249)
    retenus = imports_par_date(plage.debut, plage.fin)
    jours = {}
    agendas_vus = set()
    for cle in sorted(retenus):
        brut = jour_brut(retenus[cle], cle) or {}
        par_agenda = {}
        for ligne in brut.get("praticiens") or []:
            if isinstance(ligne, dict):
                par_agenda[str(ligne.get("praticien", "")).strip()] = ligne
        agendas_vus.update(par_agenda)
        for p in praticiens:
            if not p["agenda"]:
                continue
            ligne = par_agenda.get(p["agenda"])
            if ligne is None:
                continue
            triviale = (
                not ligne.get("presence")
                and ligne.get("verdict") == VERDICT_NON_PLANIFIE
                and not ligne.get("nb_rdv")
            )
            if triviale:
                continue
            creneaux = _creneaux(ligne.get("creneaux"))
            jours.setdefault(cle, {})[p["id"]] = {
                "pr": bool(ligne.get("presence")),
                "v": str(ligne.get("verdict", "")),
                "c": creneaux,
                "fin": creneaux[-1][1] if creneaux else None,
                "n": ligne.get("nb_rdv") or 0,
                "jc": bool(ligne.get("journee_courte")),
                "min": ligne.get("duree_rdv_vivants_minutes") or 0,
            }
    if retenus:
        for p in praticiens:
            if p["agenda"] and p["agenda"] not in agendas_vus:
                alerter(
                    f"agenda « {p['agenda']} » sans ligne dans les imports du mois "
                    f"({p['label']} n'apparaîtra jamais présent)"
                )

    non_couverts = []
    jour = plage.debut
    while jour <= plage.fin:
        if jour.isoformat() not in retenus:
            non_couverts.append(jour.isoformat())
        jour += datetime.timedelta(days=1)

    # Seuils du premier import de la plage ; à défaut, ceux du skill.
    seuils = dict(SEUILS_DEFAUT)
    if retenus:
        premier = retenus[min(retenus)]
        donnees = (premier.payload or {}).get("donnees") or {}
        courte = _nombre(donnees.get("seuil_heures"), None)
        presence = _nombre(donnees.get("seuil_presence"), None)
        if courte is None or presence is None:
            alerter("seuils absents du payload importé : valeurs par défaut (4 h / 5 h)")
        else:
            seuils = {"courte_h": courte, "presence_h": presence}
    else:
        alerter("aucun import réussi ne couvre la plage")
    enveloppes = [
        import_.message
        for import_ in sorted(set(retenus.values()), key=lambda i: i.pk)
    ]

    # --- 5. congés, cours, demandes en attente (skill l.251-289)
    conges, attentes, cours = [], [], {}
    for absence in absences_du_mois(plage.debut, plage.fin, pour_la_paie=False):
        s = sal_par_pk.get(absence.personne_id)
        if s is None:
            # Hors périmètre (non planifiée, inactive, praticien) : écartée
            # sans alerte, pour ne rien dire d'une personne absente de la page.
            continue
        if absence.type.libelle == LIBELLE_ECOLE and s["id"] in etudiantes:
            cours.setdefault(s["id"], set()).update(_dates(absence, plage))
            continue
        for iso in _dates(absence, plage):
            conges.append(
                {
                    "s": s["id"],
                    "date": iso,
                    "type": libelle_conge(absence),
                    "bloque": bool(absence.type.bloquant),
                }
            )
    en_attente = (
        AbsenceSalariee.objects.filter(
            statut=AbsenceSalariee.Statut.EN_ATTENTE,
            date_debut__lte=plage.fin,
            date_fin__gte=plage.debut,
        )
        .select_related("personne")
        .order_by("personne__nom", "personne__prenom", "date_debut")
    )
    for absence in en_attente:
        s = sal_par_pk.get(absence.personne_id)
        if s is None:
            continue
        for iso in _dates(absence, plage):
            attentes.append({"s": s["id"], "date": iso})
    cours = {sid: sorted(dates) for sid, dates in cours.items()}

    # --- 6. fériés de la plage (skill l.291-296)
    feries = {
        jour.isoformat(): nom
        for jour, nom in sorted(feries_entre(plage.debut, plage.fin).items())
    }

    return {
        "meta": {
            "mois": mois,
            "libelle": libelle_mois(mois),
            "debut": plage.debut.isoformat(),
            "fin": plage.fin.isoformat(),
            "genere": timezone.now().isoformat(),
            "source": SOURCE,
            "heures": {
                "J": regles.heures_par_brique["J"],
                "C": regles.heures_par_brique["C"],
            },
            "seuils": seuils,
            "enveloppes": enveloppes,
            "non_couverts": non_couverts,
            "alertes": alertes,
        },
        "praticiens": praticiens,
        "salaries": salaries,
        "jours": jours,
        "conges": conges,
        "feries": feries,
        "cours": cours,
        "attentes": attentes,
    }
