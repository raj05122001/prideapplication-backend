from fastapi import APIRouter, HTTPException, Depends
from datetime import date
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import UserDetails, PushToken

import os
import json
import time
import asyncio
import concurrent.futures
from typing import List, Dict, Any
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, messaging

class FCMBatchSender:
    def __init__(self):
        self.initialize_firebase()
    
    def initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        if not firebase_admin._apps:
            load_dotenv()
            service_account_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')
            if service_account_key:
                key_data = json.loads(service_account_key)
                cred = credentials.Certificate(key_data)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized")
            else:
                raise Exception("❌ No Firebase credentials found")
    
    def send_individual_batch(self, tokens: List[str], title: str, body: str, 
                            data: Dict[str, Any] = None, max_workers: int = 5) -> Dict:
        """
        Send notifications to multiple devices using individual sends with threading
        This is a workaround when batch operations fail
        """
        print(f"🚀 Sending notifications to {len(tokens)} devices...")
        
        results = {
            'success_count': 0,
            'failure_count': 0,
            'responses': [],
            'successful_tokens': [],
            'failed_tokens': []
        }
        
        def send_single_notification(token: str, index: int) -> Dict:
            """Send notification to a single token"""
            try:
                message = messaging.Message(
                    token=token,
                    notification=messaging.Notification(
                        title=title,
                        body=body
                    ),
                    data=data or {},
                    android=messaging.AndroidConfig(
                        notification=messaging.AndroidNotification(
                            title=title,
                            body=body,
                            sound='default',
                            priority="high",
                            default_sound=True,
                            default_vibrate_timings=True,
                            default_light_settings=True
                        ),
                        priority="high"
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                alert=messaging.ApsAlert(
                                    title=title,
                                    body=body
                                ),
                                badge=1,
                                sound="default"
                            )
                        ),
                        headers={"apns-priority": "10"}
                    )
                )
                
                response = messaging.send(message)
                return {
                    'success': True,
                    'token': token,
                    'index': index,
                    'message_id': response,
                    'error': None
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'token': token,
                    'index': index,
                    'message_id': None,
                    'error': str(e)
                }
        
        # Use ThreadPoolExecutor for concurrent sends
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_token = {
                executor.submit(send_single_notification, token, i): (token, i) 
                for i, token in enumerate(tokens)
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_token):
                result = future.result()
                results['responses'].append(result)
                
                if result['success']:
                    results['success_count'] += 1
                    results['successful_tokens'].append(result['token'])
                    print(f"   ✅ Token {result['index'] + 1}: {result['message_id']}")
                else:
                    results['failure_count'] += 1
                    results['failed_tokens'].append(result['token'])
                    print(f"   ❌ Token {result['index'] + 1}: {result['error']}")
        
        return results
    
    def send_personalized_batch(self, token_messages: List[Dict], max_workers: int = 5) -> Dict:
        """
        Send different messages to different tokens using threading
        token_messages format: [{'token': 'xxx', 'title': 'xxx', 'body': 'xxx', 'data': {}}]
        """
        print(f"📤 Sending personalized notifications to {len(token_messages)} devices...")
        
        results = {
            'success_count': 0,
            'failure_count': 0,
            'responses': []
        }
        
        def send_personalized_notification(token_msg: Dict, index: int) -> Dict:
            """Send personalized notification"""
            try:
                message = messaging.Message(
                    token=token_msg['token'],
                    notification=messaging.Notification(
                        title=token_msg['title'],
                        body=token_msg['body']
                    ),
                    data=token_msg.get('data', {}),
                    android=messaging.AndroidConfig(
                        notification=messaging.AndroidNotification(
                            title=token_msg['title'],
                            body=token_msg['body'],
                            sound='default',
                            priority="high"
                        ),
                        priority="high"
                    )
                )
                
                response = messaging.send(message)
                return {
                    'success': True,
                    'index': index,
                    'message_id': response,
                    'error': None
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'index': index,
                    'message_id': None,
                    'error': str(e)
                }
        
        # Use ThreadPoolExecutor for concurrent sends
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(send_personalized_notification, token_msg, i): i 
                for i, token_msg in enumerate(token_messages)
            }
            
            for future in concurrent.futures.as_completed(future_to_index):
                result = future.result()
                results['responses'].append(result)
                
                if result['success']:
                    results['success_count'] += 1
                    print(f"   ✅ Message {result['index'] + 1}: {result['message_id']}")
                else:
                    results['failure_count'] += 1
                    print(f"   ❌ Message {result['index'] + 1}: {result['error']}")
        
        return results


# Pydantic model for incoming request
class PushNotification(BaseModel):
    msg_title: str
    msg_body: str
    service: str

router = APIRouter(
    prefix="/notification",
    tags=["notification"],
)

# Initialize Firebase Admin SDK once
FIREBASE_CRED_PATH = "service_account.json"  # update this path
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred)

@router.post("/send-notification")
def send_notification_to_all(
    req: PushNotification,
    db: Session = Depends(get_db)
):
    """
    Sends push notifications to all users of a specific service
    whose service_active_date is today or later.
    """
    # 1. Determine today's date
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')

    # 2. Fetch all eligible users
    users = (
        db.query(UserDetails)
        .filter(
            UserDetails.service == req.service,
            UserDetails.service_active_date >= today_str
        )
        .all()
    )
    if not users:
        raise HTTPException(status_code=404, detail="No active users found for this service.")

    # 3. Extract phone numbers for token lookup
    phone_numbers = [user.phone_number for user in users]

    # 4. Fetch their push tokens
    token_rows = (
        db.query(PushToken.token)
        .filter(PushToken.user_id.in_(phone_numbers))
        .all()
    )
    tokens = [row[0] for row in token_rows]
    if not tokens:
        raise HTTPException(status_code=404, detail="No push tokens found for these users.")

    sender = FCMBatchSender()

    results1 = sender.send_individual_batch(
        tokens=tokens,
        title=req.msg_title,
        body=req.msg_body,
        data={
            "test": "true",
            "method": "individual_batch",
            "timestamp": str(int(time.time()))
        }
    )

    # 6. Return summary
    return {
        "responses": results1
    }
