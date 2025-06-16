# app/firebase.py
import firebase_admin
from firebase_admin import credentials

# point this at the JSON you downloaded
cred = credentials.Certificate("firebase_credentials.json")
default_app = firebase_admin.initialize_app(cred)
