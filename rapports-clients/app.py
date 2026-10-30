"""Fenêtre de l'outil d'envoi des rapports clients, lancée par « Rapports clients.bat »."""

import json
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from envoi_rapports import ICI, MOIS_FR, outlook_configure, preparer

PARAMETRES = ICI / "parametres.json"
# Charte Progim (même look que l'outil de facturation de services).
MARINE, ORANGE, FOND, BLANC, LIGNE = "#131A2F", "#EE7203", "#F3F4F6", "#FFFFFF", "#DDE2E6"
VERT, ROUGE, GRIS, PALE = "#2D7A3E", "#B4471A", "#5B6770", "#AEB6C8"
POLICE = "Segoe UI"


def lire_parametres() -> dict:
    try:
        return json.loads(PARAMETRES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_parametres(valeurs: dict) -> None:
    PARAMETRES.write_text(json.dumps(valeurs, ensure_ascii=False, indent=2), encoding="utf-8")


def ouvrir(chemin: Path) -> None:
    if sys.platform == "win32":
        os.startfile(chemin)  # noqa: S606 — ouvre avec l'application par défaut de Windows
    elif sys.platform == "darwin":
        subprocess.run(["open", str(chemin)], check=False)
    else:
        webbrowser.open(chemin.as_uri())


def pluriel(nombre: int, singulier: str, pluriel_: str) -> str:
    return f"{nombre} {singulier if nombre <= 1 else pluriel_}"


def mois_recents(nombre: int = 6) -> list[tuple[str, str]]:
    """(AAAA-MM, libellé) des derniers mois, le plus récent mois terminé en premier."""
    annee, mois = date.today().year, date.today().month
    resultat = []
    for _ in range(nombre):
        mois -= 1
        if mois == 0:
            annee, mois = annee - 1, 12
        resultat.append((f"{annee}-{mois:02d}", f"{MOIS_FR[mois - 1].capitalize()} {annee}"))
    return resultat


def trouver_dossier_du_mois(racine: str, mois: str) -> str:
    """Dans 1_CLIENTS, trouve le sous-dossier du mois, par exemple « 09-septembre 2026 »."""
    racine_ = Path(racine)
    if not racine_.is_dir():
        return ""
    for dossier in sorted(racine_.iterdir()):
        if dossier.is_dir() and re.match(rf"^0?{int(mois[5:])}\D", dossier.name) and mois[:4] in dossier.name:
            return str(dossier)
    return ""


class Application(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Rapports clients – Progim")
        self.geometry("760x560")
        self.minsize(640, 480)
        self.parametres = lire_parametres()
        self.dernier_rapport: Path | None = None
        self.mois_choix = mois_recents()

        self.var_mois = tk.StringVar(value=self.mois_choix[0][1])
        self.var_excel = tk.StringVar(value=self.parametres.get("excel", str(ICI / "clients_rapports.xlsx")))
        self.var_racine = tk.StringVar(value=self.parametres.get("racine", ""))
        self.var_dossier = tk.StringVar()
        self.construire()
        self.var_mois.trace_add("write", lambda *_: self.deviner_dossier())
        self.deviner_dossier()

    # Mise en page -----------------------------------------------------------
    def construire(self) -> None:
        self.configure(background=FOND)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=FOND, foreground=MARINE, font=(POLICE, 10))
        style.configure("TLabel", background=FOND, foreground=MARINE)
        style.configure("TFrame", background=FOND)
        style.configure("TEntry", fieldbackground=BLANC, bordercolor=LIGNE, padding=4)
        style.configure("TCombobox", fieldbackground=BLANC, bordercolor=LIGNE, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", BLANC)])
        style.configure("Etape.TLabel", font=(POLICE, 9, "bold"), foreground=ORANGE)

        # Bandeau blanc avec le logo Progim et un filet orange, comme le rapport de contrôle
        bandeau = tk.Frame(self, background=BLANC, padx=20, pady=10)
        bandeau.pack(fill="x")
        logo_fichier = ICI / "logo_progim.png"
        if logo_fichier.exists():
            self.logo = tk.PhotoImage(file=str(logo_fichier)).subsample(3, 3)
            tk.Label(bandeau, image=self.logo, background=BLANC).pack(side="left", padx=(0, 14))
        tk.Frame(bandeau, background=LIGNE, width=1).pack(side="left", fill="y", padx=(0, 14))
        titres = tk.Frame(bandeau, background=BLANC)
        titres.pack(side="left")
        tk.Label(titres, text="Rapports clients", background=BLANC, foreground=MARINE,
                 font=(POLICE, 13, "bold")).pack(anchor="w")
        tk.Label(titres, text="Finance", background=BLANC, foreground=GRIS, font=(POLICE, 9)).pack(anchor="w")
        tk.Frame(self, background=ORANGE, height=3).pack(fill="x")

        cadre = ttk.Frame(self, padding=(20, 14, 20, 16))
        cadre.pack(fill="both", expand=True)
        cadre.columnconfigure(1, weight=1)

        ttk.Label(cadre, text="Rien n'est envoyé aux clients sans que vous cliquiez sur Envoyer dans Outlook.",
                  foreground=GRIS).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(cadre, text="Mois des rapports").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))
        ttk.Combobox(cadre, textvariable=self.var_mois, values=[libelle for _, libelle in self.mois_choix],
                     state="readonly", width=20).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(cadre, text="Dossier des rapports Hopem").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 10))
        ttk.Entry(cadre, textvariable=self.var_dossier).grid(row=3, column=1, sticky="ew", pady=4, padx=(0, 6))
        self.bouton(cadre, "Choisir…", self.choisir_dossier, "secondaire").grid(row=3, column=2, pady=4)

        ttk.Label(cadre, text="Excel des clients").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 10))
        ttk.Entry(cadre, textvariable=self.var_excel).grid(row=4, column=1, sticky="ew", pady=4, padx=(0, 6))
        self.bouton(cadre, "Choisir…", self.choisir_excel, "secondaire").grid(row=4, column=2, pady=4)

        etapes = ttk.Frame(cadre)
        etapes.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(16, 8))
        etapes.columnconfigure((0, 1, 2), weight=1, uniform="etape")
        self.boutons = []
        for colonne, (titre, texte, action, genre) in enumerate([
            ("ÉTAPE 1", "Voir les périodes\nà extraire de Hopem", self.etape_periodes, "secondaire"),
            ("ÉTAPE 2", "Vérifier les rapports\net préparer les courriels", self.etape_verifier, "principal"),
            ("ÉTAPE 3", "Créer les brouillons\ndans Outlook", self.etape_brouillons, "marine"),
        ]):
            ttk.Label(etapes, text=titre, style="Etape.TLabel").grid(row=0, column=colonne, sticky="w", padx=4)
            bouton = self.bouton(etapes, texte, action, genre, gros=True)
            bouton.grid(row=1, column=colonne, sticky="ew", padx=4, pady=(2, 0))
            self.boutons.append(bouton)
        if not outlook_configure():
            self.boutons[2].configure(state="disabled")
            ttk.Label(etapes, text="Pas encore branché à Outlook", foreground=GRIS).grid(row=2, column=2, sticky="w", padx=4)

        self.resume = ttk.Label(cadre, text="", font=(POLICE, 11, "bold"))
        self.resume.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 4))

        self.journal = tk.Text(cadre, height=8, wrap="word", relief="flat", borderwidth=0, background=BLANC,
                               foreground=MARINE, highlightthickness=1, highlightbackground=LIGNE, font=(POLICE, 9), padx=8, pady=6)
        self.journal.grid(row=7, column=0, columnspan=3, sticky="nsew")
        self.journal.configure(state="disabled")
        cadre.rowconfigure(7, weight=1)

        bas = ttk.Frame(cadre)
        bas.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.bouton(bas, "Ouvrir le rapport de contrôle", self.ouvrir_rapport, "secondaire").pack(side="left")
        self.bouton(bas, "Ouvrir l'Excel des clients", lambda: self.ouvrir_si_existe(Path(self.var_excel.get())),
                    "secondaire").pack(side="left", padx=6)
        self.bouton(bas, "Ouvrir les aperçus de courriels", self.ouvrir_apercus, "secondaire").pack(side="left")

    def bouton(self, parent, texte: str, action, genre: str, gros: bool = False) -> tk.Button:
        """Bouton aux couleurs Progim : principal orange, marine, ou secondaire blanc bordé."""
        fond, texte_couleur, survol = {"principal": (ORANGE, BLANC, "#D96500"),
                                       "marine": (MARINE, BLANC, "#26304D"),
                                       "secondaire": (BLANC, MARINE, "#E8EBEF")}[genre]
        return tk.Button(parent, text=texte, command=action, background=fond, foreground=texte_couleur,
                         activebackground=survol, activeforeground=texte_couleur, disabledforeground=PALE,
                         relief="flat", borderwidth=0, highlightthickness=1 if genre == "secondaire" else 0,
                         highlightbackground=LIGNE, cursor="hand2",
                         font=(POLICE, 10, "bold" if gros else "normal"),
                         padx=12, pady=10 if gros else 5)

    # Choix des fichiers -----------------------------------------------------
    @property
    def mois(self) -> str:
        return next(code for code, libelle in self.mois_choix if libelle == self.var_mois.get())

    def deviner_dossier(self) -> None:
        trouve = trouver_dossier_du_mois(self.var_racine.get(), self.mois)
        self.var_dossier.set(trouve)

    def choisir_dossier(self) -> None:
        dossier = filedialog.askdirectory(title="Dossier des rapports Hopem du mois",
                                          initialdir=self.var_racine.get() or None)
        if dossier:
            self.var_dossier.set(dossier)
            # Le dossier parent (1_CLIENTS) sert à retrouver tout seul le dossier des mois suivants.
            self.var_racine.set(str(Path(dossier).parent))
            self.sauvegarder()

    def choisir_excel(self) -> None:
        fichier = filedialog.askopenfilename(title="Excel des clients", filetypes=[("Excel", "*.xlsx")])
        if fichier:
            self.var_excel.set(fichier)
            self.sauvegarder()

    def sauvegarder(self) -> None:
        try:
            ecrire_parametres({"excel": self.var_excel.get(), "racine": self.var_racine.get()})
        except OSError:
            pass

    # Étapes -----------------------------------------------------------------
    def etape_periodes(self) -> None:
        self.lancer("Liste des périodes", exports=None, mode="simulation")

    def etape_verifier(self) -> None:
        if not self.verifier_dossier():
            return
        self.lancer("Vérification", exports=Path(self.var_dossier.get()), mode="simulation")

    def etape_brouillons(self) -> None:
        if not self.verifier_dossier():
            return
        if messagebox.askyesno("Créer les brouillons",
                               "Créer les brouillons dans la boîte finance@ pour tous les courriels prêts?\n\n"
                               "Rien ne sera envoyé : chaque brouillon devra être révisé et envoyé dans Outlook."):
            self.lancer("Création des brouillons", exports=Path(self.var_dossier.get()), mode="brouillons")

    def verifier_dossier(self) -> bool:
        if not Path(self.var_dossier.get()).is_dir():
            messagebox.showwarning("Dossier manquant", "Choisissez le dossier où les rapports Hopem du mois ont été téléchargés.")
            return False
        return True

    def lancer(self, nom: str, exports: Path | None, mode: str) -> None:
        excel = Path(self.var_excel.get())
        if not excel.is_file():
            messagebox.showwarning("Excel introuvable", f"L'Excel des clients est introuvable :\n{excel}")
            return
        self.sauvegarder()
        for bouton in self.boutons:
            bouton.configure(state="disabled")
        self.resume.configure(text=f"{nom} en cours…", foreground=GRIS)
        self.ecrire(f"{nom} – {self.var_mois.get()}…")
        mois = self.mois

        def travail() -> None:
            try:
                resultat = preparer(mois, excel, exports, mode, completer=exports is not None)
                self.after(0, self.terminer, nom, exports, resultat, None)
            except PermissionError:
                self.after(0, self.terminer, nom, exports, None,
                           "Un fichier est ouvert ailleurs (probablement l'Excel des clients). Fermez-le et recommencez.")
            except Exception as erreur:  # affiché à l'employé plutôt que de fermer la fenêtre
                self.after(0, self.terminer, nom, exports, None, str(erreur))

        threading.Thread(target=travail, daemon=True).start()

    def terminer(self, nom, exports, resultat, erreur) -> None:
        for bouton in self.boutons[:2]:
            bouton.configure(state="normal")
        if outlook_configure():
            self.boutons[2].configure(state="normal")
        if erreur:
            self.resume.configure(text=f"{nom} : erreur", foreground=ROUGE)
            self.ecrire(f"Erreur : {erreur}")
            messagebox.showerror(nom, erreur)
            return
        self.dernier_rapport = resultat.rapport
        if exports is None:
            self.resume.configure(text="Liste des périodes prête.", foreground=VERT)
        else:
            couleur = VERT if resultat.bloques == 0 else ROUGE
            self.resume.configure(text=f"{pluriel(resultat.prets, 'courriel prêt', 'courriels prêts')} · "
                                       f"{pluriel(resultat.bloques, 'bloqué', 'bloqués')} · "
                                       f"{pluriel(resultat.alertes, 'fichier à regarder', 'fichiers à regarder')}",
                                  foreground=couleur)
        self.ecrire(f"{nom} terminée. Rapport : {resultat.rapport}")
        if resultat.complete:
            self.ecrire(f"Noms lus dans les PDF ajoutés dans une copie de l'Excel, à réviser : {resultat.complete}")
        ouvrir(resultat.rapport)

    # Utilitaires --------------------------------------------------------------
    def ecrire(self, texte: str) -> None:
        self.journal.configure(state="normal")
        self.journal.insert("end", texte + "\n")
        self.journal.see("end")
        self.journal.configure(state="disabled")

    def ouvrir_si_existe(self, chemin: Path) -> None:
        if chemin.exists():
            ouvrir(chemin)
        else:
            messagebox.showinfo("Introuvable", f"Rien à ouvrir pour l'instant :\n{chemin}")

    def ouvrir_rapport(self) -> None:
        self.ouvrir_si_existe(self.dernier_rapport or ICI / "sortie" / self.mois / "rapport.html")

    def ouvrir_apercus(self) -> None:
        self.ouvrir_si_existe(ICI / "sortie" / self.mois / "apercus")


if __name__ == "__main__":
    Application().mainloop()
