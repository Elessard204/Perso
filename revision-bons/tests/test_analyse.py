import copy
import json
from types import SimpleNamespace

import pytest

from analyse import ajuster_main_oeuvre, analyser_bon, proposition_depuis_dict, proposition_vers_dict
from conftest import LOGICIEL
from journal import Journal
from modele import EntreeTemps, Ligne
from progression import ErreurProgression, bon_depuis_json
from regles import charger_regles
from test_progression import ENTREES, TACHE

R = charger_regles(LOGICIEL / "regles.toml")
CFG = {"claude": {"modele": "claude-opus-5-5", "effort": "medium"}, "progression": {}}
PHOTO = {"genre": "photo", "raison": "Lavabo", "fournisseur": "", "numero": "", "date": "", "sous_total": None, "lignes": []}
FACTURE = {"genre": "facture", "raison": "Reçu", "fournisseur": "Rona", "numero": "A-1", "date": "2026-11-02",
           "sous_total": 20.0, "lignes": [{"description": "Vis", "quantite": 2, "prix_unitaire": 10.0}]}
INCERTAIN = {**PHOTO, "genre": "incertain", "raison": "Flou"}
TEXTE = {"texte": "Remplacement du robinet de cuisine et pose de 2 raccords."}


class FauxClaude:
    """Renvoie les réponses JSON dans l'ordre des appels."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.appels.append(kwargs)
        texte = json.dumps(self.reponses.pop(0))
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=texte)])


class FauxProgression:
    def __init__(self, erreur_sur=()):
        self.erreur_sur = set(erreur_sur)

    def telecharger_piece(self, piece_id):
        if piece_id in self.erreur_sur:
            raise ErreurProgression("Progression ne répond pas.")
        return b"%PDF faux" if piece_id == 9002 else b"\xff\xd8 jpeg"


def nouveau_bon():
    return bon_depuis_json(copy.deepcopy(TACHE), copy.deepcopy(ENTREES), {"champ_description": "description"})


def analyser(bon, claude, tmp_path, journal=None, r=R, progression=None):
    journal = journal or Journal(tmp_path / "journal", "hugo")
    return analyser_bon(bon, progression or FauxProgression(), claude, CFG, r, journal, tmp_path / "cache")


def codes(p):
    return [a.code for a in p.alertes]


def test_arrondi_applique_aux_lignes_pas_aux_entrees(tmp_path):
    bon = nouveau_bon()   # Luc : 80 + 45 = 125 min -> 2 h 15
    p = analyser(bon, FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    mo = next(l for l in p.lignes if l.id == 501)
    assert mo.quantite == 2.25
    assert [e.minutes for e in bon.entrees] == [80, 45]
    assert next(l for l in bon.lignes if l.id == 501).quantite == 2.0833
    assert "Arrondi" in p.origine["501"] and "Luc Tremblay" in p.origine["501"] and "2,25 h" in p.origine["501"]


def test_arrondi_ne_reduit_jamais(tmp_path):
    bon = nouveau_bon()
    bon.lignes[0].quantite = 3.0   # déjà plus haut que 2 h 15
    lignes, origine = ajuster_main_oeuvre(bon, {"Luc Tremblay": 2.25})
    assert lignes[0].quantite == 3.0 and origine == {}


def test_ajout_sur_la_derniere_ligne_du_technicien():
    bon = nouveau_bon()
    bon.lignes.insert(0, Ligne(500, "Main-d'œuvre", "Luc", 1.0, 95.0))
    bon.entrees = [EntreeTemps(1, "Luc Tremblay", None, 60, 500), EntreeTemps(2, "Luc Tremblay", None, 65, 501)]
    bon.lignes[1].quantite = 1.0833
    lignes, _ = ajuster_main_oeuvre(bon, {"Luc Tremblay": 2.25})
    assert [(l.id, l.quantite) for l in lignes[:2]] == [(500, 1.0), (501, 1.25)]


def test_main_oeuvre_introuvable(tmp_path):
    bon = nouveau_bon()
    for e in bon.entrees:
        e.ligne_id = None
    p = analyser(bon, FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert "main_oeuvre_introuvable" in codes(p)
    assert next(l for l in p.lignes if l.id == 501).quantite == 2.0833


def test_main_oeuvre_partagee():
    bon = nouveau_bon()
    bon.entrees.append(EntreeTemps(9, "Max Roy", None, 30, 501))
    lignes, origine = ajuster_main_oeuvre(bon, {"Luc Tremblay": 2.25, "Max Roy": 0.5})
    assert lignes[0].quantite == 2.0833 and origine == {}


def test_ligne_materiel_ajoutee_avec_origine(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    [mat] = [l for l in p.lignes if l.external_id]
    assert (mat.libelle, mat.quantite, mat.cout_unitaire, mat.prix, mat.external_id) == ("Vis", 2, 10.0, 11.0, "rona|A-1|1")
    assert p.origine["rona|A-1|1"] == "Facture Rona A-1, coût + 10 %"
    assert [a.genre for a in p.analyses] == ["photo", "facture"]


def test_photo_ignoree(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert not [l for l in p.lignes if l.external_id]


def test_facture_deja_ecrite_dans_ce_bon_pas_reproposee(tmp_path):
    j = Journal(tmp_path / "journal", "hugo")
    j.inscrire("ecrit", 1001, "ancien", {"external_ids": ["rona|A-1|1"]})
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path, journal=j)
    assert not [l for l in p.lignes if l.external_id]


def test_cache_depend_des_regles(tmp_path):
    analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    claude = FauxClaude(PHOTO, PHOTO, TEXTE)
    analyser(nouveau_bon(), claude, tmp_path, r=copy.copy(R).__class__(**{**R.__dict__, "marge": 0.2}))
    assert len(claude.appels) == 3   # nouvelle marge : nouvelle analyse


def test_echec_de_telechargement_pas_mis_en_cache(tmp_path):
    analyser(nouveau_bon(), FauxClaude(FACTURE, TEXTE), tmp_path, progression=FauxProgression(erreur_sur={9001}))
    claude = FauxClaude(PHOTO, FACTURE, TEXTE)
    p = analyser(nouveau_bon(), claude, tmp_path)
    assert len(claude.appels) == 3 and p.analyses[0].genre == "photo"


def test_meme_facture_deux_fois_dans_le_bon(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(FACTURE, FACTURE, TEXTE), tmp_path)
    assert len([l for l in p.lignes if l.external_id]) == 1
    assert "facture_doublon" in codes(p) and p.statut == "bloque"


def test_facture_deja_dans_le_bon_non_rajoutee(tmp_path):
    bon = nouveau_bon()
    bon.lignes.append(Ligne(503, "Vis", "Rona", 2, 11.0, 10.0, None, "rona|A-1|1"))
    p = analyser(bon, FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    assert [l.id for l in p.lignes if l.external_id] == [503]
    assert "facture_doublon" not in codes(p)


def test_piece_incertaine_continue(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(INCERTAIN, FACTURE, TEXTE), tmp_path)
    assert "piece_incertaine" in codes(p)
    assert [l.external_id for l in p.lignes if l.external_id] == ["rona|A-1|1"]


def test_telechargement_echoue_continue(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(FACTURE, TEXTE), tmp_path, progression=FauxProgression(erreur_sur={9001}))
    assert p.analyses[0].genre == "incertain" and "piece_incertaine" in codes(p)
    assert [l.external_id for l in p.lignes if l.external_id] == ["rona|A-1|1"]


def test_transport_a_definir(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert "transport_a_definir" in codes(p)
    assert next(l for l in p.lignes if l.id == 502).quantite == 1


def test_description_revisee(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert p.description == TEXTE["texte"]
    assert p.description_originale.startswith("changer robinet")


def test_cache_evite_claude(tmp_path):
    analyser(nouveau_bon(), FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    claude = FauxClaude()
    p = analyser(nouveau_bon(), claude, tmp_path)
    assert claude.appels == []
    assert [l.external_id for l in p.lignes if l.external_id] == ["rona|A-1|1"]


def test_aller_retour_dict(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    assert proposition_depuis_dict(json.loads(json.dumps(proposition_vers_dict(p)))) == p


def test_statut(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert p.statut == "a_verifier"   # transport à définir
    p.alertes = []
    assert p.statut == "pret"


def test_achat_declare_sans_facture_signale(tmp_path):
    bon = nouveau_bon()
    bon.achat = "Robinet cuisine"
    p = analyser(bon, FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert "achat_sans_facture" in codes(p) and p.statut == "a_verifier"


def test_achat_coherent_sans_alerte(tmp_path):
    bon = nouveau_bon()
    bon.achat = "Robinet cuisine"
    p = analyser(bon, FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    assert "achat_sans_facture" not in codes(p) and "facture_sans_achat" not in codes(p)
