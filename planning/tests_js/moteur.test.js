// Recette du moteur (brique 4a) : node --test "planning/tests_js/**/*.test.js"
// Module intégré node:test, aucune dépendance. Fixtures fictives uniquement.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PlanningMoteur = require("../static/planning/moteur.js");

const lire = nom => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", nom), "utf8"));
const DATA = lire("data_fictif.json");
const ATTENDU = lire("proposition_attendue.json");
const STATE_FICTIF = lire("state_fictif.json");
const vide = () => ({affectations: {}, feries: {}, feries_off: [], notes: {}});
const moteur = (state = vide()) => PlanningMoteur.creer(structuredClone(DATA), state);
const b = (s, t = "J", x = false) => ({s, t, x});

test("le moteur ne propose jamais de lui-même", () => {
  const m = moteur();
  assert.deepEqual(m.state.affectations, {});
  assert.equal(m.peutAnnuler(), false);
});

test("initialState reproduit la proposition de référence figée depuis Chrome", () => {
  const m = moteur();
  m.initialState();
  assert.deepEqual(m.state.affectations, ATTENDU.affectations);
});

test("la proposition de référence ne viole aucune règle stricte", () => {
  const m = moteur();
  m.initialState();
  assert.deepEqual(m.verifier(), []);
});

test("le state est muté en place, jamais réassigné, et réduit aux quatre clés", () => {
  const state = {affectations: {}, conges: [{s: "emma_ber", date: "2026-10-13", type: "x", bloque: true}], cours: {}, modifie: "hier", initialise: true};
  const m = moteur(state);
  assert.equal(m.state, state);
  assert.deepEqual(Object.keys(state).sort(), ["affectations", "feries", "feries_off", "notes"]);
  m.initialState();
  assert.equal(m.state, state);
  assert.ok(Object.keys(state.affectations).length > 0);
});

test("place refuse une exclusive hors de son binôme", () => {
  const m = moteur();
  assert.deepEqual(m.place("2026-09-29", "alice_dup", b("zoe_gir")), {ok: false, code: "exclusive_ailleurs"});
  assert.deepEqual(m.state.affectations, {});
});

test("place refuse une non-binôme chez un praticien exclusif", () => {
  const m = moteur();
  assert.equal(m.place("2026-09-29", "chloe_ler", b("emma_ber")).code, "exclusif_intrus");
});

test("place admet une exclusive en sureffectif (reliquat du moteur)", () => {
  const m = moteur();
  assert.equal(m.place("2026-09-29", "sureffectif", b("zoe_gir")).ok, true);
});

test("place bascule en sureffectif quand le praticien est pourvu", () => {
  const m = moteur();
  assert.equal(m.place("2026-09-29", "alice_dup", b("emma_ber")).ok, true);
  const r = m.place("2026-09-29", "alice_dup", b("nora_fon"));
  assert.equal(r.ok, true);
  assert.equal(r.cible, "sureffectif");
  assert.equal(r.bascule.id, "alice_dup");
  assert.equal(m.state.affectations["2026-09-29"].sureffectif[0].s, "nora_fon");
});

test("place refuse un jour bloqué, un doublon, un praticien absent, un jour sans données", () => {
  const m = moteur();
  assert.equal(m.place("2026-10-13", "alice_dup", b("emma_ber")).code, "jour_bloque");   // congé payé
  assert.equal(m.place("2026-10-06", "sureffectif", b("lea_mor")).code, "jour_bloque");  // cours
  assert.equal(m.place("2026-10-17", "chloe_ler", b("zoe_gir")).code, "jour_bloque");    // férié du samedi
  assert.equal(m.place("2026-09-29", "alice_dup", b("emma_ber")).ok, true);
  assert.equal(m.place("2026-09-29", "sureffectif", b("emma_ber")).code, "doublon_jour");
  assert.equal(m.place("2026-09-30", "bob_mar", b("lina_rou")).code, "praticien_absent");
  assert.equal(m.place("2026-09-28", "secretariat", b("sara_pet")).code, "jour_non_affiche");
  assert.equal(m.place("2026-12-01", "alice_dup", b("emma_ber")).code, "hors_plage");
});

test("place refuse la cinquième brique de la semaine sauf hors quota", () => {
  const m = moteur();
  for (const [iso, slot] of [["2026-09-29", "alice_dup"], ["2026-09-30", "alice_dup"], ["2026-10-01", "alice_dup"], ["2026-10-02", "alice_dup"]]) assert.equal(m.place(iso, slot, b("emma_ber")).ok, true);
  assert.equal(m.place("2026-10-03", "sureffectif", b("emma_ber")).code, "quota_depasse");
  assert.equal(m.place("2026-10-03", "sureffectif", b("emma_ber", "J", true)).ok, true);
  assert.deepEqual(m.verifier(), []);
});

test("virtuels : un cours consomme la journée courte de l'étudiante", () => {
  const m = moteur();
  const lea = m.SAL.lea_mor, semaine = m.WEEKS[1];   // semaine du 5 octobre, cours le 6
  assert.equal(m.virtuels(lea, semaine).filter(v => v.prefer === "C").length, 1);
  assert.deepEqual(m.reserve(lea, semaine).rest, ["J", "J", "J"]);
  assert.deepEqual(m.reserve(lea, m.WEEKS[0]).rest, ["J", "J", "J", "C"]);
});

test("virtuels : le férié du samedi ne consomme rien, un férié en semaine consomme", () => {
  const m = moteur();
  const zoe = m.SAL.zoe_gir;
  assert.equal(m.virtuels(zoe, m.WEEKS[2]).length, 0);            // samedi 17 férié
  m.fermerJour("2026-10-14");
  assert.equal(m.virtuels(zoe, m.WEEKS[2]).length, 1);
  assert.deepEqual(m.reserve(zoe, m.WEEKS[2]).rest, ["J", "J", "J"]);
});

test("fermerJour retire les briques du jour, rouvrirJour restaure, undo annule", () => {
  const m = moteur(structuredClone(STATE_FICTIF));
  assert.equal(m.isFerie("2026-10-02"), true);   // posé dans le state
  assert.equal(m.fermerJour("2026-09-29"), 4);
  assert.equal(m.state.affectations["2026-09-29"], undefined);
  assert.equal(m.isFerie("2026-09-29"), true);
  m.rouvrirJour("2026-09-29");
  assert.equal(m.isFerie("2026-09-29"), false);
  assert.equal(m.undo(), true);   // annule la réouverture
  assert.equal(m.isFerie("2026-09-29"), true);
  assert.equal(m.undo(), true);   // annule la fermeture : les briques reviennent
  assert.equal(m.state.affectations["2026-09-29"].alice_dup[0].s, "emma_ber");
  assert.equal(m.undo(), false);
  m.rouvrirJour("2026-11-01");    // férié du serveur : passe par feries_off
  assert.deepEqual(m.state.feries_off, ["2026-11-01"]);
});

test("poserNotes normalise, vide = suppression", () => {
  const m = moteur();
  assert.deepEqual(m.poserNotes("2026-09-29", ["  a ", "", "b"]), ["a", "b"]);
  assert.deepEqual(m.state.notes, {"2026-09-29": ["a", "b"]});
  m.poserNotes("2026-09-29", [" "]);
  assert.deepEqual(m.state.notes, {});
});

test("importer reprend les affectations de la plage, ignore les salariées inconnues et les briques illisibles", () => {
  const m = moteur();
  const r = m.importer({
    affectations: {
      "2026-09-29": {"alice_dup": [b("emma_ber"), b("inconnue_xyz"), b("nora_fon", "X")]},
      "2026-12-01": {"alice_dup": [b("emma_ber")]},
    },
    feries: {"2026-10-02": "Pont", "2026-12-25": "Noël"},
    feries_off: ["2026-11-01"],
    notes: {"2026-09-29": "ancien format"},
    conges: [{s: "emma_ber", date: "2026-09-29", type: "x", bloque: true}],
    cours: {"lea_mor": ["2026-09-29"]},
  });
  assert.deepEqual(r, {jours: 1, ignorees: 2});
  assert.deepEqual(m.state.affectations, {"2026-09-29": {"alice_dup": [{s: "emma_ber", t: "J", x: false, a: false}]}});
  assert.deepEqual(m.state.feries, {"2026-10-02": "Pont"});
  assert.deepEqual(m.state.feries_off, ["2026-11-01"]);
  assert.deepEqual(m.state.notes, {"2026-09-29": ["ancien format"]});
  assert.deepEqual(Object.keys(m.state).sort(), ["affectations", "feries", "feries_off", "notes"]);
  assert.equal(m.importer({pas: "un export"}), null);
});

test("unplace retire la brique et undo la rend", () => {
  const m = moteur(structuredClone(STATE_FICTIF));
  const retiree = m.unplace("2026-09-29", "alice_dup", 0);
  assert.equal(retiree.s, "emma_ber");
  assert.equal(m.state.affectations["2026-09-29"].alice_dup, undefined);
  m.undo();
  assert.equal(m.state.affectations["2026-09-29"].alice_dup[0].s, "emma_ber");
});

test("SHOWN : du mardi au samedi, jamais le lundi ni le dimanche", () => {
  assert.deepEqual(moteur().SHOWN, [1, 2, 3, 4, 5]);
});

test("les fonctions de rendu ne sont pas dans le moteur", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "static", "planning", "moteur.js"), "utf8");
  for (const interdit of ["document.", "toast(", "confirm(", "render(", "commit(", "alert(", "localStorage"]) assert.equal(source.includes(interdit), false, interdit);
});
