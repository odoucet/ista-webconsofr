# ista-webconsofr
Grab data from ISTA webconso.fr website

Stores data in a sqlite database.

Usage: 
```
pip install -r requirements.txt
python3 scraping.py
```
* Will create a sqlite database if it does not exist.
* Will check last data in database and grab data from this date to today.

This repository also provides Grafana dashboard compatible with the implementation.
To launch on localhost:
```
docker compose up -d

Overview
---------

![Grafana overview](images/grafana.png)
