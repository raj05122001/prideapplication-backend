import io
import xml.etree.ElementTree as ET
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

router = APIRouter()

def generate_pdf(xml_data: bytes) -> io.BytesIO:
    """
    Convert XML data to a PDF and return it as an in-memory buffer,
    with all fields in a two-column table and without the 'APP_' prefix.
    """
    # Parse XML
    tree = ET.ElementTree(ET.fromstring(xml_data.decode("utf-8")))
    root = tree.getroot()

    # Prepare PDF buffer & document
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    # Build table data: header row + one row per element
    data = [["Field", "Value"]]

    def collect(element):
        # strip APP_ prefix if present
        tag = element.tag
        if tag.startswith("APP_"):
            tag = tag[len("APP_"):]
        # only add if there's non-empty text
        text = element.text.strip() if element.text else ""
        data.append([tag, text])
        for child in element:
            collect(child)

    collect(root)

    # Create and style the table
    table = Table(data, hAlign="LEFT", colWidths=[210, 340])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ])
    )

    # Build PDF
    doc.build([table])

    # rewind buffer and return
    buffer.seek(0)
    return buffer

@router.post("/convert-xml-to-pdf")
async def convert_xml_to_pdf(file: UploadFile = File(...)):
    """
    Accepts an uploaded XML file and returns a generated PDF as a download.
    """
    # Read the uploaded XML file
    xml_data = await file.read()

    # Generate PDF using the provided XML data
    pdf_buffer = generate_pdf(xml_data)

    # Set appropriate headers for file download
    headers = {"Content-Disposition": 'attachment; filename="output.pdf"'}
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)
