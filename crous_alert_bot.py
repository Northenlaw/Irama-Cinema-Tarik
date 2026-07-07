"""
Bot d'alerte logement CROUS -> Telegram (version GitHub Actions)
=================================================================

Contrairement à la version "ordinateur personnel", ce script ne tourne PAS
en boucle infinie : il fait UNE vérification puis s'arrête. C'est GitHub
Actions qui se charge de le relancer automatiquement toutes les X minutes
selon le fichier .github/workflows/crous-check.yml

La configuration (URL de recherche, token Telegram, chat_id) ne se met plus
directement dans ce fichier : elle est lue depuis des "secrets" GitHub,
pour ne jamais exposer ton token publiquement dans le code.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import sys

# ============ CONFIGURATION (lue depuis les variables d'environnement) ============

SEARCH_URL = os.environ.get("CROUS_SEARCH_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SEEN_FILE = "logements_deja_vus.json"

# ====================================================================================


def envoyer_message_telegram(texte):
    """Envoie un message via le bot Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texte,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code != 200:
            print(f"[Erreur Telegram] {r.status_code} : {r.text}")
    except Exception as e:
        print(f"[Erreur Telegram] {e}")


def recuperer_logements():
    """Récupère la liste des logements affichés sur la page de recherche."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resultats = []
    try:
        resp = requests.get(SEARCH_URL, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Erreur de connexion] {e}")
        return resultats

    if "trop nombreux" in resp.text.lower():
        print("⏳ Le site CROUS affiche 'Vous êtes trop nombreux !' (forte affluence).")
        return resultats

    soup = BeautifulSoup(resp.text, "html.parser")
    liens = soup.select("a[href*='/accommodations/']")

    vus_ids = set()
    for lien in liens:
        href = lien.get("href", "")
        if "/accommodations/" not in href:
            continue
        accommodation_id = href.rstrip("/").split("/")[-1]
        if accommodation_id in vus_ids:
            continue
        vus_ids.add(accommodation_id)

        nom = lien.get_text(strip=True) or "Logement CROUS"
        url_complete = href if href.startswith("http") else f"https://trouverunlogement.lescrous.fr{href}"

        resultats.append({
            "id": accommodation_id,
            "nom": nom,
            "url": url_complete,
        })

    return resultats


def charger_logements_vus():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def sauvegarder_logements_vus(liste_ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(liste_ids, f, ensure_ascii=False, indent=2)


def main():
    if not SEARCH_URL or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERREUR : il manque une variable de configuration "
              "(CROUS_SEARCH_URL, TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID).")
        sys.exit(1)

    ids_deja_vus = set(charger_logements_vus())
    premiere_execution = len(ids_deja_vus) == 0

    logements = recuperer_logements()

    if not logements:
        print("Aucun logement récupéré à ce cycle (page vide, file d'attente, ou erreur).")
        return

    nouveaux = [l for l in logements if l["id"] not in ids_deja_vus]

    if premiere_execution:
        print(f"Premier scan : {len(logements)} logements enregistrés comme référence.")
        envoyer_message_telegram(
            f"✅ Bot CROUS activé (cloud). {len(logements)} logements actuellement en ligne "
            f"sont pris comme référence. Tu seras alerté des nouveautés."
        )
    elif nouveaux:
        print(f"{len(nouveaux)} nouveau(x) logement(s) trouvé(s) !")
        for l in nouveaux:
            message = f"🏠 <b>Nouveau logement disponible !</b>\n{l['nom']}\n{l['url']}"
            envoyer_message_telegram(message)
    else:
        print("Aucun nouveau logement à ce cycle.")

    ids_deja_vus.update(l["id"] for l in logements)
    sauvegarder_logements_vus(list(ids_deja_vus))


if __name__ == "__main__":
    main()
