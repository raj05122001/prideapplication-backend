from fastapi.responses import JSONResponse
from email.message import EmailMessage
import smtplib
import ssl
import asyncio

async def Final_send_agreement( email, name, mail_subject, mail_body, agreement_pdf ):
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
        msg["Subject"] = mail_subject
        msg.add_alternative(mail_body, subtype="html")

        # Attach PDF
        msg.add_attachment(agreement_pdf, maintype="application", subtype="pdf", filename="Agreement.pdf")

        # Send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return {"message": "Agreement Sent!","email":email,"name":name}

    except Exception as e:
        return JSONResponse(content={"message": "Failed to send agreement. Please download manually.", "error": str(e)}, status_code=500)
