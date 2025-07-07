from dotenv import load_dotenv
import os
import logging
import json

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
REDIRECT_URL = os.getenv("REDIRECT_URL")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
NEWS_API = os.getenv("NEWS_API")
X_REPIDAPI_HOST = os.getenv("X_REPIDAPI_HOST")
X_REPIDAPI_KEY = os.getenv("X_REPIDAPI_KEY")
SMS_API_KEY = os.getenv("SMS_API_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = os.getenv("AWS_REGION")
PAN_API_KEY=os.getenv("PAN_API_KEY")
PAN_API_ID=os.getenv("PAN_API_ID")
PAN_TASK_ID_1=os.getenv("PAN_TASK_ID_1")
PAN_TASK_ID_2=os.getenv("PAN_TASK_ID_2")
MAIL_PASSWORD=os.getenv("SMTP_PASSWORD")


SMTP_SERVER=os.getenv("smtp_server")
SMTP_PORT=os.getenv("smtp_port")
SMTP_USER=os.getenv("smtp_user")
SMTP_PASSWORD=os.getenv("smtp_pass")

COM_SMTP_SERVER=os.getenv("com_smtp_server")
COM_SMTP_PORT=os.getenv("com_smtp_port")
COM_SMTP_USER=os.getenv("com_smtp_user")
COM_SMTP_PASSWORD=os.getenv("com_smtp_pass")

PRIDEBUZZ_ONESIGNAL_APP_ID=os.getenv("PRIDEBUZZ_ONESIGNAL_APP_ID")
PRIDEBUZZ_ONESIGNAL_API_KEY=os.getenv("PRIDEBUZZ_ONESIGNAL_API_KEY")

CASHFREE_APP_ID=os.getenv("CASHFREE_APP_ID")
CASHFREE_SECRET_KEY=os.getenv("CASHFREE_SECRET_KEY")
CASHFREE_PRODUCTION=os.getenv("CASHFREE_PRODUCTION")