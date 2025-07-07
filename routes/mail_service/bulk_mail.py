from __future__ import annotations

import io
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import pandas as pd
import smtplib
from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import JSONResponse

from config import SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

router = APIRouter(tags=["Bulk Mail"])

# ─────────────── helper to send one email ──────────────────────────────
def send_mail(
    *,
    email: str,
    name: str,
    files: Optional[List[dict]] = None,
    content: str,
    subject: str,
):
    try:
        root = MIMEMultipart("related")
        root["From"] = "Pride Trading Consultancy Pvt. Ltd. <research@pridecons.com>"
        root["To"] = email
        root["Subject"] = subject

        html_body = f"""
        <html>
          <body style="font-family:sans-serif;line-height:1.4;">
            <p>Dear <strong>{name}</strong>,</p>
            <div>{content}</div>

            <hr style="margin:30px 0;border:none;border-top:1px solid #ccc;"/>

            <footer style="text-align:center;font-size:.9em;color:#666;">
            <p>
            Our past performance does not guarantee the future performance. Investment in market is subject to market risks. Not with standing all the efforts to do best research, clients should understand that investing in market involves a risk of loss of both income and principal. Please ensure that you understand fully the risks involved in investment in market. <br>  <br>
“Registration granted by SEBI, membership of a SEBI recognized supervisory body (if any) and certification from NISM in no way guarantee performance of the intermediary or provide any assurance of returns to investors.” “Investment in securities market are subject to market risks. Read all the related documents carefully before investing.” "The securities quoted are for illustration only and are not recommendatory"

              </p>
              <img src="https://drive.google.com/uc?export=view&id=1PZ76KIfydm8Wtwip58354MMpR_96z0ta"
              alt="Pride Logo" style="width: 260px; margin-top: 10px;" />
            </footer>
          </body>
        </html>
        """

        root.attach(MIMEText(html_body, "html"))

        # Attach only PDF files
        if files:
            for f in files:
                part = MIMEApplication(f["content"], _subtype="pdf")
                part.add_header("Content-Disposition", "attachment", filename=f["filename"])
                root.attach(part)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ssl.create_default_context()) as s:
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(root)

        return {"message": "Mail sent", "email": email}

    except Exception as exc:
        return JSONResponse(
            {"message": "Failed to send email", "error": str(exc)}, status_code=500
        )


# ─────────────── bulk endpoint ─────────────────────────────────────────
@router.post("/bulk-send-mail/")
async def bulk_send_mail(
    background_tasks: BackgroundTasks,
    sheet: UploadFile = File(..., description="Excel (.xlsx) with 'name' & 'mail'"),
    subject: str = Form(...),
    content: str = Form(...),
    attachments: List[UploadFile] = File(
        default=None, description="Attach one or many PDF files (repeat the field)"
    )
):
    """
    Reads the sheet, dedups, sends personalised emails (background), with
    optional PDF attachment(s).
    """
    try:
        df = pd.read_excel(io.BytesIO(await sheet.read()))
        if {"name", "mail"} - set(df.columns):
            return JSONResponse(
                {"error": "Sheet must contain 'name' and 'mail' columns."}, 400
            )

        df["mail"] = df["mail"].str.strip().str.lower()
        df = df.drop_duplicates(subset="mail")

        # Process attachments - only PDF
        files_raw = attachments if attachments else []
        file_payloads: list[dict] = []
        for up in files_raw:
            if not getattr(up, "filename", "").lower().endswith(".pdf"):
                continue
            await up.seek(0)
            file_payloads.append(
                {
                    "filename": up.filename,
                    "content": await up.read(),
                }
            )

        # Schedule background email tasks
        for _, row in df.iterrows():
            background_tasks.add_task(
                send_mail,
                email=row["mail"],
                name=row["name"],
                files=file_payloads,
                content=content,
                subject=subject,
            )

        return {
            "message": f"Scheduled {len(df)} email(s) with "
                       f"{len(file_payloads)} PDF attachment(s)."
        }

    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
