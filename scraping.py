import requests
import yaml
import os
import sys
import sqlite3
import pickle
from datetime import datetime, timedelta

def read_config(file_path):
    """
    Lit le fichier de configuration YAML et renvoie les données.
    """
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def login(login_url, login_data):
    """
    Connectez-vous à login_url avec les identifiants fournis.
    Gère les redirections automatiquement.
    Retourne une session contenant les cookies de connexion.
    """

    # if file session.txt exist and is less than an hour old, restore session from it:
    if (os.path.exists("session.cache")):
        file_time = os.path.getmtime("session.cache")
        if (datetime.now() - datetime.fromtimestamp(file_time)).total_seconds() < 3600:
            with open("session.cache", 'rb') as file:
                session = requests.Session()
                session.cookies.update(pickle.load(file))
                return session

    session = requests.Session()
    response = session.post(login_url, data=login_data, allow_redirects=True)

    if response.status_code != 200:
        print(f"Erreur lors de la connexion : {response.status_code}")
        return None

    # write session to cache file
    with open("session.cache", 'wb') as file:
        pickle.dump(session.cookies, file)

    return session

def fetch_data(session, target_url_base, date):
    formatted_date = date.strftime("%Y-%m-%d")

    # create new_date == date + 1 day
    new_date = date + timedelta(days=1)
    formatted_new_date = new_date.strftime("%Y-%m-%d")

    target_url = f"{target_url_base}&start={formatted_date}&end={formatted_new_date}"
    try:
        response = session.get(target_url)
        response.raise_for_status()
        jsonData = response.json()

        return jsonData['response'][0]['pointsComptage']

    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des données pour {date} sur {target_url} : {e}")


# Utilisation des fonctions
config = read_config('configuration.yaml')
login_url = 'https://ista-webconso.fr/espace-client-v2/public/login.do?dispatch=login'
target_url_base = 'https://ista-webconso.fr/espace-client-v2/occupant/ficheLogement.do?dispatch=calculeConsommationChauffageRfcPourLogement'
login_data = {
    "user": "ista",
    "resolutionEcran": "2560x1440",
    "validationCGU": "test",
    "loginSave": "",
    "pwdSave": "",
    'login': config['ista_webconso']['login'],
    'pwd': config['ista_webconso']['pwd']
}

# open ista.sqlite or create it if not exist
if (os.path.exists("ista.sqlite")):
    conn = sqlite3.connect("ista.sqlite")
    cursor = conn.cursor()
else:
    conn = sqlite3.connect("ista.sqlite")
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE pointsComptage "+
        "(numeroPointComptage int primary key, numeroSerieRepartiteur int, codePiece text, libellePiece text, libelleTypeRepartiteur text, avecForfait int)"
    )
    cursor.execute(
        "CREATE TABLE consommationChauffage ("+
        "date int, numeroPointComptage int, bruteAvecPonderationDju real, bruteSansPonderationDju real, corrigeeAvecPonderationDju real, corrigeeSansPonderationDju real, "+
        "indexDernierJourPeriode real, bruteValeurDju real, corrigeeValeurDju real, PRIMARY KEY(date, numeroPointComptage))"
    )
    conn.commit()

# Get last date in table consommationChauffage
cursor = conn.cursor()
cursor.execute("SELECT MAX(date) FROM consommationChauffage")
last_date = cursor.fetchone()[0]
if last_date:
    # last_date is unix timestamp. add 86400 and convert it to datetime
    start_time = datetime.fromtimestamp(last_date) + timedelta(days=1)
    print(f"Will start scraping at {start_time.strftime('%Y-%m-%d')}")
else:
    start_time = datetime(2022, 11, 25)
    print(f"No data in database. Will start scraping at {start_time.strftime('%Y-%m-%d')}")

end_time = datetime.now() - timedelta(days=1)

# Connexion
session = login(login_url, login_data)

# Dictionnaire des pointsComptage déjà insérés
pointsComptageDone = {}

if not session:
    print("Erreur lors de la connexion")
    sys.exit(1)

# Récupération des données

# Loop from start_time to end_time
while start_time < end_time:
    datas = fetch_data(session, target_url_base, start_time)
    sommeConsommation = 0

    for data in datas:
        # add pointsComptage from data.metadata
        if data['metadata']['numeroPointComptage'] not in pointsComptageDone:
            if data['metadata']['avecForfait'] is True:
                avecForfait = 1
            else:
                avecForfait = 0
            cursor.execute(
                "INSERT OR IGNORE INTO pointsComptage VALUES (?, ?, ?, ?, ?, ?)",
                (data['metadata']['numeroPointComptage'], data['metadata']['numeroSerieRepartiteur'], data['metadata']['codePiece'], data['metadata']['libellePiece'], data['metadata']['libelleTypeRepartiteur'], avecForfait)
            )
            conn.commit()
            pointsComptageDone[data['metadata']['numeroPointComptage']] = True

        # skip if consommation.is_null
        if data['consommation']['is_null'] is True:
            continue

        cursor.execute(
            "INSERT INTO consommationChauffage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                start_time.timestamp(),
                data['metadata']['numeroPointComptage'],
                data['consommation']['consommationBrute']['avecPonderationDju'],
                data['consommation']['consommationBrute']['sansPonderationDju'],
                data['consommation']['consommationCorrigee']['avecPonderationDju'],
                data['consommation']['consommationCorrigee']['sansPonderationDju'],
                data['consommation']['indexDernierJourPeriode'],
                data['consommation']['consommationBrute']['valeurDju'],
                data['consommation']['consommationCorrigee']['valeurDju'],
            )
        )

        sommeConsommation += data['consommation']['consommationCorrigee']['sansPonderationDju']
        conn.commit()
    
    # Print infos
    print(f"{start_time.strftime('%Y-%m-%d')}: {len(datas):2d} points de Comptage ; sommeConsommation = {sommeConsommation:5.2f}")

    # iterate
    start_time += timedelta(days=1)

