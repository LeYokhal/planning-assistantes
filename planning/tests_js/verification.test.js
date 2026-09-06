// Vérification stricte côté page : mêmes cas que planning/tests/test_verification.py.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PlanningMoteur = require("../static/planning/moteur.js");

const FICHIER = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "tests", "cas_verification.json"), "utf8"));

for (const cas of FICHIER.cas) {
  test(`verifier · ${cas.nom}`, () => {
    const data = structuredClone(cas.data ?? FICHIER.data_commune);
    const m = PlanningMoteur.creer(data, structuredClone(cas.state));
    const codes = m.verifier().map(v => v.code).sort();
    assert.deepEqual(codes, [...cas.attendu].sort());
  });
}

test("chaque violation ne porte que code, date, slot, s", () => {
  const m = PlanningMoteur.creer(structuredClone(FICHIER.data_commune), {affectations: {"2026-09-29": {"alice_dup": [{s: "zoe_gir", t: "J"}]}}});
  for (const v of m.verifier()) assert.deepEqual(Object.keys(v).sort(), ["code", "date", "s", "slot"]);
});

test("tous les codes annoncés existent et aucun autre n'est émis", () => {
  const emis = new Set();
  for (const cas of FICHIER.cas) {
    const m = PlanningMoteur.creer(structuredClone(cas.data ?? FICHIER.data_commune), structuredClone(cas.state));
    for (const v of m.verifier()) emis.add(v.code);
  }
  for (const code of emis) assert.ok(PlanningMoteur.CODES.includes(code), code);
  for (const code of PlanningMoteur.CODES) assert.ok(emis.has(code), `code jamais émis par le jeu de cas : ${code}`);
});
