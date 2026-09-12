/* Page du planning assistantes — brique 4a.

   Port de la partie DOM du gabarit du skill v1
   (reference/skill-v1/assets/gabarit.html, l.797-1107) : rendu, glisser-déposer,
   toasts, boutons, appels d'API. Toute la logique métier est dans moteur.js ;
   ici on enchaîne toujours `M.x(); commit();`.

   La page propose si et seulement si `META.numero === 0` : aucun drapeau de
   l'état ne porte cette décision. En mode « autonome » (copie HTML), les
   boutons d'API sont masqués et rien ne part vers le serveur.

   Brique 4b : « Publier » (`META.urls.publier`, `META.publiee` = numéro de la
   version publiée courante) et les cases « hors présence » (R4a-1-E1) qui
   rendent visibles et manipulables les briques d'un praticien absent. */
(() => {
"use strict";
const DATA = JSON.parse(document.getElementById("planning-data").textContent);
const STATE = JSON.parse(document.getElementById("planning-state").textContent);
const META = JSON.parse(document.getElementById("planning-meta").textContent);
const M = PlanningMoteur.creer(DATA, STATE);
const state = M.state;
const {WEEKS, SHOWN, SAL, PRAT, HB, ABS, MISC, MISC_LABEL, shownDays, isFerie, ferieName, congeDe, coursDe, attentesDe, nonCouvert, bloque,
       presents, bricksAt, allBricksOfDay, orphelins, need, reserve, heures, jauge, absences, reasonRefus, weekOf, manquantes, notesDe, nbCoursMois, quota, placed} = M;
const {DOW_ABR, MOIS, toDate, weekday, fmtJour, fmtH, heure} = PlanningMoteur;

let ARMED = null;      // brique sélectionnée au clic : {s,t,x}
let CURRENT_WEEK = 0;  // semaine dont la réserve est affichée
let DRAG = null;       // brique en cours de glisser
let FILTER = null;     // brique 8 (D8.6) : null | {s: [sid, …]} | {p: [pid, …]} — jamais une liste vide, un genre à la fois
let CPOP = null;       // {iso, edit: index|null} : fenêtre de commentaires ouverte
let DERNIERE = M.empreinte();   // empreinte de l'état tel que le serveur le connaît
let VIOLATIONS = [];   // dernières violations affichées (page ou serveur)
let AUJOURDHUI = null; // brique 8 (D8.9-bis) : date du jour « AAAA-MM-JJ », locale, posée dans boot
let PLIEES = new Set();   // brique 8 (D8.9) : indices des semaines repliées sur leur bande
let DERNIER_Y = null, DERNIER_SCROLL = null, AUTOSCROLL = null;   // brique 8 (D8.12) : glisser assisté près des bords

// ------------------------------------------------------------ lisibilité : brique pleine, texte par luminance (brique 8, lot 5, D8.14, décision A)
const TXT = {};   // sid → couleur du texte sur l'encre de la personne ; la section palette de regles.json est intouchée
function texteSur(hex) { const n = parseInt(hex.slice(1), 16); const r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255; return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.6 ? "#111" : "#fff"; }

// ------------------------------------------------------------ filtre à plusieurs noms (brique 8, D8.6)
const horsS = id => !!FILTER?.s && !FILTER.s.includes(id);        // salariée hors de la sélection
const horsP = id => !!FILTER?.p && !FILTER.p.includes(id);        // praticien hors de la sélection
const aucuneS = bricks => !!FILTER?.s && !bricks.some(b => FILTER.s.includes(b.s));   // aucune brique sélectionnée dans la case
const nomsFiltre = () => FILTER?.s ? FILTER.s.map(id => SAL[id].label).join(", ") : FILTER?.p ? FILTER.p.map(id => PRAT[id].label).join(", ") : null;
function basculer(genre, id) {   // le clic ajoute, un second clic sur le même nom retire ; l'autre genre s'efface ; liste vide → null
  const liste = FILTER?.[genre];
  if (!liste) return {[genre]: [id]};
  const reste = liste.includes(id) ? liste.filter(x => x !== id) : [...liste, id];
  return reste.length ? {[genre]: reste} : null;
}

// ------------------------------------------------------------ lignes de rôle : pictogrammes et repli (brique 8, D8.7, D8.8)
const PICTO = {   // SVG inline, identiques sur tout appareil ; le CSS les dessine en 14 × 14
  secretariat: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3.5 1.5h2.2l1.2 3.1-1.6 1.2a9 9 0 0 0 4.9 4.9l1.2-1.6 3.1 1.2v2.2A1.5 1.5 0 0 1 13 14 12 12 0 0 1 2 3a1.5 1.5 0 0 1 1.5-1.5z"/></svg>',
  administratif: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M3 1.5h10a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1zm1.5 3v1.6h7V4.5zm0 3v1.6h7V7.5zm0 3v1.6h5v-1.6z"/></svg>',
  sureffectif: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1zm0 1.6a5.4 5.4 0 1 0 0 10.8A5.4 5.4 0 0 0 8 2.6zM7.2 5h1.6v2.2H11v1.6H8.8V11H7.2V8.8H5V7.2h2.2z"/></svg>',
  absent: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1zm0 1.6a5.4 5.4 0 0 0-4.3 8.6l7.5-7.5A5.4 5.4 0 0 0 8 2.6zm4.3 2.2-7.5 7.5A5.4 5.4 0 0 0 12.3 4.8z"/></svg>',
};
const LIBELLE = {secretariat: "Secrétariat", administratif: "Administratif", sureffectif: "Sureffectif", absent: "Absent"};   // les mots de MISC (moteur.js)
let REPLIS = {};   // {secretariat | administratif | sureffectif | absent: true} : lignes repliées, toutes les semaines à la fois — mémorisé par le navigateur, jamais dans STATE
const CLE_REPLIS = "planning-assistantes.replis";
function replier(type) { REPLIS[type] = !REPLIS[type]; try { localStorage.setItem(CLE_REPLIS, JSON.stringify(REPLIS)); } catch (e) {} render(); }
function boutonLigne(type) {   // le pictogramme d'une ligne de rôle : libellé en infobulle et en aria-label, un clic replie ou déplie ce type de ligne
  const ml = el("button", "ml", PICTO[type]); ml.type = "button"; ml.title = LIBELLE[type];
  ml.setAttribute("aria-label", LIBELLE[type] + (REPLIS[type] ? " — déplier" : " — replier"));
  ml.addEventListener("click", ev => { ev.stopPropagation(); replier(type); });
  return ml;
}

// ------------------------------------------------------------ messages
const MSG = {
  hors_plage: "date hors de la plage du mois",
  salariee_inconnue: "salariée inconnue de la fiche",
  slot_inconnu: "case inconnue",
  brique_invalide: "brique illisible",
  doublon_jour: "deux briques le même jour",
  jour_bloque: "jour fermé, absence ou cours",
  jour_non_affiche: "jour sans présence ni jour fixe",
  sans_donnees: "aucune donnée Doctolib ce jour-là",
  praticien_absent: "praticien absent ce jour-là",
  capacite: "trop d'assistantes pour ce praticien",
  exclusive_ailleurs: "exclusive placée hors de son binôme",
  exclusif_intrus: "praticien exclusif : réservé à ses binômes",
  quota_depasse: "briques de la semaine dépassées",
};
function messageViolation(v) {
  const qui = v.s && SAL[v.s] ? SAL[v.s].label : null;
  const ou = v.slot ? (PRAT[v.slot]?.label ?? MISC_LABEL[v.slot] ?? v.slot) : null;
  const quand = v.date ? (v.code === "quota_depasse" ? `semaine du ${fmtJour(v.date)}` : fmtJour(v.date)) : null;
  return [quand, qui, ou, MSG[v.code] ?? v.code].filter(Boolean).join(" · ");
}
function messageRefus(code, b, iso, slot) {   // toast d'un dépôt refusé par place()
  const s = SAL[b.s], p = PRAT[slot];
  const noms = ids => ids.map(x => SAL[x]?.label ?? PRAT[x]?.label).filter(Boolean).join(" et ");
  switch (code) {
    case "autre_semaine": return "Une brique appartient à sa semaine : reprenez-la dans la réserve de l'autre semaine.";
    case "jour_bloque": return `${s.label} ne peut pas être placée le ${fmtJour(iso)} : jour fermé, absence ou cours.`;
    case "doublon_jour": return `${s.label} est déjà placée le ${fmtJour(iso)}`;
    case "quota_depasse": return `Plus de brique « ${b.t === "C" ? "courte" : "journée"} » pour ${s.label} cette semaine. Utilisez + pour une journée hors quota.`;
    case "exclusive_ailleurs": return `${s.label} est exclusive : elle ne va que chez ${noms(s.binomes ?? [])}.`;
    case "exclusif_intrus": return `${p?.label ?? slot} ne reçoit que ${noms(p?.binomes ?? [])}.`;
    case "praticien_absent": return `${p?.label ?? slot} n'est pas présent le ${fmtJour(iso)}.`;
    case "sans_donnees": return `Aucune donnée Doctolib le ${fmtJour(iso)}.`;
    case "jour_non_affiche": return `Le ${fmtJour(iso)} n'est pas un jour du planning.`;
    default: return "Dépôt refusé.";
  }
}

// ------------------------------------------------------------ outils DOM
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const csrf = () => { const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ""; };
// info-bulle des postes : survol = affichage, clic = épinglée (re-clic ou Échap pour fermer)
let TIP_PINNED = null;
function showTip(target, html, pinned) {
  const tip = document.getElementById("tip"); tip.innerHTML = html; tip.className = "show" + (pinned ? " pinned" : "");
  const r = target.getBoundingClientRect(); tip.style.left = Math.min(r.left, window.innerWidth - 280) + "px"; tip.style.top = (r.bottom + 6) + "px";
}
function hideTip(force) { if (TIP_PINNED && !force) return; TIP_PINNED = null; document.getElementById("tip").className = ""; }
function tipHandlers(target, html) {
  target.addEventListener("mouseenter", () => { if (!TIP_PINNED && !DRAG) showTip(target, html, false); });
  target.addEventListener("mouseleave", () => hideTip(false));
  target.addEventListener("click", ev => { if (ev.target.closest(".brick") || ARMED) return; if (TIP_PINNED === target) { hideTip(true); } else { TIP_PINNED = target; showTip(target, html, true); } });
}
let toastTimer;
function toast(msg, err) { const t = document.getElementById("toast"); t.textContent = msg; t.className = "show" + (err ? " err" : ""); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.className = "", err ? 3600 : 2200); }
function bandeau(html, err) { const b = document.getElementById("banner"); b.className = "banner" + (err ? " err" : ""); b.innerHTML = html; }

// ------------------------------------------------------------ gestes (moteur puis commit)
function commit() { render(); }
function deposer(iso, slot, b, from) {   // rend le résultat de place() après l'avoir affiché
  const r = M.place(iso, slot, b, from);
  if (!r.ok) { toast(messageRefus(r.code, b, iso, slot), true); return r; }
  commit();
  document.querySelector(`.day[data-date="${iso}"] .slot[data-slot="${r.cible}"] .brick:last-child`)?.classList.add("posee");   // brique 8 (D8.12) : bref flash de la brique posée
  if (r.bascule) toast(`${r.bascule.label} a déjà ${r.bascule.attendues > 1 ? "ses " + r.bascule.attendues + " assistantes" : "son assistante"} le ${fmtJour(iso)} : ${SAL[b.s].label} passe en sureffectif.`);
  return r;
}
function retirer(from) { M.unplace(from.date, from.slot, from.index); commit(); }
function annuler() { if (!M.undo()) { toast("Rien à annuler"); return; } commit(); toast("Annulé"); }
function toggleFerie(iso) {
  const nb = allBricksOfDay(iso).length;
  if (isFerie(iso)) {
    if (!confirm(`${fmtJour(iso)} : rouvrir ce jour (le cabinet travaille) ?`)) return;
    M.rouvrirJour(iso); commit(); toast(`${fmtJour(iso)} rouvert — les briques reviennent dans les réserves.`);
    return;
  }
  if (!confirm(`Fermer le cabinet le ${fmtJour(iso)} (férié ou pont) ?` + (nb ? ` ${nb} brique(s) posée(s) ce jour-là seront retirées.` : "") + (weekday(iso) <= 4 ? " Le jour comptera comme une journée placée pour chaque salariée." : " Samedi ou dimanche : aucune journée comptée."))) return;
  M.fermerJour(iso); commit(); toast(`${fmtJour(iso)} fermé.`);
}
function saveNotes(iso, liste, msg) { M.poserNotes(iso, liste); commit(); toast(msg); }
function addNote(iso, t) { if (!t.trim()) return; saveNotes(iso, [...notesDe(iso), t], `Commentaire ajouté au ${fmtJour(iso)}`); }
function editNote(iso, i, t) { const l = notesDe(iso).slice(); l[i] = t; saveNotes(iso, l, `Commentaire modifié`); }
function delNote(iso, i) { const l = notesDe(iso).slice(); l.splice(i, 1); saveNotes(iso, l, `Commentaire supprimé`); }
function closeCpop() { CPOP = null; document.getElementById("cpop").className = "cpop"; }
function openCpop(iso, edit) {   // fenêtre ancrée sous la bulle (ou le bouton) du jour
  CPOP = {iso, edit: edit ?? null}; hideTip(true);
  const pop = document.getElementById("cpop"); pop.innerHTML = "";
  const liste = notesDe(iso);
  const head = el("div", "ch", `Commentaires · ${esc(fmtJour(iso))}`); const close = el("button", "close", "×"); close.title = "Fermer"; close.addEventListener("click", closeCpop); head.appendChild(close); pop.appendChild(head);
  if (liste.length) {
    const ul = el("ul");
    liste.forEach((t, i) => { const li = el("li", CPOP.edit === i ? "editing" : null); li.appendChild(el("span", null, esc(t)));
      const e = el("button", null, "✎"); e.title = "Modifier"; e.addEventListener("click", () => { CPOP.edit = i; openCpop(iso, i); });
      const x = el("button", null, "×"); x.title = "Supprimer"; x.addEventListener("click", () => delNote(iso, i));
      li.appendChild(e); li.appendChild(x); ul.appendChild(li); });
    pop.appendChild(ul);
  }
  const ta = el("textarea"); ta.placeholder = liste.length ? "Nouveau commentaire…" : "Commentaire sur la journée…"; ta.rows = 3;
  if (CPOP.edit != null) ta.value = liste[CPOP.edit] ?? "";
  const valide = () => { const t = ta.value; if (CPOP?.edit != null) editNote(iso, CPOP.edit, t); else addNote(iso, t); };
  ta.addEventListener("keydown", ev => { ev.stopPropagation(); if (ev.key === "Escape") { if (CPOP?.edit != null) { openCpop(iso, null); } else closeCpop(); } if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) valide(); });
  pop.appendChild(ta);
  const ca = el("div", "ca"); const ok = el("button", "btn primary", CPOP.edit != null ? "Enregistrer" : "Ajouter"); ok.addEventListener("click", valide); ca.appendChild(ok);
  if (CPOP.edit != null) { const ann = el("button", "btn", "Annuler"); ann.addEventListener("click", () => openCpop(iso, null)); ca.appendChild(ann); }
  ca.appendChild(el("span", "help", "Ctrl+Entrée")); pop.appendChild(ca);
  pop.className = "cpop show";
  const anchor = document.querySelector(`.day[data-date="${iso}"] .cbub`) ?? document.querySelector(`.day[data-date="${iso}"] .cbtn`) ?? document.querySelector(`.day[data-date="${iso}"]`);
  const r = anchor.getBoundingClientRect(); pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 296)) + "px"; pop.style.top = Math.min(r.bottom + 6, window.innerHeight - 320) + "px";
  setTimeout(() => ta.focus(), 0);
}

// ------------------------------------------------------------ rendu
function brickEl(b, ctx) {  // ctx : {from:{date,slot,index}, warn} ou {palette:true}
  const s = SAL[b.s];
  const e = el("div", "brick" + (b.t === "C" ? " c" : "") + (b.x ? " x" : "") + (b.a && !ctx.palette ? " auto" : "") + (!ctx.palette && horsS(b.s) ? " dim" : ""));
  e.style.setProperty("--bg", s.couleur[0]); e.style.setProperty("--fg", s.couleur[1]); e.style.setProperty("--txt", TXT[b.s] ?? "#fff");
  e.draggable = true; e.tabIndex = 0;
  e.innerHTML = `${esc(s.label)}${b.t === "C" ? '<span class="tag">16h30</span>' : ""}${b.x ? '<span class="tag">+</span>' : ""}`;
  e.title = `${s.nom} · ${s.role === "secretaire" ? "secrétaire" : "assistante"} ${s.heures} h` + (b.t === "C" ? " · journée courte, fin 16h30" : "") + (b.x ? " · hors quota" : "") + (b.a && !ctx.palette ? " · proposée par le moteur, déplacez-la pour la confirmer" : "");
  e.addEventListener("dragstart", ev => {
    DRAG = {b:{s:b.s, t:b.t, x:b.x}, from: ctx.from ?? null};
    ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("text/plain", b.s);
    e.classList.add("ghost"); markDroppables(b.s, ctx.from?.date); document.body.classList.add("placing");
    DERNIER_Y = null; DERNIER_SCROLL = window.scrollY; AUTOSCROLL = requestAnimationFrame(defiler);   // brique 8 (D8.12)
  });
  e.addEventListener("dragend", () => { DRAG = null; cancelAnimationFrame(AUTOSCROLL); AUTOSCROLL = null; e.classList.remove("ghost"); document.body.classList.remove("placing"); document.querySelectorAll(".slot.nodrop,.slot.over").forEach(x => x.classList.remove("nodrop","over")); document.getElementById("palette").classList.remove("over"); });
  if (ctx.palette) {
    e.addEventListener("click", () => { const same = ARMED && ARMED.s === b.s && ARMED.t === b.t && ARMED.x === b.x; ARMED = same ? null : {s:b.s, t:b.t, x:b.x}; render(); if (ARMED) toast(`${s.label} sélectionnée : cliquez une case pour la placer (Échap pour annuler).`); });
    if (ARMED && ARMED.s === b.s && ARMED.t === b.t && ARMED.x === b.x) e.classList.add("armed");
  } else {
    const rm = el("button", "rm", "×"); rm.title = "Retirer"; rm.addEventListener("click", ev => { ev.stopPropagation(); retirer(ctx.from); });
    e.appendChild(rm);
    if (ctx.warn) { e.classList.add("warn"); e.title += ` · ${ctx.warn}`; }
  }
  return e;
}
function markDroppables(sid, fromDate) {
  document.querySelectorAll(".slot").forEach(sl => { const iso = sl.closest(".day").dataset.date; if (reasonRefus(sid, iso, fromDate)) sl.classList.add("nodrop"); });
}
function defiler() {   // brique 8 (D8.12, Q3) : défilement assisté près des bords pendant un glisser ; se tait pour l'image où la page a bougé sans lui (défilement natif)
  if (!DRAG) return;
  const y = window.scrollY;
  if (DERNIER_SCROLL !== null && y !== DERNIER_SCROLL) { DERNIER_SCROLL = y; AUTOSCROLL = requestAnimationFrame(defiler); return; }
  const haut = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--topbar-h")) || 112;
  let pas = 0;
  if (DERNIER_Y !== null) { if (DERNIER_Y < haut + 48) pas = -8; else if (DERNIER_Y > innerHeight - 48) pas = 8; }
  if (pas) window.scrollBy(0, pas);
  DERNIER_SCROLL = window.scrollY;
  AUTOSCROLL = requestAnimationFrame(defiler);
}
function dropHandlers(target, iso, slot) {
  target.addEventListener("dragover", ev => { if (!DRAG) return; ev.preventDefault(); ev.dataTransfer.dropEffect = "move"; if (!target.classList.contains("nodrop")) target.classList.add("over"); });
  target.addEventListener("dragleave", () => target.classList.remove("over"));
  target.addEventListener("drop", ev => { ev.preventDefault(); target.classList.remove("over"); if (!DRAG) return; deposer(iso, slot, DRAG.b, DRAG.from); DRAG = null; });
  target.addEventListener("click", ev => {
    if (ev.target.closest(".brick") || !ARMED) return;
    const armed = ARMED;
    const r = deposer(iso, slot, armed);
    if (r.ok) {
      const rest = reserve(SAL[armed.s], WEEKS[weekOf(iso)]).rest.filter(t => t === armed.t).length;
      const cible = MISC_LABEL[r.cible] ?? `chez ${PRAT[r.cible].label}`;
      if (armed.x || !rest) ARMED = null;
      render();
      document.querySelector(`.day[data-date="${iso}"] .slot[data-slot="${r.cible}"] .brick:last-child`)?.classList.add("posee");
      toast(`${SAL[armed.s].label} placée ${cible} le ${fmtJour(iso)}` + (armed.x ? " (hors quota)" : rest ? ` — encore ${rest} à placer cette semaine` : " — semaine complète"));
    }
  });
}

function render() {
  hideTip(true);
  const cp = CPOP;
  const cal = document.getElementById("calendar"); cal.innerHTML = "";
  WEEKS.forEach((w, wi) => {
    const week = el("section", "week" + (wi === CURRENT_WEEK ? " current" : "") + (PLIEES.has(wi) ? " pliee" : "")); week.dataset.week = wi;
    week.addEventListener("mouseenter", () => { if (CURRENT_WEEK !== wi) { CURRENT_WEEK = wi; renderPalette(); document.querySelectorAll(".week").forEach((x,i) => x.classList.toggle("current", i === wi)); } });
    week.appendChild(bandEl(w, wi));
    const days = el("div", "days"); days.style.setProperty("--cols", SHOWN.length);
    for (const iso of shownDays(w)) days.appendChild(dayEl(iso));
    week.appendChild(days); cal.appendChild(week);
  });
  cal.appendChild(bilanEl());
  if (cp) openCpop(cp.iso, null);
  renderPalette();
  marquerViolations();
  majEntete();
}
function allerA(wi) {   // brique 8 (D8.10, D8.13) : sommaire et flèches — déplie la semaine et la fait défiler sous la barre d'outils
  CURRENT_WEEK = wi; PLIEES.delete(wi); render();
  document.querySelector(`.week[data-week="${wi}"]`)?.scrollIntoView({block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
}
function majEntete() {   // pastille de version, boutons d'API
  const modifie = M.empreinte() !== DERNIERE;
  const v = document.getElementById("version");
  const pub = META.publiee ? (META.publiee === META.numero ? " · publiée" : ` · publiée : v${META.publiee}`) : "";
  const publiee = !!META.numero && META.publiee === META.numero;
  // Brique 6d : les libellés du tableau de bord ; la copie garde le sien.
  if (META.autonome) v.textContent = `Copie de la version ${META.numero}${pub}`;
  else if (modifie) v.textContent = "Modifié, non enregistré";
  else if (!META.numero) v.textContent = "Aucune version enregistrée";
  else if (publiee) v.textContent = `Publiée (v${META.numero})`;
  else if (META.publiee) v.textContent = `Version ${META.numero} — publiée : v${META.publiee}`;
  else v.textContent = `Version ${META.numero} · non publiée`;
  v.classList.toggle("modifie", modifie && !META.autonome);
  v.classList.toggle("publiee", publiee && !modifie && !META.autonome);
  // Brique 8 (D8.2) : la pastille n'apparaît que hors de l'état stable « Publiée (vN) » ; toujours visible dans la copie
  v.hidden = !META.autonome && publiee && !modifie;
  document.getElementById("btnUndo").disabled = !M.peutAnnuler();
  document.getElementById("btnSave").disabled = META.autonome || !modifie;
  document.getElementById("btnCopie").disabled = META.autonome || modifie || !META.numero;
  document.getElementById("btnCopie").title = modifie ? "Enregistre d'abord : la copie reprend la dernière version enregistrée" : "Télécharger une copie HTML autonome de la dernière version enregistrée";
  const deja = !!META.numero && META.publiee === META.numero;
  const bp = document.getElementById("btnPublier");
  bp.disabled = META.autonome || modifie || !META.numero || deja;
  bp.title = modifie ? "Enregistre d'abord : la publication porte sur la dernière version enregistrée" : deja ? "Cette version est déjà publiée" : "Publier la dernière version enregistrée : chaque salariée la voit dans « Mes jours »";
}
function marquerViolations() {
  document.querySelectorAll(".slot.viol").forEach(x => x.classList.remove("viol"));
  for (const v of VIOLATIONS) { if (!v.date || !v.slot) continue; document.querySelector(`.day[data-date="${v.date}"] .slot[data-slot="${v.slot}"]`)?.classList.add("viol"); }
}
function afficherViolations(liste, titre, action = "enregistré") {   // `action` : « enregistré » ou « publié » (brique 6d)
  VIOLATIONS = liste;
  const b = document.getElementById("violations");
  if (!liste.length) { b.innerHTML = ""; marquerViolations(); return; }
  const suite = action === "publié" ? "Corrigez, enregistrez puis publiez à nouveau." : "Corrigez puis enregistrez à nouveau.";
  b.innerHTML = `<b>${esc(titre)}</b> : ${liste.length} règle${liste.length > 1 ? "s" : ""} stricte${liste.length > 1 ? "s" : ""} enfreinte${liste.length > 1 ? "s" : ""}. ${suite}<ul>${liste.slice(0, 30).map(v => `<li>${esc(messageViolation(v))}</li>`).join("")}${liste.length > 30 ? `<li>… et ${liste.length - 30} autre(s)</li>` : ""}</ul>`;
  marquerViolations();
  toast(`${liste.length} règle(s) stricte(s) enfreinte(s) : rien n'a été ${action}.`, true);
}
function bilanEl() {
  let manq = 0, supTot = 0, absTot = 0; for (const wk of WEEKS) manq += manquantes(wk);
  const sec = el("section", "bilan"); let rows = "";
  for (const s of DATA.salaries) {
    let q = 0, p = 0, x = 0, hp = 0, hd = 0, hs = 0;
    for (const wk of WEEKS) { const j = jauge(s, wk), h = heures(s, wk); q += j.q.length; p += j.nbPose + j.v.length; x += j.extras; hp += h.posees; hd += h.dues; hs += h.sup; }
    supTot += hs;
    const ab = absences(s.id, DATA.meta.debut, DATA.meta.fin); absTot += ab.total;
    const nbCours = nbCoursMois(s.id);
    const abTxt = [...Object.entries(ab.parType).map(([t, n]) => `<span class="${ABS[t]?.cls ?? ""}">${n} ${ABS[t]?.code ?? esc(t)}</span>`), ...(nbCours ? [`<span class="abs-cours">${nbCours} cours</span>`] : [])].join(" · ") || "—";
    const dim = horsS(s.id) ? " dimrow" : "";
    rows += `<tr><td class="${dim}" style="--fg:${s.couleur[1]}"><i></i>${esc(s.label)}</td><td class="${p < q ? "short" : "full"}${dim}">${p + x} / ${q}</td><td class="${dim}">${fmtH(hd)}</td><td class="${dim}">${fmtH(hp)}</td><td class="${hs ? "sup" : ""}${dim}">${hs ? "+" + fmtH(hs) : "—"}</td><td class="${dim}">${abTxt}</td></tr>`;
  }
  const premiers = shownDays(WEEKS[0]), derniers = shownDays(WEEKS[WEEKS.length - 1]);
  const bornes = premiers.length && derniers.length ? ` · semaines complètes du ${fmtJour(premiers[0])} au ${fmtJour(derniers[derniers.length - 1])}` : "";
  const head = el("div", "bhead", `<h3>Bilan du mois</h3><span class="bsub">${esc(DATA.meta.libelle)}${bornes}</span>`);
  const kp = el("div", "kpis");
  kp.appendChild(el("div", "kpi " + (manq ? "ko" : "ok"), `<b>${manq}</b><span>assistante${manq > 1 ? "s" : ""} manquante${manq > 1 ? "s" : ""}</span>`));
  kp.appendChild(el("div", "kpi " + (supTot ? "warn" : ""), `<b>${supTot ? "+" + fmtH(supTot) : "0 h"}</b><span>heures supplémentaires</span>`));
  kp.appendChild(el("div", "kpi", `<b>${absTot}</b><span>jour${absTot > 1 ? "s" : ""} d'absence</span>`));
  head.appendChild(kp); sec.appendChild(head);
  sec.appendChild(el("table", null, `<tr><th>Personne</th><th>Jours placés</th><th>Heures dues</th><th>Heures posées</th><th>Heures sup.</th><th>Absences</th></tr>${rows}`));
  return sec;
}
function bandEl(w, wi) {
  const b = el("div", "band");
  const d = shownDays(w);
  // Brique 8 (D8.9) : le titre est un bouton à chevron qui replie la semaine sur sa bande ; le reste de la bande garde son clic (semaine courante de la réserve)
  const pliee = PLIEES.has(wi);
  const wk = el("button", "wk", `<span class="chev" aria-hidden="true"></span><span class="wkt">Semaine ${w.num}<small>du ${fmtJour(d[0] ?? w.days[0])} au ${fmtJour(d[d.length-1] ?? w.days[6])}</small></span>`);
  wk.type = "button"; wk.setAttribute("aria-expanded", String(!pliee)); wk.title = pliee ? "Déplier la semaine" : "Replier la semaine sur sa bande";
  wk.addEventListener("click", ev => { ev.stopPropagation(); if (PLIEES.has(wi)) PLIEES.delete(wi); else PLIEES.add(wi); render(); });
  b.appendChild(wk);
  const meters = el("div", "meters");
  for (const s of DATA.salaries) {
    const j = jauge(s, w), h = heures(s, w);
    const m = el("div", "meter"); m.style.setProperty("--fg", s.couleur[1]);
    m.className = "meter" + (!j.r.rest.length && !j.extras ? " done" : "") + (horsS(s.id) ? " hide" : "");
    m.innerHTML = `<b>${esc(s.label)}</b><span class="squares">${j.sq || '<span style="color:var(--ink-3)">—</span>'}</span><span class="cnt">${j.texte}</span>${h.sup ? `<span class="hs">+${fmtH(h.sup)}</span>` : ""}`;
    m.title = `${s.nom} · ${j.q.length} j de contrat cette semaine` + (j.v.length ? `, dont ${j.v.length} en absence/férié` : "") + ` · ${fmtH(h.posees)} posées pour ${fmtH(h.dues)} dues` + (h.sup ? ` (+${fmtH(h.sup)} sup)` : "");
    meters.appendChild(m);
  }
  b.appendChild(meters);
  for (const s of DATA.salaries.filter(x => x.admin)) {
    const pose = placed(s, w).some(x => x.slot === "administratif"), rest = reserve(s, w).rest;
    if (!quota(s, w).length) continue;
    b.appendChild(el("span", "adm" + (pose ? " ok" : ""), pose ? `${esc(s.label)} : administratif ✓` : rest.length ? `${esc(s.label)} : administratif à poser` : `${esc(s.label)} : pas d'administratif (couverture)`));
  }
  const n = manquantes(w);
  b.appendChild(el("span", "postes " + (n ? "ko" : "ok"), n ? `${n} assistante${n > 1 ? "s" : ""} manquante${n > 1 ? "s" : ""}` : "tous les postes pourvus"));
  for (const s of DATA.salaries.filter(x => x.etudiante)) { const nc = w.days.filter(iso => coursDe(s.id, iso)).length; if (nc) b.appendChild(el("span", "cours", `${esc(s.label)} : ${nc > 1 ? nc + " cours" : "cours"}`)); }
  b.addEventListener("click", () => { CURRENT_WEEK = wi; render(); });
  return b;
}
function dayEl(iso) {
  const wd = weekday(iso), fer = isFerie(iso) ? ferieName(iso) : null;
  const coms = notesDe(iso);
  const day = el("div", "day" + (iso.slice(0,7) === DATA.meta.mois ? "" : " outside") + (fer ? " ferie" : "") + (coms.length ? " noted" : "") + (nonCouvert(iso) ? " noncouvert" : "") + (iso === AUJOURDHUI ? " today" : "")); day.dataset.date = iso;
  const d = toDate(iso);
  const head = el("div", "day-head", `<span class="num">${d.getDate()}</span><span>${DOW_ABR[wd]}</span>${d.getDate() === 1 || iso.slice(0,7) !== DATA.meta.mois ? `<span class="m">${MOIS[d.getMonth()]}</span>` : ""}${fer ? `<span class="fer">${esc(fer)}</span>` : ""}`);
  if (coms.length) {
    const bub = el("span", "cbub", String(coms.length)); bub.title = "";
    const html = `<b>${coms.length > 1 ? coms.length + " commentaires" : "Commentaire"}</b>` + coms.map(t => `<br>• ${esc(t)}`).join("");
    bub.addEventListener("mouseenter", () => { if (!CPOP) showTip(bub, html, false); });
    bub.addEventListener("mouseleave", () => hideTip(false));
    bub.addEventListener("click", ev => { ev.stopPropagation(); CPOP?.iso === iso ? closeCpop() : openCpop(iso, null); });
    head.querySelector(".num").after(bub);
  }
  const cb = el("button", "cbtn", "commenter"); cb.title = coms.length ? "Ajouter un autre commentaire" : "Ajouter un commentaire sur cette journée";
  cb.addEventListener("click", ev => { ev.stopPropagation(); openCpop(iso, null); });
  head.appendChild(cb);
  const fb = el("button", "fbtn", fer ? "rouvrir" : "fermer"); fb.title = fer ? "Le cabinet travaille finalement ce jour-là" : "Fermer le cabinet ce jour-là (férié, pont)";
  fb.addEventListener("click", ev => { ev.stopPropagation(); toggleFerie(iso); });
  head.appendChild(fb); day.appendChild(head);
  if (coms.length) day.appendChild(el("div", "dnote-print", coms.map(t => "• " + esc(t)).join("\n")));
  const pres = presents(iso), notes = [];
  const prats = el("div", "prats");
  if (nonCouvert(iso) && !fer) prats.appendChild(el("div", "nc", "sans données Doctolib"));
  for (const {p, l} of pres) {
    const bricks = bricksAt(iso, p.id), etat = bricks.length === 0 ? " empty" : bricks.length < p.attendues ? " partial" : "";
    const sl = el("div", "slot prat" + etat + (p.a_part ? " wide" : "") + (horsP(p.id) ? " dim" : "") + (aucuneS(bricks) ? " dim" : "")); sl.style.setProperty("--pc", p.couleur[1]); sl.dataset.slot = p.id;
    const h = l.c.length ? l.c.map(([a,b]) => `${heure(a)}–${heure(b)}`).join(" · ") : (l.v === "planning fixe" ? "jours fixes" : "");
    sl.appendChild(el("div", "sl", `<b>${esc(p.label)}</b>${p.etiquette ? `<span class="et">${esc(p.etiquette)}</span>` : ""}${p.attendues > 1 ? `<span class="att">${bricks.length}/${p.attendues}</span>` : ""}${l.v === "ouvert (atypique)" || l.jc ? '<span class="dot"></span>' : ""}`));
    const details = `<b>${esc(p.nom)}</b><br><span class="h">${esc(h || "—")}</span>` +
      (l.n != null ? `<br>${l.n} rendez-vous · agenda ${esc(l.v)}${l.jc ? " · journée courte" : ""}` : "<br>planning fixe") +
      (p.exclusif ? `<br>reçoit uniquement ${p.binomes.map(x => SAL[x]?.label).filter(Boolean).join(" et ")}` : "");
    tipHandlers(sl, details);
    const bk = el("div", "bricks");
    bricks.forEach((b, i) => bk.appendChild(brickEl(b, {from:{date:iso, slot:p.id, index:i}, warn: (b.t === "C" && l.fin && l.fin > "16:30") ? `journée courte : ${p.label} travaille jusqu'à ${heure(l.fin)}` : null})));
    sl.appendChild(bk); dropHandlers(sl, iso, p.id); prats.appendChild(sl);
  }
  // R4a-1-E1 : briques posées sur une case que la journée ne dessine pas (praticien absent ou jour fermé, slot inconnu) : visibles, retirables, déplaçables ; jamais une cible de dépôt
  const orph = orphelins(iso);
  for (const slot of orph) {
    const bricks = bricksAt(iso, slot), p = PRAT[slot];
    const sl = el("div", "slot prat orphelin" + (horsP(slot) ? " dim" : "") + (aucuneS(bricks) ? " dim" : "")); sl.dataset.slot = slot;
    if (p) sl.style.setProperty("--pc", p.couleur[1]);
    const motif = p ? (fer ? "jour fermé" : "absent ce jour-là") : "inconnu";
    sl.appendChild(el("div", "sl", `<b>${esc(p?.label ?? slot)}</b><span class="et">hors présence · ${motif}</span>`));
    sl.title = p ? `${p.nom} · ${fer ? "le cabinet est fermé ce jour-là" : "n'est pas présent ce jour-là"} : déplacez ou retirez la brique` : `case « ${slot} » inconnue : déplacez ou retirez la brique`;
    const bk = el("div", "bricks"); bricks.forEach((b, i) => bk.appendChild(brickEl(b, {from:{date:iso, slot, index:i}})));
    sl.appendChild(bk); prats.appendChild(sl);
  }
  if (pres.length || nonCouvert(iso) || orph.length) day.appendChild(prats);
  // Secrétariat toujours présent, juste sous les praticiens ; Sureffectif et Administratif seulement s'ils contiennent une brique (ou pendant un placement)
  // Brique 8 (D8.7, D8.8) : le libellé devient un pictogramme cliquable ; une ligne repliée montre « picto + N » et reste une cible de dépôt
  for (const [slot, cls] of [MISC[1], MISC[0], MISC[2]]) {
    const bricks = bricksAt(iso, slot);
    const sl = el("div", `slot misc ${cls}` + (REPLIS[slot] ? " replie" : "") + (slot !== "secretariat" && !bricks.length ? " collapsed" : "") + (FILTER?.p ? " dim" : "") + (aucuneS(bricks) ? " dim" : "")); sl.dataset.slot = slot; sl.appendChild(boutonLigne(slot));
    const bk = el("div", "bricks"); bricks.forEach((b, i) => bk.appendChild(brickEl(b, {from:{date:iso, slot, index:i}})));
    sl.appendChild(bk); if (REPLIS[slot]) sl.appendChild(el("span", "nb", String(bricks.length)));
    dropHandlers(sl, iso, slot); day.appendChild(sl);
  }
  // absences du jour (lecture seule : elles se corrigent sur /absences/), comptées comme des journées placées
  const absJour = DATA.salaries.filter(s => (congeDe(s.id, iso)?.bloque || coursDe(s.id, iso)) && !horsS(s.id));
  if (absJour.length) {
    const sl = el("div", "slot misc absr" + (REPLIS.absent ? " replie" : "") + (FILTER?.p ? " dim" : "")); sl.appendChild(boutonLigne("absent"));
    const bk = el("div", "bricks");
    for (const s of absJour.filter(x => coursDe(x.id, iso))) { const vb = el("span", "vbrick abs-cours lecture", `${esc(s.label)} · COURS`); vb.title = `${s.nom} · cours`; bk.appendChild(vb); }
    for (const s of absJour.filter(x => congeDe(x.id, iso)?.bloque)) { const c = congeDe(s.id, iso), a = ABS[c.type]; const vb = el("span", `vbrick lecture ${a?.cls ?? ""}`, `${esc(s.label)} · ${a?.code ?? esc(c.type)}`); vb.style.color = a ? "" : "var(--ink-2)"; vb.title = `${s.nom} · ${c.type} — se corrige depuis l'écran des absences`; bk.appendChild(vb); }
    sl.appendChild(bk); if (REPLIS.absent) sl.appendChild(el("span", "nb", String(absJour.length))); day.appendChild(sl);
  }
  for (const sid of attentesDe(iso)) if (SAL[sid] && !horsS(sid)) { const at = el("span", "attente", `${esc(SAL[sid].label)} : demande d'absence en attente`); at.title = "Demande à décider sur l'écran des absences ; ne bloque pas le planning"; day.appendChild(at); }
  for (const p of DATA.praticiens) { const l = DATA.jours[iso]?.[p.id]; if (l && !l.pr && l.n > 0) notes.push(`<div>${esc(p.label)} · agenda ${l.v === "non planifié" ? "non ouvert" : esc(l.v)}, ${l.n} RDV</div>`); }
  for (const s of DATA.salaries) { const c = congeDe(s.id, iso); if (c && !c.bloque && !horsS(s.id)) notes.push(`<div>ℹ ${esc(s.label)} : ${esc(c.type.toLowerCase())}</div>`); }
  if (notes.length) day.appendChild(el("div", "notes", notes.join("")));
  return day;
}
function setTitle() { const qui = nomsFiltre(); document.getElementById("title").innerHTML = `Planning assistantes <span class="month">${esc(DATA.meta.libelle)}</span>` + (qui ? ` <span class="who">· ${esc(qui)}</span>` : ""); }
function setFilter(f) { FILTER = f; render(); setTitle(); const qui = nomsFiltre(); document.title = `Planning assistantes — ${DATA.meta.libelle}` + (qui ? ` — ${qui}` : ""); }
function renderPalette() {
  const palette = document.getElementById("palette"); palette.innerHTML = "";
  const collapsed = document.body.classList.contains("pal-collapsed");
  const tg = el("button", "ptoggle", collapsed ? "Réserve ›" : "‹ Replier"); tg.title = collapsed ? "Afficher la réserve" : "Replier la réserve pour agrandir le calendrier";
  tg.addEventListener("click", () => { document.body.classList.toggle("pal-collapsed"); renderPalette(); });
  palette.appendChild(tg);
  // Brique 8 (D8.9, D8.10) : sommaire des semaines, hors de .pbody donc visible panneau replié ; « tout replier / déplier » à côté
  const som = el("nav", "sommaire"); som.setAttribute("aria-label", "Semaines");
  WEEKS.forEach((w, wi) => {
    const b = el("button", "sw" + (wi === CURRENT_WEEK ? " on" : "") + (PLIEES.has(wi) ? " pliee" : ""), `<span class="s">S</span>${w.num}`);
    b.type = "button"; b.title = `Semaine ${w.num}` + (PLIEES.has(wi) ? " (repliée)" : ""); b.addEventListener("click", () => allerA(wi)); som.appendChild(b);
  });
  for (const [texte, court, titre, jeu] of [["tout replier", "▾▾", "Replier toutes les semaines sur leur bande", () => new Set(WEEKS.keys())], ["tout déplier", "▴▴", "Déplier toutes les semaines", () => new Set()]]) {
    const b = el("button", "sw tous", collapsed ? court : texte); b.type = "button"; b.title = titre;
    b.addEventListener("click", () => { PLIEES = jeu(); render(); }); som.appendChild(b);
  }
  palette.appendChild(som);
  const pal = el("div", "pbody"); palette.appendChild(pal);
  const w = WEEKS[CURRENT_WEEK], d = shownDays(w);
  // --- praticiens en tête : un clic filtre la vue
  pal.appendChild(el("div", "grp", "Praticiens"));
  const chips = el("div", "pchips");
  for (const p of DATA.praticiens) { const c = el("button", "pchip" + (FILTER?.p?.includes(p.id) ? " on" : ""), esc(p.label)); c.style.setProperty("--pc", p.couleur[1]); c.title = p.nom; c.addEventListener("click", () => setFilter(basculer("p", p.id))); chips.appendChild(c); }
  pal.appendChild(chips);
  // --- filtre actif
  const fb = el("div", "filtre-bar" + (FILTER ? " on" : "")); fb.style.marginTop = "6px";
  if (FILTER) { fb.innerHTML = `Vue filtrée : <b>${esc(nomsFiltre())}</b>`; const off = el("button", "btn", "Tout afficher"); off.addEventListener("click", () => setFilter(null)); fb.appendChild(off); }
  pal.appendChild(fb);

  // --- tuiles salariées
  for (const [role, titre] of [["assistante","Assistantes"],["secretaire","Secrétaires"]]) {
    pal.appendChild(el("div", "grp", `${titre}<span class="wk-hint">${d.length ? `${fmtJour(d[0])} → ${fmtJour(d[d.length-1])}` : ""}</span>`));
    const grid = el("div", "tiles");
    for (const s of DATA.salaries.filter(x => x.role === role)) {
      const j = jauge(s, w), r = j.r, q = j.q, h = heures(s, w);
      const tile = el("div", "tile" + (FILTER?.s?.includes(s.id) ? " on" : "")); tile.style.setProperty("--fg", s.couleur[1]); tile.style.setProperty("--bg", s.couleur[0]);
      const badges = {}; for (const v of j.v) badges[v.code] = badges[v.code] ? badges[v.code] + 1 : 1;
      const badgeHtml = Object.entries(badges).map(([code, n]) => `<span class="badge-abs ${j.v.find(v => v.code === code).cls}">${esc(code)}${n > 1 ? " ×" + n : ""}</span>`).join("");
      const nm = el("div", "nm", `<i></i>${esc(s.label)}${badgeHtml}<small>${s.heures_fixes ? `${s.fixes.length} j fixes` : s.etudiante ? "étudiante" : `${s.heures} h`}</small>`);
      const acts = el("div", "acts");
      const plus = el("button", null, "+"); plus.title = `Journée supplémentaire (hors quota, +${fmtH(HB.J)}) pour ${s.label}`;
      plus.addEventListener("click", ev => { ev.stopPropagation(); ARMED = {s:s.id, t:"J", x:true}; render(); toast(`Journée supplémentaire pour ${s.label} (+${fmtH(HB.J)}) : cliquez la case où la placer.`); });
      acts.appendChild(plus);
      nm.appendChild(acts); tile.appendChild(nm);
      if (s.etudiante) { const n = nbCoursMois(s.id); tile.appendChild(el("div", "crs", `<span>cours ce mois</span><b>${n}</b>`)); }
      tile.appendChild(el("div", "mt", `<span class="squares">${j.sq || "—"}</span><span class="cnt">${j.texte}</span>${!r.rest.length && q.length ? '<span class="done" title="semaine placée">✓</span>' : ""}${h.sup ? `<span class="sup" title="heures supplémentaires cette semaine">+${fmtH(h.sup)}</span>` : ""}`));
      if (r.rest.length) { const stack = el("div", "stack"); r.rest.forEach(t => stack.appendChild(brickEl({s:s.id, t, x:false}, {palette:true}))); tile.appendChild(stack); }
      tile.addEventListener("click", ev => { if (ev.target.closest(".brick,button")) return; setFilter(basculer("s", s.id)); });
      grid.appendChild(tile);
    }
    pal.appendChild(grid);
  }
  if (ARMED?.x) { const note = el("div", "sub", `Journée supplémentaire de ${SAL[ARMED.s].label} en main — cliquez une case.`); note.style.color = "var(--warn)"; note.style.marginTop = "8px"; pal.appendChild(note); }
  document.body.classList.toggle("placing", !!ARMED);
  pal.appendChild(el("div", "hint", "Cliquez un ou plusieurs noms pour filtrer (Échap efface). Glissez une brique (ou cliquez-la puis la case). + journée sup. Les absences et les cours se corrigent depuis l'écran des absences. Glissez une brique posée jusqu'ici pour la retirer. Ctrl+Z annule."));
  palette.addEventListener("dragover", ev => { if (DRAG?.from) { ev.preventDefault(); palette.classList.add("over"); } });
  palette.addEventListener("dragleave", () => palette.classList.remove("over"));
  palette.addEventListener("drop", ev => { ev.preventDefault(); palette.classList.remove("over"); if (DRAG?.from) { retirer(DRAG.from); DRAG = null; } });
}

// ------------------------------------------------------------ fichiers : export, import, copie
function download(name, text, type) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
function exportJson() { download(`planning-assistantes_${DATA.meta.mois}.json`, JSON.stringify(M.exporter(META.numero), null, 1), "application/json"); }
function importFrom(text) {   // export JSON, ou HTML enregistré (bloc planning-state)
  let src = null;
  try { if (text.trim().startsWith("{")) src = JSON.parse(text);
        else { const m = text.match(/<script id="planning-state"[^>]*>([\s\S]*?)<\/script>/); if (m) src = JSON.parse(m[1]); } } catch(e) {}
  const r = M.importer(src);
  if (!r) { toast("Fichier non reconnu : il faut un export JSON ou une copie HTML du planning.", true); return; }
  commit();
  const parts = [`${r.jours} jour(s) repris`];
  if (r.ignorees) parts.push(`${r.ignorees} brique(s) ignorée(s) (personne absente de la fiche ou brique illisible)`);
  if (r.orphelines) parts.push(`${r.orphelines} brique(s) sur un praticien absent ce jour-là (lignes « Hors présence »)`);
  toast(parts.join(", ") + ".");
}

// ------------------------------------------------------------ API : enregistrer, erreurs
async function enregistrer() {
  if (META.autonome) return;
  const locales = M.verifier();
  if (locales.length) { afficherViolations(locales, "Enregistrement refusé par la page"); return; }
  let r;
  try {
    r = await fetch(META.urls.versions, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()}, body: JSON.stringify(M.charge(META.numero))});
  } catch (e) { toast("Réseau indisponible : rien n'a été enregistré.", true); return; }
  if (r.redirected || !(r.headers.get("content-type") || "").includes("application/json")) {
    bandeau("Session expirée : exportez votre travail (Exporter (JSON)), puis rechargez la page pour vous reconnecter.", true); return;
  }
  let corps = {}; try { corps = await r.json(); } catch (e) {}
  if (r.status === 201) {
    META.numero = corps.numero; DERNIERE = M.empreinte();
    // la route de publication suit le numéro : sans rechargement, le bouton Publier doit viser la version qu'on vient d'enregistrer
    META.urls.publier = `${META.urls.versions}${corps.numero}/publier/`;
    afficherViolations([], ""); bandeau(""); render(); toast(`Version ${corps.numero} enregistrée.`);
  }
  else if (r.status === 409) bandeauConflit(corps.derniere);
  else if (r.status === 422) afficherViolations(corps.violations ?? [], "Enregistrement refusé par le serveur");
  else if (r.status === 403) bandeau("Accès refusé : ce compte ne peut pas enregistrer le planning.", true);
  else toast(`Enregistrement impossible (${r.status}).`, true);
}
async function publier() {   // brique 4b : publie la dernière version enregistrée, celle que la page affiche sans modification
  if (META.autonome || !META.urls?.publier) return;
  if (!confirm(`Publier la version ${META.numero} ? Chaque salariée verra ses jours dans « Mes jours ».`)) return;
  const locales = M.verifier();
  if (locales.length) { afficherViolations(locales, "Publication refusée par la page", "publié"); return; }
  let r;
  try {
    r = await fetch(META.urls.publier, {method: "POST", credentials: "same-origin", headers: {"X-CSRFToken": csrf()}});
  } catch (e) { toast("Réseau indisponible : rien n'a été publié.", true); return; }
  if (r.redirected || !(r.headers.get("content-type") || "").includes("application/json")) {
    bandeau("Session expirée : rechargez la page pour vous reconnecter, puis publiez à nouveau.", true); return;
  }
  let corps = {}; try { corps = await r.json(); } catch (e) {}
  if (r.status === 200) { META.publiee = corps.numero; afficherViolations([], ""); bandeau(""); majEntete(); toast(corps.deja_publiee ? `Version ${corps.numero} déjà publiée.` : `Version ${corps.numero} publiée.`); }
  else if (r.status === 409) bandeauConflit(corps.derniere, "publication");
  else if (r.status === 422) afficherViolations(corps.violations ?? [], "Publication refusée par le serveur", "publié");
  else if (r.status === 403) bandeau("Accès refusé : ce compte ne peut pas publier le planning.", true);
  else toast(`Publication impossible (${r.status}).`, true);
}
function bandeauConflit(derniere, contexte = "enregistrement") {
  const b = document.getElementById("banner"); b.className = "banner err";
  if (contexte === "publication") {
    b.textContent = `Quelqu'un a enregistré la version ${derniere} entre-temps : la publication est refusée. Rechargez la page pour voir cette version.`;
  } else {
    b.textContent = `Quelqu'un a enregistré la version ${derniere} entre-temps : votre enregistrement est refusé. Exportez votre travail (Exporter (JSON)), puis rechargez la page et réimportez-le.`;
    const exp = el("button", "btn", "Exporter (JSON)"); exp.addEventListener("click", exportJson); b.appendChild(exp);
  }
  const rl = el("button", "btn", "Recharger"); rl.addEventListener("click", () => location.reload()); b.appendChild(rl);
}
function signalerErreur(nom, source, ligne) {
  if (META.autonome || !META.urls?.erreurs) return;
  try {
    fetch(META.urls.erreurs, {method: "POST", credentials: "same-origin", keepalive: true, headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
      body: JSON.stringify({nom: String(nom ?? "Erreur").slice(0, 80), source: String(source ?? "").slice(0, 80), ligne: String(ligne ?? "").slice(0, 80), mois: META.mois})}).catch(() => {});
  } catch (e) {}
}

// ------------------------------------------------------------ démarrage
function boot() {
  setTitle();
  document.title = `Planning assistantes — ${DATA.meta.libelle}` + (META.autonome ? ` (copie v${META.numero})` : "");
  // Brique 8 (D8.3) : la date des données prend la place de l'horodatage de génération — date locale « AAAA-MM-JJ » servie par la vue, découpée sans Date (le jour est celui du cabinet)
  const du = META.donnees_du;
  document.getElementById("subtitle").textContent = (du ? `Données Doctolib du ${du.slice(8, 10)}/${du.slice(5, 7)} · ` : "Doctolib · ") + `présence = agenda ouvert ou ≥ ${DATA.meta.seuils.presence_h} h de rendez-vous`;
  // Brique 6d : `bottom` du .topbar collé = barre commune (absente de la copie) + barre d'outils ; la réserve colle dessous
  const mesure = () => document.documentElement.style.setProperty("--topbar-h", document.querySelector(".topbar").getBoundingClientRect().bottom + "px");
  mesure(); window.addEventListener("resize", mesure); if (window.ResizeObserver) new ResizeObserver(mesure).observe(document.querySelector(".topbar"));
  const alertes = (DATA.meta.alertes ?? []).slice();
  if (alertes.length) bandeau(esc(alertes.join(" · ")));
  // Brique 8 (D8.8) : lignes de rôle repliées, mémorisées par le navigateur (localStorage), par type de ligne
  try { REPLIS = JSON.parse(localStorage.getItem(CLE_REPLIS) ?? "{}") || {}; } catch (e) { REPLIS = {}; }
  // Brique 8 (D8.9, D8.9-bis, décision B) : jour actuel en date locale (jamais toISOString) ; quand il tombe dans la grille,
  // les semaines passées s'ouvrent repliées et la réserve s'ouvre sur la semaine en cours ; mois passé ou à venir : tout déplié
  const t = new Date(); AUJOURDHUI = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  if (WEEKS.length && AUJOURDHUI >= WEEKS[0].days[0] && AUJOURDHUI <= WEEKS[WEEKS.length - 1].days[6]) {
    WEEKS.forEach((w, wi) => { if (w.days[6] < AUJOURDHUI) PLIEES.add(wi); });
    CURRENT_WEEK = Math.max(0, WEEKS.findIndex(w => w.days.includes(AUJOURDHUI)));
  }
  document.addEventListener("dragover", ev => { DERNIER_Y = ev.clientY; });   // brique 8 (D8.12) : position du pointeur pendant un glisser
  for (const s of DATA.salaries) TXT[s.id] = texteSur(s.couleur[1]);   // brique 8, lot 5 : texte blanc ou noir selon la luminance de l'encre
  // La proposition ne dépend que du numéro de version servi : 0 = aucune version, on propose.
  if (META.numero === 0 && !META.autonome) M.initialState();
  render();
  document.getElementById("btnSave").addEventListener("click", enregistrer);
  document.getElementById("btnPublier").addEventListener("click", publier);
  document.getElementById("btnCopie").addEventListener("click", () => { if (!META.autonome && META.urls.copie && M.empreinte() === DERNIERE && META.numero) location.href = META.urls.copie; });
  document.getElementById("btnExport").addEventListener("click", exportJson);
  document.getElementById("btnPrint").addEventListener("click", () => window.print());
  document.getElementById("btnUndo").addEventListener("click", annuler);
  document.getElementById("btnPropose").addEventListener("click", () => { M.snapshot(); let n = 0; for (const w of WEEKS) n += M.proposer(w); commit(); toast(n ? `${n} brique${n > 1 ? "s" : ""} proposée${n > 1 ? "s" : ""} dans les cases vides.` : "Rien à compléter : toutes les briques disponibles sont posées."); });
  document.getElementById("btnImport").addEventListener("click", () => document.getElementById("importFile").click());
  document.getElementById("importFile").addEventListener("change", ev => { const f = ev.target.files[0]; if (!f) return; f.text().then(importFrom); ev.target.value = ""; });
  document.getElementById("btnReset").addEventListener("click", () => { if (confirm("Refaire toute la proposition ? Les placements manuels seront perdus.")) { M.snapshot(); M.initialState(); commit(); toast("Nouvelle proposition calculée"); } });
  // Brique 6d : le menu « Plus » (<details>) se referme après une entrée ou un clic hors du menu
  const plus = document.querySelector(".plus");
  plus.querySelector(".plus-menu").addEventListener("click", ev => { if (ev.target.closest("button")) plus.open = false; });
  document.addEventListener("click", ev => { if (plus.open && !(ev.composedPath ? ev.composedPath() : []).includes(plus)) plus.open = false; });
  document.addEventListener("click", ev => { if (!CPOP) return; const chemin = ev.composedPath ? ev.composedPath() : []; if (!chemin.some(n => n.id === "cpop" || n.classList?.contains("cbub") || n.classList?.contains("cbtn"))) closeCpop(); });
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape") { hideTip(true); if (CPOP) closeCpop(); else if (ARMED) { ARMED = null; render(); } else if (FILTER) setFilter(null); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); annuler(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); if (!META.autonome) enregistrer(); }
    // Brique 8 (D8.13) : ← → d'une semaine à l'autre, seulement sans rien en main, sans modificateur, hors champs, panneau et commentaires
    if ((ev.key === "ArrowLeft" || ev.key === "ArrowRight") && !DRAG && !ARMED && !ev.ctrlKey && !ev.metaKey && !ev.altKey && !ev.shiftKey && !ev.target.closest("input,select,textarea,.palette,.cpop")) {
      ev.preventDefault(); allerA(Math.min(WEEKS.length - 1, Math.max(0, CURRENT_WEEK + (ev.key === "ArrowRight" ? 1 : -1))));
    }
  });
  window.addEventListener("beforeunload", ev => { if (META.autonome) return; if (M.empreinte() !== DERNIERE) { ev.preventDefault(); ev.returnValue = ""; } });
  window.onerror = (message, source, ligne, colonne, erreur) => { signalerErreur(erreur?.name ?? "Erreur", source, ligne); };
  window.addEventListener("unhandledrejection", ev => { signalerErreur(String(ev.reason?.name ?? "Rejet"), "", ""); });
}
boot();
})();
