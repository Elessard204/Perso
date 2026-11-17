import copy
import json
from types import SimpleNamespace

import pytest

from analyse import analyser_bon, proposition_depuis_dict, proposition_vers_dict, transports_en_double
from conftest import LOGICIEL
from journal import Journal
from modele import EntreeTemps, Ligne, Proposition
from progression import ErreurProgression, bon_depuis_json
from regles import charger_regles
from test_progression import ENTREES, TACHE

R = charger_regles(LOGICIEL / "regles.toml")
CFG = {"claude": {"modele": "claude-opus-5-5", "effort": "medium"}, "progression": {}}
PHOTO = {"genre": "photo", "raison": "Lavabo", "fournisseur": "", "numero": "", "date": "", "sous_total": None, "lignes": []}
FACTURE = {"genre": "facture", "raison": "Reçu", "fournisseur": "Rona", "numero": "A-1", "date": "2026-11-02",
           "sous_total": 20.0, "lignes": [{"description": "Vis", "quantite": 2, "prix_unitaire": 10.0}]}
INCERTAIN = {**PHOTO, "genre": "incertain", "raison": "Flou"}
TEXTE = {"texte": "Remplacement du robinet de cuisine et pose de 2 raccords.", "ajouts_photos": []}


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


def test_piece_incertaine_continue(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(INCERTAIN, FACTURE, TEXTE), tmp_path)
    assert "piece_incertaine" in codes(p)
    assert [l.external_id for l in p.lignes if l.external_id] == ["rona|A-1|1"]


def test_telechargement_echoue_continue(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(FACTURE, TEXTE), tmp_path, progression=FauxProgression(erreur_sur={9001}))
    assert p.analyses[0].genre == "incertain" and "piece_incertaine" in codes(p)
    assert [l.external_id for l in p.lignes if l.external_id] == ["rona|A-1|1"]


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


def test_heures_et_transport_selon_les_regles_de_hugo(tmp_path):
    bon = nouveau_bon()
    p = analyser(bon, FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert next(l for l in p.lignes if l.id == 502).quantite == 1        # transport à 1
    assert next(l for l in p.lignes if l.id == 501).quantite == 2.5      # 2 h 05 + 20 min d'excédent -> 2,5
    assert [e.minutes for e in bon.entrees] == [80, 80, 45]              # feuilles de temps intactes


def test_une_ligne_materiel_par_facture(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    [mat] = [l for l in p.lignes if l.external_id]
    assert (mat.libelle, mat.quantite, mat.cout_unitaire, mat.prix, mat.external_id) == ("Matériel acheté", 1, 20.0, 23.0, "rona|A-1|1")
    assert p.origine["rona|A-1|1"] == "Facture Rona A-1, coût avant taxes + 15 %"


def test_ligne_materiel_vide_reutilisee(tmp_path):
    bon = nouveau_bon()
    bon.lignes.append(Ligne(503, "Matériel acheté", "", 0.0, 0.0, None, "Matériel acheté", None))
    p = analyser(bon, FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    reutilisee = next(l for l in p.lignes if l.id == 503)
    assert (reutilisee.prix, reutilisee.external_id) == (23.0, "rona|A-1|1")
    assert len([l for l in p.lignes if l.external_id]) == 1 and p.lignes_retirees == []


def test_ligne_materiel_vide_inutile_retiree(tmp_path):
    bon = nouveau_bon()
    bon.lignes.append(Ligne(503, "Matériel acheté", "", 0.0, 0.0, None, "Matériel acheté", None))
    p = analyser(bon, FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert p.lignes_retirees == [503] and "retirée" in p.origine["503"]


def test_facture_deja_dans_le_bon_non_rajoutee(tmp_path):
    bon = nouveau_bon()
    bon.lignes.append(Ligne(503, "Matériel acheté", "Rona", 1, 23.0, 20.0, "Matériel acheté", "rona|A-1|1"))
    p = analyser(bon, FauxClaude(PHOTO, FACTURE, TEXTE), tmp_path)
    assert [l.id for l in p.lignes if l.external_id] == [503]


def test_photos_transmises_a_la_redaction(tmp_path):
    claude = FauxClaude(PHOTO, FACTURE, TEXTE)
    analyser(nouveau_bon(), claude, tmp_path)
    contenu = claude.appels[-1]["messages"][0]["content"]
    assert [b["type"] for b in contenu] == ["image", "text"]   # la photo, pas la facture
    assert "Fuite" in contenu[-1]["text"]                       # la demande de départ sert de contexte


def test_marge_calculee(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert p.marge["revenu"] == 212.5 and p.marge["cout"] == 102.5


def test_statut(tmp_path):
    p = analyser(nouveau_bon(), FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert p.statut == "a_verifier"   # transport long : à vérifier
    p.alertes = []
    assert p.statut == "pret"


def _bon_le(code, client_id, jour="2026-11-03"):
    from datetime import date, datetime
    b = nouveau_bon()
    b.code, b.lieu = code, f"{client_id}/1"
    for e in b.entrees:
        e.jour = date.fromisoformat(jour)
        e.debut = datetime.fromisoformat(jour + ("T08:00:00" if code.endswith("1") else "T13:00:00"))
    return b


def test_transport_en_double_meme_immeuble_meme_jour():
    a, b = _bon_le("BS-1", 77), _bon_le("BS-2", 77)
    pa, pb = Proposition(1, "m", "", ""), Proposition(2, "m", "", "")
    transports_en_double([(b, pb), (a, pa)])
    assert [x.code for x in pa.alertes] == [] and [x.code for x in pb.alertes] == ["transport_double"]
    assert "BS-1" in pb.alertes[0].message


def test_pas_de_double_si_autre_immeuble_ou_autre_jour():
    pa, pb, pc = (Proposition(i, "m", "", "") for i in (1, 2, 3))
    transports_en_double([(_bon_le("BS-1", 77), pa), (_bon_le("BS-2", 88), pb), (_bon_le("BS-3", 77, "2026-11-04"), pc)])
    assert not pa.alertes and not pb.alertes and not pc.alertes


def test_bon_pas_encore_facture_montre_seulement_le_blocage(tmp_path):
    # Essai réel du 17 novembre : avant « Facturer », le bon affichait aussi un rabais de 701 $ et « bon à perte »,
    # simples conséquences des lignes pas encore créées.
    b = nouveau_bon()
    b.lignes = [l for l in b.lignes if l.id not in (501, 502)]   # « Facturer » pas encore cliqué
    for e in b.entrees:
        e.ligne_id = None
    p = analyser(b, FauxClaude(PHOTO, PHOTO, TEXTE), tmp_path)
    assert "heures_non_facturees" in codes(p)
    bruit = {"rabais", "bon_a_perte", "bon_sans_revenu", "marge_faible", "excedent_sans_main_oeuvre",
             "transport_manquant", "transport_long"}
    assert not bruit & set(codes(p)) and p.rabais == {}
