"""
Bot d'alerte logement CROUS -> Telegram (version Render + cron-job.org)
=========================================================================

Ce script expose une petite page web (/check). Chaque fois que cette page
est appelée (par cron-job.org, toutes les 5 minutes), le script vérifie
les logements CROUS et envoie une alerte Telegram si un nouveau est trouvé.

Configuration : via variables d'environnement, définies dans le tableau de
bord Render (Environment), jamais dans ce fichier.
"""

from flask import Flask
import requests
from bs4 import BeautifulSoup
import json
import os

app = Flask(__name__)

SEARCH_URL = os.environ.get("CROUS_SEARCH_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SEEN_FILE = "logements_deja_vus.json"


def envoyer_message_telegram(texte):
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


@app.route("/")
def accueil():
    # Route utilisée par Render pour vérifier que le service est en vie
    return "Bot CROUS en ligne. Utilise /check pour lancer une vérification."


@app.route("/check")
def check():
    if not SEARCH_URL or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return "ERREUR : variable d'environnement manquante.", 500

    ids_deja_vus = set(charger_logements_vus())
    premiere_execution = len(ids_deja_vus) == 0

    logements = recuperer_logements()

    if not logements:
        return "Aucun logement récupéré ce cycle (page vide, file d'attente, ou erreur)."

    nouveaux = [l for l in logements if l["id"] not in ids_deja_vus]

    if premiere_execution:
        envoyer_message_telegram(
            f"✅ Bot CROUS activé (Render). {len(logements)} logements actuellement en ligne "
            f"sont pris comme référence. Tu seras alerté des nouveautés."
        )
        message_reponse = f"Premier scan : {len(logements)} logements enregistrés comme référence."
    elif nouveaux:
        for l in nouveaux:
            message = f"🏠 <b>Nouveau logement disponible !</b>\n{l['nom']}\n{l['url']}"
            envoyer_message_telegram(message)
        message_reponse = f"{len(nouveaux)} nouveau(x) logement(s) trouvé(s) et notifié(s)."
    else:
        message_reponse = "Aucun nouveau logement à ce cycle."

    ids_deja_vus.update(l["id"] for l in logements)
    sauvegarder_logements_vus(list(ids_deja_vus))

    return message_reponse


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
