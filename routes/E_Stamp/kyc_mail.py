from fastapi.responses import JSONResponse
from email.message import EmailMessage
import smtplib
import ssl

async def send_agreement(email: str, name: str, signing_url: str):
    # Replace with your actual SMTP settings or load them from environment variables
    smtp_server = "smtpout.secureserver.net"
    smtp_port = 465
    smtp_user = "compliance@pridecons.com"
    smtp_pass = "Pride@#0308"  # move to environment variable in production

    try:
        # Create email
        msg = EmailMessage()
        msg["From"] = "Pride Trading Consultancy Pvt. Ltd. <compliance@pridecons.com>"
        msg["To"] = email
        msg["Bcc"] = "compliance@pridecons.com"
        msg["Cc"] = "prideconsultancy04@gmail.com"
        msg["Subject"] = "Pride Service Agreement - Action Required"

        # Email content with the signing URL
        msg.set_content(f"""
Dear {name},

Thank you for choosing Pride Trading Consultancy Pvt. Ltd.

Please click the link below to review and sign your service agreement:

{signing_url}

If you have any questions or require further assistance, please feel free to reach out to our support team.

Thanks & Regards,  
Pride Trading Consultancy Pvt. Ltd.
        """)

        # Send email using a secure SSL context
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return {"message": "Agreement sent successfully!", "email": email, "name": name}

    except Exception as e:
        return JSONResponse(
            content={"message": "Failed to send agreement. Please download manually.", "error": str(e)},
            status_code=500
        )
