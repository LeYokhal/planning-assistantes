/* Moteur du planning assistantes — brique 4a.

   Port de la partie sans DOM du gabarit du skill v1
   (reference/skill-v1/assets/gabarit.html, l.337-741) : calendrier, réserve
   hebdomadaire, proposition, mutations de l'état, vérification stricte.

   Forme : `PlanningMoteur.creer(DATA, state)` rend un objet de fonctions
   fermées sur `DATA` et sur `state`, muté EN PLACE et jamais réassigné.
   Aucune fonction d'ici n'appelle `commit`, `render`, `toast` ni `confirm` :
   le moteur mute et rend des résultats, page.js affiche.

   Le même fichier tourne dans le navigateur (`window.PlanningMoteur`) et sous
   Node (`module.exports`, tests `planning/tests_js/`). Aucune dépendance.

   Les règles strictes de `verifier()` sont les mêmes, avec les mêmes codes,
   que `planning/verification.py` ; les deux sont éprouvées sur
   `planning/tests/cas_verification.json`. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) { module.exports = factory(); }
  else { root.PlanningMoteur = factory(); }
})(this, function () {
"use strict";

const DOW_ABR = ["lun.","mar.","mer.","jeu.","ven.","sam.","dim."];
const MOIS = ["janv.","févr.","mars","avr.","mai","juin","juil.","août","sept.","oct.","nov.","déc."];
const MISC = [["sureffectif","sur","Sureffectif"],["secretariat","secr","Secrétariat"],["administratif","adm","Administratif"]];
const MISC_SLOTS = ["secretariat","sureffectif","administratif"];
const MISC_LABEL = {sureffectif:"en sureffectif", secretariat:"au secrétariat", administratif:"en administratif"};
// trois types d'absence stylés ; les autres s'affichent avec leur libellé
const ABS = {"Congé payé": {code:"CP", cls:"abs-cp", libelle:"congé payé"}, "Maladie": {code:"MAL", cls:"abs-mal", libelle:"maladie"}, "Congé sans solde": {code:"SS", cls:"abs-ss", libelle:"sans solde"}};
const BRIQUES = ["J","C"];
const CLES_STATE = ["affectations","feries","feries_off","notes"];
const CODES = ["hors_plage","salariee_inconnue","slot_inconnu","brique_invalide","doublon_jour","jour_bloque","jour_non_affiche","sans_donnees","praticien_absent","capacite","exclusive_ailleurs","exclusif_intrus","quota_depasse"];

// ------------------------------------------------------------ dates (pures)
const toDate = iso => new Date(iso + "T12:00:00");
const toIso = d => d.toISOString().slice(0,10);
const addDays = (iso,n) => { const d = toDate(iso); d.setDate(d.getDate()+n); return toIso(d); };
const weekday = iso => (toDate(iso).getDay()+6)%7;  // 0 = lundi
const isoWeek = iso => { const d = toDate(iso); d.setDate(d.getDate()+3-weekday(iso)); const y=new Date(d.getFullYear(),0,4); return 1+Math.round(((d-y)/86400000-3+((y.getDay()+6)%7))/7); };
const fmtJour = iso => { const d = toDate(iso); return `${d.getDate()} ${MOIS[d.getMonth()]}`; };
const heure = h => h ? h.replace(":", "h").replace(/h00$/,"h") : "";
const fmtH = h => { const m = Math.round(h * 60), hh = Math.floor(m / 60), mm = m % 60; return mm ? `${hh} h ${String(mm).padStart(2,"0")}` : `${hh} h`; };
const dateValide = iso => typeof iso === "string" && /^\d{4}-\d{2}-\d{2}$/.test(iso) && !isNaN(toDate(iso).getTime()) && toIso(toDate(iso)) === iso;

// ------------------------------------------------------------ état : nettoyage et empreinte
const estObjet = v => !!v && typeof v === "object" && !Array.isArray(v);
const listeDeNotes = brut => (typeof brut === "string" ? [brut] : Array.isArray(brut) ? brut : []).filter(x => typeof x === "string").map(x => x.trim()).filter(Boolean);

function nettoyer(brut) {   // les quatre clés du contrat, copiées ; même règle que verification.nettoyer
  const src = estObjet(brut) ? brut : {};
  const affectations = estObjet(src.affectations) ? JSON.parse(JSON.stringify(src.affectations)) : {};
  const feries = {};
  if (estObjet(src.feries)) for (const [k, v] of Object.entries(src.feries)) feries[String(k)] = String(v);
  const feries_off = Array.isArray(src.feries_off) ? src.feries_off.filter(x => typeof x === "string") : [];
  const notes = {};
  if (estObjet(src.notes)) for (const [k, v] of Object.entries(src.notes)) { const l = listeDeNotes(v); if (l.length) notes[String(k)] = l; }
  return {affectations, feries, feries_off, notes};
}
function canonique(v) {   // JSON à clés triées : deux états égaux donnent la même chaîne
  if (Array.isArray(v)) return "[" + v.map(canonique).join(",") + "]";
  if (estObjet(v)) return "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canonique(v[k])).join(",") + "}";
  return JSON.stringify(v === undefined ? null : v);
}

// ------------------------------------------------------------ fabrique
function creer(DATA, state) {
  if (!estObjet(state)) throw new TypeError("PlanningMoteur.creer : state doit être un objet");
  const propre = nettoyer(state);
  for (const k of Object.keys(state)) if (!CLES_STATE.includes(k)) delete state[k];
  Object.assign(state, propre);
  const HISTORY = [];

  const WEEKS = [];
  for (let iso = DATA.meta.debut; iso <= DATA.meta.fin; iso = addDays(iso,7)) {
    const days = []; for (let i=0;i<7;i++) days.push(addDays(iso,i));
    WEEKS.push({ start: iso, days, num: isoWeek(iso) });
  }
  const SHOWN = (() => {   // colonnes : jours où quelqu'un est présent (Doctolib) ou a un jour fixe ; jamais le dimanche
    const set = new Set();
    for (const [iso, prs] of Object.entries(DATA.jours ?? {})) if (Object.values(prs).some(p => p.pr)) set.add(weekday(iso));
    for (const s of DATA.salaries) (s.fixes ?? []).forEach(w => set.add(w));
    for (const p of DATA.praticiens) if (!p.agenda) (p.fixes ?? []).forEach(w => set.add(w));
    set.delete(6);
    return [0,1,2,3,4,5].filter(w => set.has(w));
  })();
  const SAL = Object.fromEntries(DATA.salaries.map(s => [s.id, s]));
  const PRAT = Object.fromEntries(DATA.praticiens.map(p => [p.id, p]));
  const CONGES = {};
  for (const c of (DATA.conges ?? [])) (CONGES[c.s] ??= {})[c.date] = c;
  const COURS = DATA.cours ?? {};
  const ATTENTES = {};
  for (const a of (DATA.attentes ?? [])) (ATTENTES[a.date] ??= []).push(a.s);
  const NON_COUVERTS = new Set(DATA.meta.non_couverts ?? []);
  const HB = DATA.meta.heures ?? {J: 9.75, C: 6.75};       // heures par brique

  // ------------------------------------------------------------ lecture
  const shownDays = week => week.days.filter(iso => SHOWN.includes(weekday(iso)));
  // fériés : ceux du serveur (calendrier français) sauf rouverts dans la page, plus ceux fermés dans la page
  const isFerie = iso => (iso in DATA.feries && !state.feries_off.includes(iso)) || iso in state.feries;
  const ferieName = iso => state.feries[iso] ?? DATA.feries[iso];
  const congeDe = (sid, iso) => CONGES[sid]?.[iso];              // congés : ceux du serveur seulement
  const coursDe = (sid, iso) => (COURS[sid] ?? []).includes(iso);
  const attentesDe = iso => ATTENTES[iso] ?? [];
  const nonCouvert = iso => NON_COUVERTS.has(iso);
  const bloque = (sid, iso) => isFerie(iso) || (congeDe(sid, iso)?.bloque === true) || coursDe(sid, iso);
  function virtuels(s, week) {   // journées comptées comme placées sans brique : absences, fériés (lundi→vendredi), cours (qui consomment la courte)
    const out = [];
    for (const iso of week.days) {
      if (coursDe(s.id, iso)) { out.push({date: iso, code: "COURS", cls: "abs-cours", type: "Cours", prefer: "C"}); continue; }
      if (!SHOWN.includes(weekday(iso))) continue;
      if (s.role === "secretaire" && s.fixes.length && !s.fixes.includes(weekday(iso))) continue;   // jours fixes : seules leurs journées comptent
      const c = congeDe(s.id, iso);
      if (c?.bloque) out.push({date: iso, code: ABS[c.type]?.code ?? "ABS", cls: ABS[c.type]?.cls ?? "", type: c.type});
      else if (isFerie(iso) && weekday(iso) <= 4) out.push({date: iso, code: "FÉRIÉ", cls: "", type: ferieName(iso)});
    }
    return out;
  }
  function consommer(bricks, items) {   // retire une brique par journée virtuelle : la courte pour un cours, sinon une journée complète d'abord
    const q = bricks.slice();
    for (const it of items) { const t = it.prefer && q.includes(it.prefer) ? it.prefer : q.includes("J") ? "J" : q[q.length - 1]; const i = q.indexOf(t); if (i >= 0) q.splice(i, 1); }
    return q;
  }
  const praticienPresent = (iso, p) => p.agenda ? !!DATA.jours[iso]?.[p.id]?.pr : (p.fixes ?? []).includes(weekday(iso));
  function presents(iso) {   // praticiens à pourvoir ce jour, avec leur ligne S7 ; aucun un jour férié
    const out = [];
    if (isFerie(iso)) return out;
    for (const p of DATA.praticiens) {
      if (p.agenda) { const l = DATA.jours[iso]?.[p.id]; if (l?.pr) out.push({p, l}); }
      else if (p.fixes.includes(weekday(iso))) out.push({p, l:{pr:true, v:"planning fixe", c:[], fin:null, min:0}});
    }
    return out;
  }
  const bricksAt = (iso, slot) => (state.affectations[iso]?.[slot]) ?? [];
  const allBricksOfDay = iso => Object.entries(state.affectations[iso] ?? {}).flatMap(([slot, arr]) => (Array.isArray(arr) ? arr : []).map(b => ({...b, slot})));
  const need = (iso, p) => p.attendues - bricksAt(iso, p.id).length;
  const free = (sid, iso) => !bloque(sid, iso) && !allBricksOfDay(iso).some(b => b.s === sid);
  const finOf = (iso, p) => DATA.jours[iso]?.[p.id]?.fin ?? null;
  const chargePoste = (iso, p) => DATA.jours[iso]?.[p.id]?.min ?? 0;

  function quota(s, week) {  // briques du contrat sur la semaine ; les absences et fériés ne les retirent pas, ils les occupent (cf. reserve)
    const days = shownDays(week);
    if (s.role === "secretaire" && s.fixes.length) return days.filter(iso => s.fixes.includes(weekday(iso))).map(() => "J");
    return s.gabarit.slice();
  }
  function placed(s, week) {
    const out = [];
    for (const iso of week.days) for (const b of allBricksOfDay(iso)) if (b.s === s.id) out.push({...b, date: iso});
    return out;
  }
  function reserve(s, week) {  // types encore à poser + nombre posé en trop sans marque hors-quota ; les absences occupent d'abord les journées complètes
    let q = consommer(quota(s, week), virtuels(s, week)); let over = 0;
    for (const b of placed(s, week)) {
      if (b.x) continue;
      const i = q.indexOf(b.t); if (i >= 0) q.splice(i,1); else if (q.length) q.pop(); else over++;
    }
    return { rest: q, over };
  }
  function heures(s, week) {   // heures de la semaine : posées (hors quota comprises), dues (contrat moins absences/fériés), supplémentaires
    const posees = placed(s, week).reduce((a, b) => a + (HB[b.t] ?? 0), 0);
    const dues = consommer(quota(s, week), virtuels(s, week)).reduce((a, t) => a + (HB[t] ?? 0), 0);
    return { posees, dues, sup: Math.max(0, posees - dues) };
  }
  function jauge(s, week) {    // carrés de la jauge : journées posées, puis absences/fériés (hachurés), puis vides ; hors quota en orange
    const q = quota(s, week), r = reserve(s, week), pl = placed(s, week), v = virtuels(s, week);
    const nbPose = pl.filter(x => !x.x).length - r.over, extras = pl.filter(x => x.x).length + r.over;
    const restant = consommer(q, v); let sq = ""; let posesAffiches = 0;
    q.forEach((t) => {
      const idx = restant.indexOf(t); const virtuel = idx < 0; if (!virtuel) restant.splice(idx, 1);
      let cls = ""; if (virtuel) cls = " v"; else if (posesAffiches < nbPose) { cls = " on"; posesAffiches++; }
      sq += `<span class="sq${t === "C" ? " c" : ""}${cls}"></span>`; });
    for (let i = 0; i < extras; i++) sq += `<span class="sq x"></span>`;
    return { sq, nbPose, extras, v, q, r, texte: `${nbPose + v.length + extras}/${q.length}` };
  }
  function absences(sid, du, au) {   // comptage par type sur une plage
    const out = {}; let total = 0;
    for (const iso of Object.keys(CONGES[sid] ?? {}))
      if (iso >= du && iso <= au) { const c = congeDe(sid, iso); if (c?.bloque) { out[c.type] = (out[c.type] ?? 0) + 1; total++; } }
    return { parType: out, total };
  }
  function reasonRefus(sid, iso, fromDate) {   // code de refus d'un dépôt, ou null
    if (!dateValide(iso) || iso < DATA.meta.debut || iso > DATA.meta.fin) return "hors_plage";
    if (bloque(sid, iso)) return "jour_bloque";
    if (fromDate !== iso && allBricksOfDay(iso).some(b => b.s === sid)) return "doublon_jour";
    return null;
  }
  const weekOf = iso => WEEKS.findIndex(w => w.days.includes(iso));
  function manquantes(w) { let n = 0; for (const iso of shownDays(w)) for (const {p} of presents(iso)) n += Math.max(0, need(iso, p)); return n; }
  const notesDe = iso => { const n = state.notes[iso]; return Array.isArray(n) ? n : n ? [n] : []; };
  const nbCoursMois = sid => (COURS[sid] ?? []).filter(d => d >= DATA.meta.debut && d <= DATA.meta.fin).length;

  // ------------------------------------------------------------ mutations (avec historique, sans affichage)
  function snapshot() { HISTORY.push(JSON.stringify({a: state.affectations, f: state.feries, o: state.feries_off, n: state.notes})); if (HISTORY.length > 60) HISTORY.shift(); }
  function peutAnnuler() { return HISTORY.length > 0; }
  function undo() { if (!HISTORY.length) return false; const h = JSON.parse(HISTORY.pop()); state.affectations = h.a; state.feries = h.f; state.feries_off = h.o; state.notes = h.n; return true; }
  function addBrick(iso, slot, b) { ((state.affectations[iso] ??= {})[slot] ??= []).push({s:b.s, t:b.t, x:!!b.x, a:!!b.a}); }
  function removeBrick(iso, slot, index) {
    const arr = state.affectations[iso]?.[slot]; if (!arr) return null;
    const [b] = arr.splice(index,1);
    if (!arr.length) delete state.affectations[iso][slot];
    if (!Object.keys(state.affectations[iso]).length) delete state.affectations[iso];
    return b;
  }
  function retirerBriquesDe(iso, sid) {   // retire toutes les briques d'une personne (ou de tout le monde si sid null) un jour donné
    const d = state.affectations[iso]; if (!d) return 0; let n = 0;
    for (const slot of Object.keys(d)) { const avant = d[slot].length; d[slot] = d[slot].filter(b => sid && b.s !== sid); n += avant - d[slot].length; if (!d[slot].length) delete d[slot]; }
    if (!Object.keys(d).length) delete state.affectations[iso];
    return n;
  }
  function place(iso, slot, b, from) {   // action manuelle : la brique devient confirmée. Rend {ok, code, cible, bascule}
    const wk = weekOf(iso);
    if (wk < 0) return {ok:false, code:"hors_plage"};
    if (from?.date && weekOf(from.date) !== wk) return {ok:false, code:"autre_semaine"};
    const refus = reasonRefus(b.s, iso, from?.date);
    if (refus) return {ok:false, code:refus};
    if (!from?.date && !b.x && !reserve(SAL[b.s], WEEKS[wk]).rest.includes(b.t)) return {ok:false, code:"quota_depasse"};
    let cible = slot, bascule = null;
    if (PRAT[slot]) {
      const p = PRAT[slot];
      if (nonCouvert(iso)) return {ok:false, code:"sans_donnees"};
      if (!praticienPresent(iso, p)) return {ok:false, code:"praticien_absent"};
      // exclusivité (règle stricte du skill, absente de l'ancien place())
      if (SAL[b.s].exclusif && !(SAL[b.s].binomes ?? []).includes(slot)) return {ok:false, code:"exclusive_ailleurs"};
      if (p.exclusif && !(p.binomes ?? []).includes(b.s)) return {ok:false, code:"exclusif_intrus"};
      const deja = bricksAt(iso, slot).filter((x, i) => !(from?.date === iso && from.slot === slot && from.index === i)).length;
      if (deja >= p.attendues) { cible = "sureffectif"; bascule = p; }
    } else if (!SHOWN.includes(weekday(iso))) return {ok:false, code:"jour_non_affiche"};
    snapshot();
    if (from?.date) removeBrick(from.date, from.slot, from.index);
    addBrick(iso, cible, {...b, a:false});
    return {ok:true, code:null, cible, bascule};
  }
  function unplace(iso, slot, index) { snapshot(); return removeBrick(iso, slot, index); }
  function retirerCourte(sid, wk) {   // retire la journée courte posée dans la semaine (consommée par un cours)
    for (const d of wk.days) { const arr = state.affectations[d]; if (!arr) continue; for (const slot of Object.keys(arr)) { const i = arr[slot].findIndex(b => b.s === sid && b.t === "C"); if (i >= 0) { removeBrick(d, slot, i); return true; } } }
    return false;
  }
  function fermerJour(iso) {   // férié ou pont posé dans la page ; rend le nombre de briques retirées
    snapshot();
    const n = retirerBriquesDe(iso, null);
    if (iso in DATA.feries) state.feries_off = state.feries_off.filter(x => x !== iso); else state.feries[iso] = "Fermé (ajouté)";
    return n;
  }
  function rouvrirJour(iso) {   // le cabinet travaille finalement ce jour-là
    snapshot();
    if (iso in state.feries) delete state.feries[iso]; else if (!state.feries_off.includes(iso)) state.feries_off.push(iso);
  }
  function poserNotes(iso, liste) {   // remplace les commentaires du jour ; liste vide = suppression
    snapshot();
    const l = listeDeNotes(liste);
    if (l.length) state.notes[iso] = l; else delete state.notes[iso];
    return l;
  }

  // ------------------------------------------------------------ moteur de proposition
  // Strict : heures hebdo (briques), une brique par jour, congés/fériés/cours, exclusifs.
  // Relatif : binômes, continuité, équilibre, créneau administratif, reliquat en renfort.
  function proposer(week) {
    const days = shownDays(week);
    let poses = 0;
    const auto = (iso, slot, sid, t) => { addBrick(iso, slot, {s:sid, t, x:false, a:true}); poses++; };
    const chargeJour = iso => presents(iso).length;
    const travailleAvec = (sid, pid, w) => { let n = 0; for (const iso of w.days) for (const b of (state.affectations[iso]?.[pid] ?? [])) if (b.s === sid) n++; return n; };
    const joursPraticien = sid => { let n = 0; for (const iso in state.affectations) for (const [slot, arr] of Object.entries(state.affectations[iso])) if (PRAT[slot]) n += arr.filter(b => b.s === sid).length; return n; };
    const postesOuverts = (filtre) => { const out = []; for (const iso of days) for (const {p} of presents(iso)) if (need(iso, p) > 0 && (!filtre || filtre(p))) out.push({iso, p}); return out; };
    // choisit le type de brique à poser : J d'abord ; C sur le jour où le praticien finit le plus tôt ; les personnes à créneau administratif gardent leur C
    const poserChez = (s, cibles) => {  // cibles : [{iso, p}] triées par priorité ; pose autant que la réserve le permet
      let rest = reserve(s, week).rest.slice();
      if (s.admin) rest = rest.filter(t => t !== s.admin);
      const prises = cibles.slice(0, rest.length);
      if (!prises.length) return;
      const parFin = prises.slice().sort((a, b) => (finOf(a.iso, a.p) ?? "99").localeCompare(finOf(b.iso, b.p) ?? "99") || chargePoste(a.iso, a.p) - chargePoste(b.iso, b.p));
      const jourCourte = rest.includes("C") ? parFin[0].iso : null;
      for (const c of prises) { const t = (c.iso === jourCourte) ? "C" : (rest.includes("J") ? "J" : rest[0]); rest.splice(rest.indexOf(t), 1); auto(c.iso, c.p.id, s.id, t); }
    };
    const ciblesBinomes = (s) => {  // jours où un binôme est présent et manque de monde, une cible par jour
      const cands = [];
      for (const iso of days) for (const pid of s.binomes) { const p = PRAT[pid]; if (p && presents(iso).some(x => x.p.id === pid) && need(iso, p) > 0 && free(s.id, iso)) cands.push({iso, p, need: need(iso, p), charge: chargePoste(iso, p)}); }
      cands.sort((a, b) => b.need - a.need || b.charge - a.charge);
      const vu = new Set(); return cands.filter(c => !vu.has(c.iso) && vu.add(c.iso));
    };
    // 1. exclusives chez leur binôme
    for (const s of DATA.salaries.filter(x => x.exclusif && x.binomes.length)) poserChez(s, ciblesBinomes(s));
    // 2. binômes relatifs
    for (const s of DATA.salaries.filter(x => !x.exclusif && x.binomes.length)) poserChez(s, ciblesBinomes(s));
    // 3. couverture des postes restants (hors praticiens exclusifs) — postes les plus chargés d'abord
    let garde = 200;
    while (garde-- > 0) {
      const postes = postesOuverts(p => !p.exclusif).map(x => ({...x, charge: chargePoste(x.iso, x.p)})).sort((a, b) => b.charge - a.charge);
      let fait = false;
      for (const {iso, p} of postes) {
        const cands = DATA.salaries.filter(s => s.role === "assistante" && !s.exclusif && free(s.id, iso))
          .map(s => { let rest = reserve(s, week).rest; const restJ = rest.filter(t => t !== s.admin); return {s, rest, restJ}; })
          .filter(c => c.rest.length);
        if (!cands.length) continue;
        // priorité : briques non réservées à l'administratif > continuité avec ce praticien dans la semaine > équité (moins de journées chez un praticien dans le mois) > briques restantes
        cands.sort((a, b) => (b.restJ.length > 0) - (a.restJ.length > 0) || travailleAvec(b.s.id, p.id, week) - travailleAvec(a.s.id, p.id, week) || joursPraticien(a.s.id) - joursPraticien(b.s.id) || b.rest.length - a.rest.length);
        const c = cands[0];
        const t = c.restJ.includes("J") ? "J" : (c.restJ[0] ?? c.rest[0]);   // dernier recours : la brique administrative sert la couverture
        auto(iso, p.id, c.s.id, t); fait = true; break;
      }
      if (!fait) break;
    }
    // 3b. réparation : si la brique administrative a servi la couverture (jour d1), chercher un jour d2 où la personne
    //     est chez un praticien avec une journée complète et où une autre assistante libre peut la remplacer.
    for (const s of DATA.salaries.filter(x => x.admin)) {
      if (reserve(s, week).rest.includes(s.admin)) continue;
      const d1 = days.find(iso => allBricksOfDay(iso).some(b => b.s === s.id && b.t === s.admin && PRAT[b.slot]));
      if (!d1) continue;
      let repare = false;
      for (const d2 of days.filter(iso => iso !== d1)) {
        if (repare) break;
        const bj = allBricksOfDay(d2).find(b => b.s === s.id && b.t !== s.admin && PRAT[b.slot]);
        if (!bj) continue;
        const p2 = PRAT[bj.slot];
        if (p2.exclusif) continue;
        const rempl = DATA.salaries.find(c => c.role === "assistante" && !c.exclusif && !c.admin && free(c.id, d2) && reserve(c, week).rest.includes("J"));
        if (!rempl) continue;
        const idx = state.affectations[d2][p2.id].findIndex(b => b.s === s.id);
        removeBrick(d2, p2.id, idx);
        auto(d2, p2.id, rempl.id, "J");
        const b1 = allBricksOfDay(d1).find(b => b.s === s.id);
        state.affectations[d1][b1.slot].find(b => b.s === s.id).t = "J";
        repare = true;
      }
    }
    // 4. créneau administratif s'il reste la brique prévue — jour libre le moins chargé, mardi→vendredi de préférence
    for (const s of DATA.salaries.filter(x => x.admin)) {
      const rest = reserve(s, week).rest; if (!rest.includes(s.admin)) continue;
      const libres = days.filter(iso => free(s.id, iso)).sort((a, b) => (weekday(a) === 5 || weekday(a) === 0) - (weekday(b) === 5 || weekday(b) === 0) || chargeJour(a) - chargeJour(b));
      if (libres.length) auto(libres[0], "administratif", s.id, s.admin);
    }
    // 5. reliquat → sureffectif (renfort) sur les jours les plus chargés, mardi→vendredi ; samedi ou lundi seulement à défaut
    for (const s of DATA.salaries.filter(x => x.role === "assistante")) {
      for (const t of reserve(s, week).rest.slice()) {
        const ok = days.filter(iso => free(s.id, iso));
        const semaine = ok.filter(iso => weekday(iso) >= 1 && weekday(iso) <= 4), bord = ok.filter(iso => weekday(iso) === 5 || weekday(iso) === 0);
        const choix = (semaine.length ? semaine : bord).sort((a, b) => chargeJour(b) - chargeJour(a) || bricksAt(a, "sureffectif").length - bricksAt(b, "sureffectif").length);
        if (choix.length) auto(choix[0], "sureffectif", s.id, t);
      }
    }
    return poses;
  }
  function initialState() {  // secrétaires sur leurs jours fixes, puis proposition sur chaque semaine. Jamais appelée par le moteur lui-même.
    state.affectations = {};
    for (const s of DATA.salaries) if (s.role === "secretaire") for (const w of WEEKS) for (const iso of shownDays(w))
      if (s.fixes.includes(weekday(iso)) && !bloque(s.id, iso)) addBrick(iso, "secretariat", {s:s.id, t:"J", x:false, a:true});
    for (const w of WEEKS) proposer(w);
  }

  // ------------------------------------------------------------ import, export, charge
  function importer(src) {   // fusion d'un export JSON ou du state d'une copie ; rend {jours, ignorees} ou null si illisible
    if (!estObjet(src) || !estObjet(src.affectations)) return null;
    snapshot();
    const dansPlage = iso => dateValide(iso) && iso >= DATA.meta.debut && iso <= DATA.meta.fin;
    if (estObjet(src.feries)) for (const [iso, nom] of Object.entries(src.feries)) if (dansPlage(iso)) state.feries[iso] = String(nom);
    if (Array.isArray(src.feries_off)) for (const iso of src.feries_off) if (dansPlage(iso) && !state.feries_off.includes(iso)) state.feries_off.push(iso);
    if (estObjet(src.notes)) for (const [iso, txt] of Object.entries(src.notes)) { if (!dansPlage(iso)) continue; const l = listeDeNotes(txt); if (l.length) state.notes[iso] = l; }
    let jours = 0, ignorees = 0;
    for (const [iso, slots] of Object.entries(src.affectations)) {
      if (!dansPlage(iso) || !estObjet(slots)) continue;
      const clean = {};
      for (const [slot, arr] of Object.entries(slots)) {
        if (!Array.isArray(arr)) continue;
        const ok = arr.filter(b => estObjet(b) && SAL[b.s] && BRIQUES.includes(b.t)); ignorees += arr.length - ok.length;
        if (ok.length) clean[slot] = ok.map(b => ({s:b.s, t:b.t, x:!!b.x, a:!!b.a}));
      }
      if (Object.keys(clean).length) state.affectations[iso] = clean; else delete state.affectations[iso];
      jours++;
    }
    return {jours, ignorees};
  }
  function exporter(numero) {   // l'objet du fichier « Exporter JSON » : sans congé, sans cours, sans type d'absence
    const propre = nettoyer(state);
    return {mois: DATA.meta.mois, numero: numero ?? 0, affectations: propre.affectations, feries: propre.feries, feries_off: propre.feries_off, notes: propre.notes, exporte: new Date().toISOString()};
  }
  function charge(version_de_base) {   // la seule sérialisation envoyée à l'API
    return {version_de_base: version_de_base ?? 0, state: nettoyer(state)};
  }
  function empreinte() { return canonique(nettoyer(state)); }

  // ------------------------------------------------------------ vérification stricte (mêmes codes que verification.py)
  function verifier() {
    const v = [];
    const push = (code, date = null, slot = null, s = null) => v.push({code, date, slot, s});
    const dansPlage = iso => dateValide(iso) && iso >= DATA.meta.debut && iso <= DATA.meta.fin;
    const parJour = {};
    for (const [iso, slots] of Object.entries(state.affectations)) {
      if (!dansPlage(iso)) { push("hors_plage", iso); continue; }
      if (!estObjet(slots)) { push("brique_invalide", iso); continue; }
      for (const [slot, arr] of Object.entries(slots)) {
        if (!PRAT[slot] && !MISC_SLOTS.includes(slot)) { push("slot_inconnu", iso, slot); continue; }
        if (!Array.isArray(arr)) { push("brique_invalide", iso, slot); continue; }
        for (const b of arr) {
          const s = estObjet(b) && typeof b.s === "string" ? b.s : null;
          if (!estObjet(b) || !BRIQUES.includes(b.t) || s === null) { push("brique_invalide", iso, slot, s); continue; }
          if (!SAL[s]) { push("salariee_inconnue", iso, slot, s); continue; }
          (parJour[iso] ??= {})[s] = (parJour[iso][s] ?? 0) + 1;
          if (bloque(s, iso)) push("jour_bloque", iso, slot, s);
          if (PRAT[slot]) {
            const p = PRAT[slot];
            if (nonCouvert(iso)) push("sans_donnees", iso, slot, s);
            else if (!praticienPresent(iso, p)) push("praticien_absent", iso, slot, s);
            // une exclusive ne va chez aucun autre praticien ; les cases secrétariat / sureffectif / administratif lui restent ouvertes
            if (SAL[s].exclusif && !(SAL[s].binomes ?? []).includes(slot)) push("exclusive_ailleurs", iso, slot, s);
            if (p.exclusif && !(p.binomes ?? []).includes(s)) push("exclusif_intrus", iso, slot, s);
          } else if (!SHOWN.includes(weekday(iso))) push("jour_non_affiche", iso, slot, s);
        }
        if (PRAT[slot] && arr.length > (PRAT[slot].attendues || 1)) push("capacite", iso, slot);
      }
    }
    for (const [iso, comptes] of Object.entries(parJour)) for (const [s, n] of Object.entries(comptes)) if (n > 1) push("doublon_jour", iso, null, s);
    for (const iso of [...Object.keys(state.feries), ...state.feries_off, ...Object.keys(state.notes)]) if (!dansPlage(iso)) push("hors_plage", iso);
    for (const s of DATA.salaries) for (const w of WEEKS) if (reserve(s, w).over > 0) push("quota_depasse", w.start, null, s.id);
    return v;
  }

  return {
    DATA, state, WEEKS, SHOWN, SAL, PRAT, HB, ABS, MISC, MISC_SLOTS, MISC_LABEL,
    shownDays, isFerie, ferieName, congeDe, coursDe, attentesDe, nonCouvert, bloque, virtuels, consommer,
    presents, praticienPresent, bricksAt, allBricksOfDay, need, free, finOf, chargePoste, quota, placed, reserve,
    heures, jauge, absences, reasonRefus, weekOf, manquantes, notesDe, nbCoursMois,
    snapshot, peutAnnuler, undo, addBrick, removeBrick, retirerBriquesDe, place, unplace, retirerCourte,
    fermerJour, rouvrirJour, poserNotes, proposer, initialState, importer, exporter, charge, empreinte, verifier,
  };
}

return { creer, nettoyer, canonique, CODES, BRIQUES, CLES_STATE, MISC, MISC_SLOTS, MISC_LABEL, ABS, DOW_ABR, MOIS,
         toDate, toIso, addDays, weekday, isoWeek, fmtJour, heure, fmtH, dateValide };
});
