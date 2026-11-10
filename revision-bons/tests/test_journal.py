from journal import Journal


def test_inscrire_puis_relire(tmp_path):
    j = Journal(tmp_path, "hugo")
    j.inscrire("approuve", 1, "m1", {"code": "BS-1"})
    [e] = j.historique()
    assert (e["evenement"], e["bon_id"], e["maj"], e["personne"], e["details"]) == ("approuve", 1, "m1", "hugo", {"code": "BS-1"})
    assert e["horodatage"]
    assert (tmp_path / "hugo.jsonl").exists()


def test_historique_combine_et_trie(tmp_path):
    Journal(tmp_path, "hugo").inscrire("ecrit", 1, "m1", {})
    Journal(tmp_path, "autre").inscrire("ecrit", 2, "m2", {})
    h = Journal(tmp_path, "hugo").historique()
    assert [e["bon_id"] for e in h] == [2, 1]   # plus récent d'abord


def test_deja_ecrit_meme_maj_seulement(tmp_path):
    j = Journal(tmp_path, "hugo")
    j.inscrire("ecrit", 1, "m1", {})
    j.inscrire("echec", 2, "m2", {})
    assert j.deja_ecrit(1, "m1")
    assert not j.deja_ecrit(1, "m-autre")
    assert not j.deja_ecrit(2, "m2")


def test_factures_refacturees(tmp_path):
    Journal(tmp_path, "autre").inscrire("ecrit", 42, "m", {"external_ids": ["rona|A-1|1", "rona|A-1|2", "bmr|9|1"]})
    assert Journal(tmp_path, "hugo").factures_refacturees() == {"rona|A-1": 42, "bmr|9": 42}


def test_ligne_corrompue_ignoree(tmp_path):
    j = Journal(tmp_path, "hugo")
    j.inscrire("ecrit", 1, "m1", {})
    with open(tmp_path / "hugo.jsonl", "a", encoding="utf-8") as f:
        f.write("{coupé\n")
    assert len(j.historique()) == 1
