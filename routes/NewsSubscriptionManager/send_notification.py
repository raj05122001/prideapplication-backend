from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from firebase_admin import messaging
from typing import List, Dict, Any
import firebase_admin
from firebase_admin import credentials
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import PushToken

import requests
import json

# Initialize Firebase (only do this once)
try:
    # Check if already initialized
    firebase_admin.get_app()
except ValueError:
    # If not initialized, initialize it
    cred = credentials.Certificate("firebase_credentials.json")
    default_app = firebase_admin.initialize_app(cred)

router = APIRouter(
    prefix="/notification",
    tags=["notification"],
)

class PushRequest(BaseModel):
    title: str
    body: str
    data: Dict[str, str] = {}  # FCM requires string values only

class NotificationResult(BaseModel):
    total_tokens: int
    successful_sends: int
    failed_sends: int
    failed_tokens: List[str] = []

@router.post("/send-notification", response_model=NotificationResult)
def send_notification_to_all(
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Sends push notifications to all registered users.
    """
    try:
        # Fetch all push tokens from database
        all_tokens = db.query(PushToken).all()
        
        if not all_tokens:
            raise HTTPException(
                status_code=404, 
                detail="No push tokens found in database"
            )
        
        successful_sends = 0
        failed_sends = 0
        failed_tokens = []
        
        # Send notification to each token
        for token_record in all_tokens:
            try:
                # Convert data values to strings for FCM
                fcm_data = {k: str(v) for k, v in req.data.items()} if req.data else {}
                
                # Build the message
                message = messaging.Message(
                    token=token_record.token,
                    notification=messaging.Notification(
                        title=req.title,
                        body=req.body
                    ),
                    data=fcm_data
                )
                
                # Send the message
                message_id = messaging.send(message)
                successful_sends += 1
                print(f"✅ Sent to {token_record.user_id}: {message_id}")
                
            except Exception as send_error:
                failed_sends += 1
                failed_tokens.append(token_record.user_id)
                print(f"❌ Failed to send to {token_record.user_id}: {str(send_error)}")
                
                # Optionally remove invalid tokens
                if "not-registered" in str(send_error).lower() or "invalid-registration-token" in str(send_error).lower():
                    print(f"🗑️ Removing invalid token for user {token_record.user_id}")
                    db.delete(token_record)
        
        # Commit any token deletions
        db.commit()
        
        return NotificationResult(
            total_tokens=len(all_tokens),
            successful_sends=successful_sends,
            failed_sends=failed_sends,
            failed_tokens=failed_tokens
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send notifications: {str(e)}")

@router.post("/send-notification-to-user")
def send_notification_to_specific_user(
    user_id: str,
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Sends push notification to a specific user.
    """
    try:
        # Find user's token
        user_token = db.query(PushToken).filter(PushToken.user_id == user_id).first()
        
        if not user_token:
            raise HTTPException(
                status_code=404, 
                detail=f"No push token found for user_id: {user_id}"
            )
        
        # Convert data values to strings for FCM
        fcm_data = {k: str(v) for k, v in req.data.items()} if req.data else {}
        
        # Build and send message
        message = messaging.Message(
            token=user_token.token,
            notification=messaging.Notification(
                title=req.title,
                body=req.body
            ),
            data=fcm_data
        )
        
        message_id = messaging.send(message)
        return {
            "message_id": message_id,
            "user_id": user_id,
            "status": "sent"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # If token is invalid, remove it
        if "not-registered" in str(e).lower() or "invalid-registration-token" in str(e).lower():
            if user_token:
                db.delete(user_token)
                db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")

@router.post("/send-notification-batch")
def send_notification_batch(
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Sends push notifications using FCM batch/multicast (more efficient for large lists).
    """
    try:
        # Fetch all push tokens
        all_tokens = db.query(PushToken).all()
        
        if not all_tokens:
            raise HTTPException(
                status_code=404, 
                detail="No push tokens found in database"
            )
        
        # Extract just the token strings
        registration_tokens = [token.token for token in all_tokens]
        
        # Convert data values to strings for FCM
        fcm_data = {k: str(v) for k, v in req.data.items()} if req.data else {}
        
        # Create multicast message
        multicast_message = messaging.MulticastMessage(
            tokens=registration_tokens,
            notification=messaging.Notification(
                title=req.title,
                body=req.body
            ),
            data=fcm_data
        )
        
        # Send to all tokens at once
        batch_response = messaging.send_multicast(multicast_message)
        
        # Process results and clean up invalid tokens
        failed_tokens = []
        for idx, response in enumerate(batch_response.responses):
            if not response.success:
                failed_user_id = all_tokens[idx].user_id
                failed_tokens.append(failed_user_id)
                
                # Remove invalid tokens
                error_code = response.exception.code if response.exception else ""
                if "NOT_FOUND" in error_code or "INVALID_ARGUMENT" in error_code:
                    db.delete(all_tokens[idx])
        
        db.commit()
        
        return {
            "total_tokens": len(registration_tokens),
            "successful_sends": batch_response.success_count,
            "failed_sends": batch_response.failure_count,
            "failed_tokens": failed_tokens
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send batch notifications: {str(e)}")

# Add this to your send_notification.py file

@router.post("/debug-token")
def debug_token_info(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to check token validity and project information
    """
    try:
        # Check if token exists in database
        db_token = db.query(PushToken).filter(PushToken.token == token).first()
        
        if not db_token:
            return {"error": "Token not found in database"}
        
        # Try to validate token with Firebase
        try:
            # Create a test message
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(
                    title="Debug Test",
                    body="This is a debug test message"
                ),
                dry_run=True  # Don't actually send, just validate
            )
            
            # This will validate the token without sending
            result = messaging.send(message, dry_run=True)
            
            return {
                "status": "valid",
                "token_exists_in_db": True,
                "user_id": db_token.user_id,
                "firebase_validation": "passed",
                "message_id": result
            }
            
        except Exception as firebase_error:
            return {
                "status": "invalid",
                "token_exists_in_db": True,
                "user_id": db_token.user_id,
                "firebase_validation": "failed",
                "firebase_error": str(firebase_error)
            }
            
    except Exception as e:
        return {"error": f"Debug failed: {str(e)}"}

@router.get("/project-info")
def get_project_info():
    """
    Get Firebase project information from backend
    """
    try:
        app = firebase_admin.get_app()
        return {
            "project_id": app.project_id,
            "status": "Firebase initialized successfully"
        }
    except Exception as e:
        return {"error": f"Firebase not initialized: {str(e)}"}


# Add this to your send_notification.py file

@router.post("/send-expo-notification")
def send_expo_notification_to_all(
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Send notifications using Expo Push Service (for development/testing)
    """
    try:
        # Fetch all push tokens
        all_tokens = db.query(PushToken).all()
        
        if not all_tokens:
            raise HTTPException(
                status_code=404, 
                detail="No push tokens found in database"
            )
        
        # Filter Expo tokens (they start with ExponentPushToken)
        expo_tokens = [
            token.token for token in all_tokens 
            if token.token.startswith('ExponentPushToken')
        ]
        
        if not expo_tokens:
            # Try Firebase if no Expo tokens
            return send_notification_to_all(req, db)
        
        # Prepare Expo push notification
        expo_messages = []
        for token in expo_tokens:
            message = {
                "to": token,
                "title": req.title,
                "body": req.body,
                "data": req.data,
                "sound": "default",
                "priority": "high"
            }
            expo_messages.append(message)
        
        # Send to Expo Push Service
        expo_response = requests.post(
            'https://exp.host/--/api/v2/push/send',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            json=expo_messages
        )
        
        if expo_response.status_code == 200:
            result = expo_response.json()
            successful_sends = len([r for r in result['data'] if r['status'] == 'ok'])
            failed_sends = len(expo_messages) - successful_sends
            
            return {
                "service": "expo",
                "total_tokens": len(expo_tokens),
                "successful_sends": successful_sends,
                "failed_sends": failed_sends,
                "expo_response": result
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Expo push service failed: {expo_response.text}"
            )
            
    except Exception as e:
        # Fallback to Firebase if Expo fails
        print(f"Expo notification failed: {str(e)}")
        print("Falling back to Firebase...")
        return send_notification_to_all(req, db)

# Update the main endpoint to auto-detect token type
@router.post("/send-notification-auto", response_model=NotificationResult)
def send_notification_auto_detect(
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Automatically detect token type and use appropriate service
    """
    try:
        # First try Expo tokens
        expo_result = send_expo_notification_to_all(req, db)
        if expo_result.get("service") == "expo":
            return expo_result
    except:
        pass
    
    # Fallback to Firebase
    return send_notification_to_all(req, db)

# Add this to your send_notification.py file

@router.post("/send-mock-notification")
def send_mock_notification_to_all(
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Mock notification endpoint for testing with Expo Go
    Returns notification data that the frontend can use to trigger local notifications
    """
    try:
        # Fetch all push tokens (including mock ones)
        all_tokens = db.query(PushToken).all()
        
        if not all_tokens:
            raise HTTPException(
                status_code=404, 
                detail="No push tokens found in database"
            )
        
        # Count mock vs real tokens
        mock_tokens = [token for token in all_tokens if 'mock-' in token.token]
        real_tokens = [token for token in all_tokens if 'mock-' not in token.token]
        
        print(f"📊 Found {len(mock_tokens)} mock tokens and {len(real_tokens)} real tokens")
        
        # For mock tokens, return the notification data for local delivery
        mock_responses = []
        for token_record in mock_tokens:
            mock_responses.append({
                "user_id": token_record.user_id,
                "token": token_record.token,
                "notification": {
                    "title": req.title,
                    "body": req.body,
                    "data": req.data
                },
                "delivery_method": "local_simulation"
            })
        
        # For real tokens, try actual push (will fail in Expo Go but that's expected)
        real_send_results = []
        for token_record in real_tokens:
            try:
                # Convert data values to strings for FCM
                fcm_data = {k: str(v) for k, v in req.data.items()} if req.data else {}
                
                # Build the message
                message = messaging.Message(
                    token=token_record.token,
                    notification=messaging.Notification(
                        title=req.title,
                        body=req.body
                    ),
                    data=fcm_data
                )
                
                # Send the message
                message_id = messaging.send(message)
                real_send_results.append({
                    "user_id": token_record.user_id,
                    "status": "sent",
                    "message_id": message_id,
                    "delivery_method": "firebase_push"
                })
                print(f"✅ Real push sent to {token_record.user_id}: {message_id}")
                
            except Exception as send_error:
                real_send_results.append({
                    "user_id": token_record.user_id,
                    "status": "failed",
                    "error": str(send_error),
                    "delivery_method": "firebase_push"
                })
                print(f"❌ Failed to send to {token_record.user_id}: {str(send_error)}")
        
        return {
            "status": "mixed_delivery",
            "total_tokens": len(all_tokens),
            "mock_simulations": len(mock_tokens),
            "real_pushes_attempted": len(real_tokens),
            "mock_responses": mock_responses,
            "real_results": real_send_results,
            "notification_data": {
                "title": req.title,
                "body": req.body,
                "data": req.data
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process notifications: {str(e)}")

@router.post("/trigger-local-notification")
def trigger_local_notification_for_user(
    user_id: str,
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Trigger a local notification for a specific user (for testing)
    Returns the notification data that the frontend should display
    """
    try:
        # Find user's token
        user_token = db.query(PushToken).filter(PushToken.user_id == user_id).first()
        
        if not user_token:
            raise HTTPException(
                status_code=404, 
                detail=f"No push token found for user_id: {user_id}"
            )
        
        # Return notification data for local display
        return {
            "user_id": user_id,
            "token": user_token.token,
            "notification": {
                "title": req.title,
                "body": req.body,
                "data": req.data
            },
            "delivery_method": "local_trigger",
            "timestamp": time.time(),
            "instructions": "Frontend should call simulateIncomingPush() with this data"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger local notification: {str(e)}")

# Update the auto-detect endpoint to handle mock tokens
@router.post("/send-notification-auto-mock", response_model=NotificationResult)
def send_notification_auto_detect_with_mock(
    req: PushRequest,
    db: Session = Depends(get_db)
):
    """
    Auto-detect token types and handle mock tokens appropriately
    """
    try:
        # Try mock endpoint first (for development)
        mock_result = send_mock_notification_to_all(req, db)
        if mock_result.get("mock_simulations", 0) > 0:
            return {
                "total_tokens": mock_result["total_tokens"],
                "successful_sends": mock_result["mock_simulations"],
                "failed_sends": 0,
                "failed_tokens": [],
                "delivery_method": "mock_simulation"
            }
    except:
        pass
    
    # Fallback to regular endpoints
    try:
        return send_expo_notification_to_all(req, db)
    except:
        return send_notification_to_all(req, db)

        