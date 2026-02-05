import json
import logging
import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

logger = logging.getLogger(__name__)


def _initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            info = json.loads(service_account_json)
            cred = credentials.Certificate(info)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized with service account JSON.")
            return
        except Exception as e:
            logger.error(f"Failed to initialize Firebase with service account JSON: {e}")
            raise

    # Fallback to application default credentials (GCP / Cloud Run)
    firebase_admin.initialize_app()
    logger.info("Firebase Admin initialized with application default credentials.")


def verify_firebase_token(id_token: str) -> dict:
    _initialize_firebase()
    try:
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=True)
        return decoded
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        raise
