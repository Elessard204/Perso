from analyse import doublons_externes
from journal import Journal
from modele import Alerte, Ligne, Proposition


def prop(bon_id, *cles):
    lignes = [Ligne(501, "MO", "", 1, 95.0)]
    lignes += [Ligne(None, "Vis", "", 1, 11.0, 10.0, None, f"{c}|1") for c in cles]
    return Proposition(bon_id, "m", "d", "d", lignes, [], [Alerte("transport_a_definir", "t")], {})


class FauxProg:
    def __init__(self, porteurs=None):
        self.porteurs = porteurs or {}
        self.appels = 0

    def bon_avec_ligne(self, external_id):
        self.appels += 1
        return self.porteurs.get(external_id)


def codes(p):
    return [a.code for a in p.alertes]


def test_meme_facture_dans_deux_bons_du_lot(tmp_path):
    a, b = prop(1, "rona|A-1"), prop(2, "rona|A-1")
    doublons_externes([a, b], Journal(tmp_path, "h"), None, {})
    assert "facture_autre_bon" not in codes(a)
    assert "facture_autre_bon" in codes(b) and b.statut == "bloque"
    assert "1" in b.alertes[-1].message


def test_facture_deja_ecrite_dans_un_autre_bon(tmp_path):
    j = Journal(tmp_path, "h")
    j.inscrire("ecrit", 9, "m", {"external_ids": ["rona|A-1|1"]})
    p = prop(1, "rona|A-1")
    doublons_externes([p], j, None, {})
    assert p.statut == "bloque" and "9" in p.alertes[-1].message


def test_facture_deja_dans_progression(tmp_path):
    p = prop(1, "rona|A-1")
    doublons_externes([p], Journal(tmp_path, "h"), FauxProg({"rona|A-1|1": 55}), {})
    assert p.statut == "bloque" and "55" in p.alertes[-1].message


def test_meme_bon_dans_progression_n_est_pas_un_doublon(tmp_path):
    p = prop(1, "rona|A-1")
    doublons_externes([p], Journal(tmp_path, "h"), FauxProg({"rona|A-1|1": 1}), {})
    assert p.statut == "a_verifier"


def test_recalcul_sans_accumulation_et_memo(tmp_path):
    a, b = prop(1, "rona|A-1"), prop(2, "rona|A-1")
    prog, memo = FauxProg(), {}
    for _ in range(3):
        doublons_externes([a, b], Journal(tmp_path, "h"), prog, memo)
    assert codes(b).count("facture_autre_bon") == 1
    assert prog.appels == 1   # une seule requête par facture
    doublons_externes([b], Journal(tmp_path, "h"), prog, memo)   # le bon 1 n'est plus dans le lot
    assert "facture_autre_bon" not in codes(b)
