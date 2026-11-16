"""Export Excel (.xlsx) minimal écrit avec la bibliothèque standard, sans dépendance.

`export_periode` reproduit la feuille de temps hebdomadaire envoyée à la paie, avec les km à payer.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape

from regles import cents, montant_km

_JOURS = ["Dim.", "Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam."]
# Caractères de contrôle refusés par Excel (tout sauf tabulation, saut de ligne et retour chariot).
_ILLEGAL = re.compile("[" + "".join(chr(i) for i in range(32) if i not in (9, 10, 13)) + "]")


class Gras:
    """Valeur (texte ou nombre) affichée en gras."""

    def __init__(self, valeur):
        self.valeur = valeur


def h_mm(minutes: float) -> str:
    total = int(round(minutes or 0))
    return f"{total // 60}:{total % 60:02d}"


def _lettre(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cellule(ref: str, v) -> str:
    gras = isinstance(v, Gras)
    if gras:
        v = v.valeur
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        v = "Oui" if v else "Non"
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{' s="1"' if gras else ""}><v>{v!r}</v></c>'
    style = ' s="1"' if gras else ""
    texte = escape(_ILLEGAL.sub("", str(v)))
    return f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{texte}</t></is></c>'


def _feuille_xml(lignes: list[list]) -> str:
    rangs = []
    for n, ligne in enumerate(lignes, 1):
        cellules = "".join(_cellule(f"{_lettre(i)}{n}", v) for i, v in enumerate(ligne))
        rangs.append(f'<row r="{n}">{cellules}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<cols><col min="1" max="1" width="26" customWidth="1"/>'
            '<col min="2" max="11" width="14" customWidth="1"/></cols>'
            f'<sheetData>{"".join(rangs)}</sheetData></worksheet>')


def _nom_feuille(nom: str, utilises: set[str]) -> str:
    nom = re.sub(r"[\[\]:*?/\\]", " ", nom)[:31] or "Feuille"
    base, k = nom, 2
    while nom.lower() in utilises:
        suffixe = f" ({k})"
        nom = base[:31 - len(suffixe)] + suffixe
        k += 1
    utilises.add(nom.lower())
    return nom


def ecrire_xlsx(feuilles: dict[str, list[list]]) -> bytes:
    utilises: set[str] = set()
    noms = [_nom_feuille(n, utilises) for n in feuilles]
    n = len(noms)
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, n + 1))
          + '<Override PartName="/xl/styles.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/></Relationships>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                + "".join(f'<sheet name="{escape(nom, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                          for i, nom in enumerate(noms, 1))
                + '</sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                         f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
               + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
               'relationships/styles" Target="styles.xml"/></Relationships>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill>'
              '<fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
              '</styleSheet>')
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        for i, lignes in enumerate(feuilles.values(), 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _feuille_xml(lignes))
    return tampon.getvalue()


def _entier_si_rond(x: float):
    return int(x) if float(x) == int(x) else round(x, 1)


def _semaine(periode: dict, dimanche: date, premiere: bool) -> list[list]:
    """Une semaine; montant de la semaine 1 arrondi, semaine 2 = montant validé de la période - semaine 1."""
    samedi = dimanche + timedelta(days=6)
    jours = [(dimanche + timedelta(days=i)).isoformat() for i in range(7)]
    taux = periode.get("taux") or 0
    if periode.get("statut") == "valide":
        statut = ["Statut : validé", f"Validé par : {periode.get('valide_par') or ''}",
                  f"Le : {periode.get('valide_le') or ''}"]
    else:
        statut = ["Statut : brouillon"]
    lignes: list[list] = [[Gras(f"Semaine du {dimanche.isoformat()} - {samedi.isoformat()}")], statut,
                          [Gras(t) for t in ["Ressource humaine"] + _JOURS + ["Total", "Km à payer", "Montant km ($)"]]]
    tot_min = [0.0] * 7
    tot_km = tot_montant = 0.0
    for t in periode.get("techniciens", []):
        if not t.get("paie") or t.get("statut") in ("sous_traitant", "a_configurer", "recalcul_requis"):
            continue
        par_jour = t.get("minutes_par_jour") or {}
        minutes = [float(par_jour.get(j, 0)) for j in jours]
        km = round(sum(d.get("km_paye", 0.0) for d in t.get("details", []) if d.get("jour") in jours), 1)
        if premiere:
            montant = montant_km(km, taux)
        else:
            jours1 = {(dimanche - timedelta(days=7 - i)).isoformat() for i in range(7)}
            km1 = round(sum(d.get("km_paye", 0.0) for d in t.get("details", []) if d.get("jour") in jours1), 1)
            montant = cents((t.get("montant") or 0) - montant_km(km1, taux))
        lignes.append([t["nom"]] + [h_mm(m) for m in minutes] + [h_mm(sum(minutes)), _entier_si_rond(km), montant])
        tot_min = [a + b for a, b in zip(tot_min, minutes)]
        tot_km += km
        tot_montant += montant
    lignes.append([Gras("Total")] + [Gras(h_mm(m)) for m in tot_min]
                  + [Gras(h_mm(sum(tot_min))), Gras(_entier_si_rond(round(tot_km, 1))), Gras(cents(tot_montant))])
    return lignes


def _detail(periode: dict) -> list[list]:
    lignes: list[list] = [[Gras(t) for t in ["Technicien", "Jour", "Trajet", "Km calculé", "Uhaul", "Km magasin",
                                             "Km payé", "À vérifier"]]]
    for t in periode.get("techniciens", []):
        if not t.get("paie"):
            continue
        for d in t.get("details", []):
            lignes.append([t["nom"], d.get("jour"), " → ".join(a.get("code") or "" for a in d.get("arrets", [])),
                           d.get("km", 0.0), "Oui" if d.get("uhaul") else "", d.get("magasin_km", 0.0),
                           d.get("km_paye", 0.0), " ; ".join(d.get("a_verifier", []))])
    return lignes


def export_periode(periode: dict) -> tuple[bytes, str]:
    debut, fin = periode["debut"], periode["fin"]
    d1 = date.fromisoformat(debut)
    d2 = d1 + timedelta(days=7)
    feuilles = {f"Semaine du {d.isoformat()}": _semaine(periode, d, d is d1) for d in (d1, d2)}
    feuilles["Détail"] = _detail(periode)
    rev = periode.get("revision")
    nom = f"Feuille de temps et km {debut} au {fin}{' (revise ' + str(rev) + ')' if rev else ''}.xlsx"
    return ecrire_xlsx(feuilles), nom
