# ============================================================================
#  Progim - Rapports clients : creation des brouillons dans Outlook (classique)
#
#  Repris de l'outil de facturation (meme methode, deja eprouvee avec la boite
#  Finance). Appele par envoi_rapports.py avec un fichier JSON (manifeste) qui
#  decrit les courriels : destinataires, copie, objet, corps HTML, pieces.
#  Cree les brouillons dans la boite partagee finance@. N'ENVOIE RIEN.
#
#  Sortie : une ligne par resultat, prefixee OK| / AVERT| / ERREUR|
# ============================================================================

param([Parameter(Mandatory = $true)][string]$Manifeste)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$m = Get-Content -LiteralPath $Manifeste -Raw -Encoding UTF8 | ConvertFrom-Json

# Outlook classique doit etre OUVERT pendant et apres la creation : s'il est seulement demarre
# en arriere-plan, il peut se refermer avant d'avoir envoye les brouillons vers le serveur.
$dejaOuvert = [bool](Get-Process OUTLOOK -ErrorAction SilentlyContinue)
if (-not $dejaOuvert) {
    try {
        Start-Process "outlook.exe"
        Write-Output "AVERT|Outlook classique n'était pas ouvert : il vient d'être ouvert. Laissez-le ouvert jusqu'à la fin."
        for ($i = 0; $i -lt 60 -and -not (Get-Process OUTLOOK -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 1 }
        Start-Sleep -Seconds 12          # le temps qu'Outlook charge le profil et les boites
    } catch {
        Write-Output "ERREUR|Outlook (version classique) est introuvable sur ce poste."
        exit 1
    }
}
try {
    $outlook = New-Object -ComObject Outlook.Application
} catch {
    Write-Output "ERREUR|Outlook (version classique) est introuvable sur ce poste."
    exit 1
}
$ns = $outlook.GetNamespace("MAPI")

# Adresse du proprietaire d'une boite d'Outlook (ex. finance@progim.com) : le nom affiche ne suffit pas.
function Get-AdresseBoite($store) {
    try {
        $id = $store.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x661B0102")  # PR_MAILBOX_OWNER_ENTRYID
        $hex = [BitConverter]::ToString($id).Replace("-", "")
        return [string]$ns.GetAddressEntryFromID($hex).GetExchangeUser().PrimarySmtpAddress
    } catch { return "" }
}

# Dossier Brouillons de la boite dont l'ADRESSE est l'expediteur, sinon ouverte directement par cette adresse.
$brouillons = $null
foreach ($store in $ns.Stores) {
    if ((Get-AdresseBoite $store) -eq $m.expediteur) {
        try { $brouillons = $store.GetDefaultFolder(16) } catch { }   # 16 = olFolderDrafts
        if ($brouillons) { break }
    }
}
if (-not $brouillons) {
    try {
        $dest = $ns.CreateRecipient($m.expediteur)
        if ($dest.Resolve()) { $brouillons = $ns.GetSharedDefaultFolder($dest, 16) }
    } catch { }
}
if (-not $brouillons) {
    # On ne cree RIEN ailleurs : des brouillons dans la mauvaise boite passent inapercus.
    Write-Output "ERREUR|La boîte $($m.expediteur) est introuvable dans Outlook classique sur ce poste. Ajoutez-la (Fichier > Paramètres du compte > Modifier > Paramètres supplémentaires > Avancé > Ouvrir ces boîtes aux lettres), puis recommencez. Aucun brouillon n'a été créé."
    exit 1
}
Write-Output ("OK|Boîte de destination : {0}" -f $brouillons.FolderPath)
try {
    if ($brouillons.Store.IsCachedExchange) {
        Write-Output "AVERT|Sur ce poste, Outlook garde une copie locale de la boîte Finance : les brouillons n'apparaîtront chez vos collègues qu'après la synchronisation (laisser Outlook classique ouvert jusqu'à « Tous les dossiers sont à jour »)."
    }
} catch { }

$nbErreurs = 0
foreach ($c in $m.courriels) {
    try {
        $mail = $brouillons.Items.Add(0)                     # 0 = olMailItem
        $mail.SentOnBehalfOfName = $m.expediteur
        if ($c.a) { $mail.To = $c.a }
        if ($c.cc) { $mail.CC = $c.cc }
        $mail.Subject = $c.objet
        $mail.HTMLBody = $c.html
        # Logo de la signature, en image integree (cid) et masquee de la liste des pieces jointes
        if ($m.logo -and (Test-Path -LiteralPath $m.logo)) {
            $logo = $mail.Attachments.Add($m.logo, 1, 0, "logo")
            $logo.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x3712001F", $m.logo_cid)  # Content-ID
            $logo.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x7FFE000B", $true)        # masquee
        }
        foreach ($p in $c.pieces) { $null = $mail.Attachments.Add($p) }
        $mail.Save()
        # Outlook enregistre souvent le brouillon dans la boite PRINCIPALE : on le deplace au bon endroit.
        if ($mail.Parent.EntryID -ne $brouillons.EntryID) {
            $mail = $mail.Move($brouillons)
        }
        Write-Output ("OK|{0} : brouillon créé ({1} pièce(s) jointe(s)) -> {2}" -f $c.nom, $c.pieces.Count, $c.a)
        Write-Output ("CREE|{0}" -f $c.code)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mail) | Out-Null
    } catch {
        $nbErreurs++
        Write-Output ("ERREUR|{0} : {1}" -f $c.nom, $_.Exception.Message)
    }
}
# Envoi vers le serveur, puis verification : les brouillons sont-ils bien dans la boite ?
try { $ns.SendAndReceive($false) } catch { }
Start-Sleep -Seconds 8
$objets = @($m.courriels | ForEach-Object { $_.objet } | Select-Object -Unique)
$trouves = @($brouillons.Items | Where-Object { $objets -contains $_.Subject }).Count
Write-Output ("OK|Vérification : {0} brouillon(s) de ce mois présents dans {1}" -f $trouves, $brouillons.FolderPath)
if ($trouves -lt ($m.courriels.Count - $nbErreurs)) {
    Write-Output "AVERT|Moins de brouillons que prévu dans la boîte : laissez Outlook classique ouvert quelques minutes, puis vérifiez Finance > Brouillons."
}
if (-not $dejaOuvert) {
    Write-Output "AVERT|Laissez Outlook classique ouvert 1 à 2 minutes, le temps que les brouillons arrivent dans la boîte Finance du serveur."
}
if ($nbErreurs -gt 0) { exit 1 }
exit 0
