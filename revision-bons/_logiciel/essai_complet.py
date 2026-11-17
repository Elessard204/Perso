"""Essai complet sur un poste : vraie IA, vrai Google Maps, lecture seule dans Progression.

Prend des bons d'octobre déjà facturés par Hugo, retire ses lignes de matériel et laisse l'outil les refaire à
partir des factures jointes : on compare ensuite les deux. Pose aussi deux questions à Jarvis, fait rédiger une
recommandation, vérifie la clé Google et calcule une période de kilométrage si des codes postaux sont inscrits.
Rien n'est écrit dans Progression. Le rapport va dans _logiciel/essais/ (texte simple).
"""

from __future__ import annotations

import sys
import time
import traceback
import tomllib
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

if sys.platform == "win32":
    import dependances
    sys.pycache_prefix = str(dependances.dossier_profil() / "pycache")
    sys.dont_write_bytecode = False
    print("Vérification des modules de l'IA...")
    dependances.preparer(ICI / "roues", manifeste=ICI / "roues.toml")

import cles  # noqa: E402
import profil  # noqa: E402
from analyse import analyser_bon  # noqa: E402
from assistant import contexte_bon, contexte_regles, rediger_recommandation, repondre  # noqa: E402
from claude_client import creer_client  # noqa: E402
from facturation import classer  # noqa: E402
from journal import Journal  # noqa: E402
from progression import Progression  # noqa: E402
from regles import charger_regles  # noqa: E402

MAX_BONS = 8
PERIODE_BONS = "2026-10-01,2026-10-31"
ETAT_FACTURE = "700"   # « Transférer au système comptable » : bons déjà facturés par Hugo
# Prix de Claude Opus 5.5 par million de jetons (estimation du coût de l'essai)
PRIX = {"entree": 4.0, "sortie": 20.0, "cache_ecriture": 5.0, "cache_lecture": 0.20}


class Compteur:
    """Enveloppe le client de Claude pour additionner les jetons de chaque appel."""

    def __init__(self, client):
        self._client = client
        self.jetons = {"entree": 0, "sortie": 0, "cache_ecriture": 0, "cache_lecture": 0}
        self.appels = 0

        class _Messages:
            def create(_, **kwargs):
                reponse = self._client.beta.messages.create(**kwargs)
                self.appels += 1
                u = getattr(reponse, "usage", None)
                if u is not None:
                    self.jetons["entree"] += getattr(u, "input_tokens", 0) or 0
                    self.jetons["sortie"] += getattr(u, "output_tokens", 0) or 0
                    self.jetons["cache_ecriture"] += getattr(u, "cache_creation_input_tokens", 0) or 0
                    self.jetons["cache_lecture"] += getattr(u, "cache_read_input_tokens", 0) or 0
                return reponse

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()

    def cout(self) -> float:
        return sum(self.jetons[k] * PRIX[k] / 1_000_000 for k in PRIX)


def argent(x: float) -> str:
    return f"{x:,.2f} $".replace(",", " ").replace(".", ",")


def main() -> None:
    dossier = ICI / "essais"
    dossier.mkdir(exist_ok=True)
    debut_essai = time.time()
    lignes: list[str] = []

    def ecrire(texte: str = "") -> None:
        print(texte)
        lignes.append(texte)

    ecrire(f"ESSAI COMPLET – Révision des bons – {datetime.now():%Y-%m-%d %H:%M}")
    ecrire("Lecture seule : rien n'est écrit dans Progression.")
    c = cles.lire()
    ecrire(f"Clés : Progression {'oui' if c.get('progression') else 'NON'}, Claude {'oui' if c.get('claude') else 'NON'}, "
           f"Google {'oui' if c.get('google') else 'NON'}")
    if not c.get("progression") or not c.get("claude"):
        ecrire("Clés manquantes : les inscrire dans l'onglet Règles, section Connexions, puis relancer.")
        return
    cfg = tomllib.loads((ICI / "config.toml").read_text(encoding="utf-8"))
    r = charger_regles(ICI / "regles.toml")
    prog = Progression(c["progression"], cfg["progression"]["base"], cfg=cfg["progression"])
    client = Compteur(creer_client(c["claude"]))
    journal = Journal(dossier / "journal-essai", "essai")

    # ---------- 1. Matériel et descriptions sur des bons d'octobre ----------
    ecrire("\n=== 1. MATÉRIEL ET DESCRIPTIONS (bons d'octobre déjà facturés par Hugo) ===")
    taches = prog.lister_bons(ETAT_FACTURE, "", PERIODE_BONS)
    ecrire(f"{len(taches)} bons d'octobre trouvés; on garde ceux qui ont des pièces jointes et du matériel facturé.")
    choisis = []
    for t in sorted(taches, key=lambda x: x.get("id", 0), reverse=True):
        if len(choisis) >= MAX_BONS:
            break
        try:
            bon = prog.lire_bon(t["id"])
        except Exception as e:  # un bon illisible ne doit pas arrêter l'essai
            ecrire(f"- {t.get('code')} : lecture impossible ({e})")
            continue
        if bon.pieces and any(classer(l) == "materiel" and l.prix > 0 for l in bon.lignes):
            choisis.append(bon)
    resultats = []
    for bon in choisis:
        ecrire(f"\n--- {bon.code} · {bon.client} · {bon.type_bon} · {len(bon.pieces)} pièce(s) jointe(s)")
        hugo = [l for l in bon.lignes if classer(l) == "materiel" and l.prix > 0]
        total_hugo = sum(l.quantite * l.prix for l in hugo)
        sans_materiel = replace(bon, lignes=[l for l in bon.lignes if classer(l) != "materiel"])
        cout_avant, t0 = client.cout(), time.time()
        try:
            p = analyser_bon(sans_materiel, prog, client, cfg, r, journal, dossier / "cache-essai")
        except Exception as e:
            ecrire(f"ERREUR pendant l'analyse : {type(e).__name__} : {e}")
            ecrire("".join(traceback.format_exc(limit=3)))
            continue
        outil = [l for l in p.lignes if classer(l) == "materiel" and l.external_id]
        total_outil = sum(l.quantite * l.prix for l in outil)
        genres = {}
        for a in p.analyses:
            genres[a.genre] = genres.get(a.genre, 0) + 1
        ecrire(f"Pièces classées : {genres}  ·  {time.time() - t0:.0f} s  ·  coût {argent(client.cout() - cout_avant)}")
        for a in p.analyses:
            if a.genre == "facture" and a.facture:
                f = a.facture
                ecrire(f"  Facture lue : {f.fournisseur} {f.numero} du {f.date} · sous-total {f.sous_total}")
            elif a.genre == "incertain":
                ecrire(f"  Pièce incertaine : {a.raison}")
        ecrire(f"Matériel facturé par Hugo : {argent(total_hugo)}")
        for l in hugo:
            ecrire(f"  - {l.libelle} · {l.description[:120]!r} · {l.quantite:g} × {argent(l.prix)}")
        ecrire(f"Matériel proposé par l'outil : {argent(total_outil)}  (écart {argent(total_outil - total_hugo)})")
        for l in outil:
            ecrire(f"  - {l.libelle} · {l.description[:120]!r} · {l.quantite:g} × {argent(l.prix)}")
        alertes = [f"[{a.code}] {a.message}" for a in p.alertes]
        ecrire("Alertes : " + (" | ".join(alertes) if alertes else "aucune"))
        ecrire(f"Note du technicien : {(bon.description or '(vide)')[:500]!r}")
        ecrire(f"Version proposée   : {(p.description or '(vide)')[:500]!r}")
        resultats.append((bon, p, total_hugo, total_outil))

    if resultats:
        proches = sum(1 for _, _, h, o in resultats if abs(o - h) <= max(1.0, 0.02 * h))
        ecrire(f"\nRÉSUMÉ MATÉRIEL : {proches} bon(s) sur {len(resultats)} à 2 % près du montant d'Hugo. "
               f"Total Hugo {argent(sum(h for *_, h, _ in resultats))}, outil {argent(sum(o for *_, o in resultats))}.")

    # ---------- 2. Jarvis ----------
    ecrire("\n=== 2. JARVIS ===")
    regles_txt = contexte_regles(r)
    for bon, p, *_ in resultats[:2]:
        contexte = contexte_bon(bon, p, p.statut, False)
        alerte = next((a for a in p.alertes if a.code not in ("description_creee", "description_enrichie")), None)
        q1 = (f"Pourquoi cette alerte sur ce bon : « {alerte.message} » ? Que dois-je faire ?" if alerte
              else "Explique-moi comment l'outil a établi les lignes de matériel de ce bon.")
        q2 = "Comment pourrait-on rendre la facturation de ce genre de bon plus précise avec l'outil ?"
        historique = []
        for q in (q1, q2):
            try:
                rep = repondre(client, cfg["claude"], q, historique, regles_txt, contexte)
            except Exception as e:
                rep = f"ERREUR : {type(e).__name__} : {e}"
            historique.append({"question": q, "reponse": rep})
            ecrire(f"\n[{bon.code}] Hugo : {q}\nJarvis : {rep}")
        try:
            brouillon = rediger_recommandation(client, cfg["claude"], historique, regles_txt, contexte)
            ecrire(f"\nBrouillon de recommandation : {brouillon}")
        except Exception as e:
            ecrire(f"\nBrouillon de recommandation : ERREUR {type(e).__name__} : {e}")

    # ---------- 3. Google Maps et kilométrage ----------
    ecrire("\n=== 3. GOOGLE MAPS ET KILOMÉTRAGE ===")
    if not c.get("google"):
        ecrire("Clé Google absente : partie sautée.")
    else:
        from cartes import Cartes
        cartes = Cartes(c["google"], dossier / "cache-cartes-essai.json")
        try:
            bureau = cartes.geocoder("J4W 3J9")   # code postal du bureau (Brossard)
            ecrire(f"Géocodage (Geocoding API) : OK {bureau}")
            if bureau:
                autre = cartes.geocoder("H2X 1Y4")   # centre-ville de Montréal
                ecrire(f"Distance bureau -> centre-ville (Routes API) : {cartes.distance_km(bureau, autre):.1f} km")
        except Exception as e:
            ecrire(f"Google Maps : ERREUR {type(e).__name__} : {e}")
        techniciens = profil.lire_techniciens()
        avec_code = [n for n, t in techniciens.items() if (t or {}).get("code_postal")]
        ecrire(f"Techniciens avec code postal dans ce profil Windows : {len(avec_code)}")
        if avec_code:
            try:
                from interface import Application
                app = Application(ICI, demo=False, personne="essai")
                periodes = app.km_periodes()["periodes"]
                debut = periodes[1]["debut"]   # la dernière période complète
                app.km_calculer(debut)
                while app.km_progres.get("en_cours"):
                    time.sleep(1)
                ecrire(f"Période du {debut} : {app.km_progres.get('message')}")
                periode = app.km_periode(debut)["periode"] or {}
                for tot in periode.get("techniciens") or []:
                    ecrire(f"  - {tot['nom']} : à payer {tot['km_a_payer']} km · déclaré {tot['km_declare']} km · "
                           f"écart {tot['ecart']} · {tot['statut']}")
            except Exception as e:
                ecrire(f"Kilométrage : ERREUR {type(e).__name__} : {e}")
        else:
            ecrire("Aucun code postal inscrit sur ce poste : calcul de période sauté (à faire sur le poste d'Hugo).")

    # ---------- Résumé ----------
    ecrire("\n=== RÉSUMÉ ===")
    ecrire(f"Durée : {(time.time() - debut_essai) / 60:.1f} min · appels à Claude : {client.appels} · "
           f"jetons {client.jetons}")
    ecrire(f"Coût estimé de l'essai (Claude) : {argent(client.cout())}"
           + (f" · environ {argent(client.cout() / len(resultats))} par bon analysé et questions" if resultats else ""))
    fichier = dossier / f"rapport-essai-{datetime.now():%Y-%m-%d-%H%M}.txt"
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"\nRapport enregistré : {fichier}")
    print("Tu peux fermer cette fenêtre et prévenir Claude : il lira le rapport sur SharePoint.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        (ICI / "essais").mkdir(exist_ok=True)
        (ICI / "essais" / f"erreur-essai-{datetime.now():%Y-%m-%d-%H%M}.txt").write_text(traceback.format_exc(),
                                                                                         encoding="utf-8")
