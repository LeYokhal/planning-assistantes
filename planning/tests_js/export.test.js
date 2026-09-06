// Export JSON, charge envoyée à l'API, nettoyage : la structure est figée ici.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PlanningMoteur = require("../static/planning/moteur.js");

const DATA = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "data_fictif.json"), "utf8"));
const STATE = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "state_fictif.json"), "utf8"));
const CLES = ["affectations", "feries", "feries_off", "notes"];

test("exporter : clés exactes, sans congé, sans cours, sans type d'absence", () => {
  const m = PlanningMoteur.creer(structuredClone(DATA), structuredClone(STATE));
  const e = m.exporter(3);
  assert.deepEqual(Object.keys(e), ["mois", "numero", "affectations", "feries", "feries_off", "notes", "exporte"]);
  assert.equal(e.mois, "2026-10");
  assert.equal(e.numero, 3);
  assert.deepEqual(e.affectations, STATE.affectations);
  const texte = JSON.stringify(e);
  for (const interdit of ["conges", "cours", "Congé", "Retard", "bloque"]) assert.equal(texte.includes(interdit), false, interdit);
});

test("charge : version_de_base et un state aux quatre clés, copié", () => {
  const m = PlanningMoteur.creer(structuredClone(DATA), structuredClone(STATE));
  const c = m.charge(2);
  assert.deepEqual(Object.keys(c), ["version_de_base", "state"]);
  assert.equal(c.version_de_base, 2);
  assert.deepEqual(Object.keys(c.state).sort(), CLES);
  c.state.affectations["2026-09-29"].alice_dup[0].s = "autre";
  assert.equal(m.state.affectations["2026-09-29"].alice_dup[0].s, "emma_ber");
});

test("nettoyer : clés interdites retirées, notes normalisées en liste", () => {
  const propre = PlanningMoteur.nettoyer({
    affectations: {"2026-09-29": {}}, conges: [1], cours: {}, modifie: "x", initialise: true,
    feries: {"2026-10-02": 7}, feries_off: ["2026-11-01", 3, null], notes: {"a": " un ", "b": ["", "deux", 4], "c": [], "d": ""},
  });
  assert.deepEqual(propre, {affectations: {"2026-09-29": {}}, feries: {"2026-10-02": "7"}, feries_off: ["2026-11-01"], notes: {a: ["un"], b: ["deux"]}});
  assert.deepEqual(PlanningMoteur.nettoyer(null), {affectations: {}, feries: {}, feries_off: [], notes: {}});
});

test("empreinte : identique pour deux états égaux à l'ordre des clés près", () => {
  const a = PlanningMoteur.creer(structuredClone(DATA), {notes: {"2026-09-29": ["x"]}, affectations: {"2026-09-29": {"alice_dup": [{a: false, x: false, t: "J", s: "emma_ber"}]}}});
  const b = PlanningMoteur.creer(structuredClone(DATA), {affectations: {"2026-09-29": {"alice_dup": [{s: "emma_ber", t: "J", x: false, a: false}]}}, notes: {"2026-09-29": "x"}});
  assert.equal(a.empreinte(), b.empreinte());
  b.place("2026-10-01", "bob_mar", {s: "lina_rou", t: "J", x: false});
  assert.notEqual(a.empreinte(), b.empreinte());
});
