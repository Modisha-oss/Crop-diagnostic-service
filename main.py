import os
import warnings
import requests
import resend

from fastapi import FastAPI, HTTPException, Request

from google import genai
from google.genai import types


# ============================================================
# SUPPRESS NON-CRITICAL WARNINGS
# ============================================================

warnings.filterwarnings("ignore")


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Modisha's Agricultural AI Assistant (Email)",
    version="1.2"
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

KOBO_TOKEN = os.environ.get("KOBO_TOKEN")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

SENDER_EMAIL = os.environ.get(
    "SENDER_EMAIL", 
    "Modisha Crop Diagnostics <reports@modisha-agri.co.za>"
)


# ============================================================
# GEMINI & RESEND SETUP
# ============================================================

if GEMINI_API_KEY:

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

else:

    client = None

    print(
        "WARNING: GEMINI_API_KEY is missing."
    )


if RESEND_API_KEY:

    resend.api_key = RESEND_API_KEY

else:

    print(
        "WARNING: RESEND_API_KEY is missing."
    )


# ============================================================
# SEND EMAIL FUNCTION (RESEND)
# ============================================================

def send_email_message(
    to_email: str,
    site_name: str,
    region_location: str,
    diagnostic_report: str
):

    print()
    print("==========================================")
    print("         EMAIL PROCESS STARTED")
    print("==========================================")

    clean_email = str(to_email).strip().lower()

    print(
        f"Recipient Email: {clean_email}"
    )

    print(
        f"Sender Email: {SENDER_EMAIL}"
    )


    if not RESEND_API_KEY:

        print(
            "ERROR: RESEND_API_KEY is missing from Environment Variables."
        )

        return


    if not clean_email:

        print(
            "ERROR: Recipient email is empty."
        )

        return


    # --------------------------------------------------------
    # SEND EMAIL VIA RESEND API
    # --------------------------------------------------------

    try:

        print(
            "--> Dispatching email via Resend..."
        )

        # Convert markdown formatted report to styled HTML lines
        html_content = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333333;">
            <h2 style="color: #2e7d32; margin-bottom: 5px;">Agricultural Diagnostic Report</h2>
            <div style="background-color: #f1f8e9; padding: 12px; border-left: 4px solid #2e7d32; margin-bottom: 20px;">
                <p style="margin: 0; font-weight: bold;">Site / Farm Name: <span style="font-weight: normal;">{site_name}</span></p>
                <p style="margin: 4px 0 0 0; font-weight: bold;">Region / Location: <span style="font-weight: normal;">{region_location}</span></p>
            </div>
            <hr style="border: 0; border-top: 1px solid #cccccc; margin-bottom: 20px;">
            <div>
                {diagnostic_report.replace('\n', '<br>')}
            </div>
        </div>
        """

        response = resend.Emails.send({
            "from": SENDER_EMAIL,
            "to": [clean_email],
            "subject": f"Crop Assessment Report - {site_name} ({region_location})",
            "html": html_content
        })


        print()
        print("==========================================")
        print("      EMAIL DISPATCH SUCCESSFUL!")
        print("==========================================")

        print(
            f"Email ID: {response.get('id')}"
        )


    except Exception as error:

        print()
        print("==========================================")
        print("         EMAIL DISPATCH ERROR")
        print("==========================================")

        print(
            "Error type:",
            type(error).__name__
        )

        print(
            "Error message:",
            str(error)
        )

        print("==========================================")


# ============================================================
# DOWNLOAD KOBO MEDIA FUNCTION
# ============================================================

def download_kobo_media(download_url: str):

    print()
    print("==========================================")
    print("       KOBO MEDIA DOWNLOAD STARTED")
    print("==========================================")

    print(
        f"Download URL: {download_url}"
    )

    headers = {}

    if KOBO_TOKEN:

        headers["Authorization"] = f"Token {KOBO_TOKEN}"


    try:

        res = requests.get(
            download_url,
            headers=headers,
            timeout=30
        )


        if res.status_code == 200:

            content_type = res.headers.get("Content-Type", "image/jpeg")

            print(
                "--> Kobo image download successful!"
            )

            print(
                f"--> MIME type: {content_type}"
            )

            return res.content, content_type

        else:

            print(
                f"--> Failed to download Kobo media. HTTP {res.status_code}"
            )

            return None, "image/jpeg"


    except Exception as error:

        print(
            "--> Exception occurred while downloading Kobo media:"
        )

        print(
            type(error).__name__,
            str(error)
        )

        return None, "image/jpeg"


# ============================================================
# PROCESS FARM REPORT
# ============================================================

def process_farm_report(payload: dict):

    print()
    print("==========================================")
    print("        NEW FARM REPORT RECEIVED")
    print("==========================================")

    sender_email = ""

    site_name = "Main Production Site"

    region_location = "Not specified"

    weekly_observation = "No text observation provided."

    image_parts = []


    # --------------------------------------------------------
    # EXTRACT DATA FIELDS FROM KOBO PAYLOAD
    # --------------------------------------------------------

    for key, val in payload.items():

        if "email" in key.lower() or "mail" in key.lower():

            if val and "@" in str(val):

                sender_email = str(val)

                break


    for key, val in payload.items():

        if any(site_key in key.lower() for site_key in ["site", "farm", "plot", "field_name"]):

            if val and isinstance(val, str):

                site_name = val

                break


    for key, val in payload.items():

        if any(region_key in key.lower() for region_key in ["region", "province", "location", "district", "area", "town"]):

            if val and isinstance(val, str):

                region_location = val

                break


    for key, val in payload.items():

        if "observation" in key.lower() or "note" in key.lower() or "issue" in key.lower() or "description" in key.lower():

            if val and isinstance(val, str):

                weekly_observation = val

                break


    # Extract GPS Geolocation if region text key is not explicitly named
    if region_location == "Not specified" and "_geolocation" in payload:

        geo = payload.get("_geolocation")

        if geo and isinstance(geo, list) and len(geo) >= 2:

            region_location = f"GPS: {geo[0]}, {geo[1]}"


    # --------------------------------------------------------
    # EXTRACT & DOWNLOAD MULTIPLE IMAGE ATTACHMENTS
    # --------------------------------------------------------

    attachments = payload.get("_attachments", [])

    if attachments and isinstance(attachments, list):

        for attachment in attachments:

            download_url = attachment.get("download_url")

            mimetype = attachment.get("mimetype", "image/")

            if download_url and "image" in mimetype:

                img_bytes, img_mime = download_kobo_media(download_url)

                if img_bytes:

                    try:

                        part = types.Part.from_bytes(
                            data=img_bytes,
                            mime_type=img_mime
                        )

                        image_parts.append(part)

                        print(f"--> Successfully prepared image attachment {len(image_parts)}")

                    except Exception as error:

                        print("--> Failed to format image part:", str(error))


    # --------------------------------------------------------
    # DISPLAY EXTRACTED INFORMATION
    # --------------------------------------------------------

    print()
    print("------------------------------------------")
    print(f"Sender Email: {sender_email}")
    print(f"Site Name: {site_name}")
    print(f"Region/Location: {region_location}")
    print(f"Observation: {weekly_observation}")
    print(f"Total Images Attached: {len(image_parts)}")
    print("------------------------------------------")


    if not client:

        print("ERROR: Gemini client is not configured.")

        return


    # --------------------------------------------------------
    # CREATE AI PROMPT
    # --------------------------------------------------------

    prompt_text = f"""

You are an agricultural expert helping smallholder farmers in South Africa.

Analyze the following farm report, location context, and all attached crop images.


SITE / FARM NAME: {site_name}

FARM LOCATION / REGION: {region_location}

FIELD OBSERVATION: {weekly_observation}


TASK:

Provide a comprehensive agricultural assessment. 

Reference the site name ({site_name}) and tailor your diagnostic and climate-related advice specifically to the regional conditions of {region_location} in South Africa.


Include:

1. Primary Issue / Pests / Diseases identified across the attached photos and observation

2. Severity Rating (Mild, Moderate, or Severe)

3. Region-Specific Advisory & Practical Actions for the Farmer at {site_name}

4. Preventative Measures & Next Week Monitoring

5. Confidence Level

"""


    # --------------------------------------------------------
    # PREPARE & CALL GEMINI
    # --------------------------------------------------------

    contents = [prompt_text] + image_parts


    try:

        print("--> Calling Gemini API with multi-image, site, and regional context...")

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents
        )

        diagnostic_report = (
            response.text if response.text else "Gemini did not return an assessment."
        )


        print()
        print("==========================================")
        print("          AI REPORT GENERATED")
        print("==========================================")
        print(diagnostic_report)
        print("==========================================")


        # ----------------------------------------------------
        # DISPATCH REPORT VIA EMAIL
        # ----------------------------------------------------

        if sender_email:

            send_email_message(
                sender_email,
                site_name,
                region_location,
                diagnostic_report
            )

        else:

            print("WARNING: No email address extracted from Kobo submission.")


    except Exception as error:

        print("ERROR: Gemini processing failed:", str(error))


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def home():

    return {
        "status": "Live",
        "service": "Agricultural AI Assistant (Multi-Image, Site & Regional Kobo to Email)"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY),
        "resend_configured": bool(RESEND_API_KEY),
        "kobo_configured": bool(KOBO_TOKEN)
    }


@app.post("/webhook/kobo")
@app.post("/webhook")
async def handle_kobo_webhook(request: Request):

    try:

        payload = await request.json()

    except Exception:

        raise HTTPException(status_code=400, detail="Invalid JSON payload")


    process_farm_report(payload)

    return {
        "status": "success",
        "message": "Kobo submission processed and Email dispatched."
    }
