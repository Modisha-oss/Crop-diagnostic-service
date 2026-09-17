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
    version="1.4"
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
# HELPER: FLATTEN NESTED KOBO PAYLOAD
# ============================================================

def flatten_kobo_payload(payload_dict, parent_key=''):
    """
    Recursively flattens KoboToolbox payloads (including nested groups like site_issues)
    so field names like 'site_issues/farmer_email' can be parsed cleanly.
    """
    items = []
    if isinstance(payload_dict, dict):
        for k, v in payload_dict.items():
            new_key = f"{parent_key}/{k}" if parent_key else k
            if isinstance(v, (dict, list)):
                items.extend(flatten_kobo_payload(v, new_key).items())
            else:
                items.append((new_key, v))
    elif isinstance(payload_dict, list):
        for idx, item in enumerate(payload_dict):
            new_key = f"{parent_key}[{idx}]"
            if isinstance(item, (dict, list)):
                items.extend(flatten_kobo_payload(item, new_key).items())
            else:
                items.append((new_key, item))
    return dict(items)


# ============================================================
# SEND EMAIL FUNCTION (RESEND)
# ============================================================

def send_email_message(
    to_email: str,
    site_name: str,
    region_location: str,
    soil_type: str,
    seedling_crop_type: str,
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
            "ERROR: Recipient email is empty. Cannot dispatch email."
        )

        return


    # --------------------------------------------------------
    # SEND EMAIL VIA RESEND API
    # --------------------------------------------------------

    try:

        print(
            "--> Dispatching email via Resend..."
        )

        html_content = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333333;">
            <h2 style="color: #2e7d32; margin-bottom: 5px;">Agricultural Diagnostic Report</h2>
            <div style="background-color: #f1f8e9; padding: 12px; border-left: 4px solid #2e7d32; margin-bottom: 20px;">
                <p style="margin: 0; font-weight: bold;">Site / Farm Name: <span style="font-weight: normal;">{site_name}</span></p>
                <p style="margin: 4px 0 0 0; font-weight: bold;">Region / Location: <span style="font-weight: normal;">{region_location}</span></p>
                <p style="margin: 4px 0 0 0; font-weight: bold;">Soil Type: <span style="font-weight: normal;">{soil_type}</span></p>
                <p style="margin: 4px 0 0 0; font-weight: bold;">Seedling / Crop Type: <span style="font-weight: normal;">{seedling_crop_type}</span></p>
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

    # Flatten nested payload
    flat_payload = flatten_kobo_payload(payload)

    # PRINT ALL RECEIVED KEYS FOR DEBUGGING IN RENDER LOGS
    print("RECEIVED KOBO KEYS & VALUES:")
    for k, v in flat_payload.items():
        if not str(k).startswith("_") and len(str(v)) < 100:
            print(f"  {k} ==> {v}")
    print("------------------------------------------")

    sender_email = ""

    site_name = "Not specified"

    region_location = "Not specified"

    date_planted = "Not specified"

    soil_type = "Not specified"

    seedling_crop_type = "Not specified"

    weekly_observation = "No text observation provided."

    image_parts = []


    # Kobo internal metadata keys to strictly ignore
    ignored_metadata_keys = [
        "_id", "_uuid", "_submission_time", "_submitted_by",
        "_status", "start", "end", "today", "deviceid", "instanceID"
    ]


    # --------------------------------------------------------
    # 1. EXTRACT FARMER EMAIL
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        if val and isinstance(val, str) and "@" in val and "." in val:

            # Ignore generic non-user email strings if any
            if not any(ign in key.lower() for ign in ["meta", "attachment"]):

                sender_email = val.strip()

                break


    # --------------------------------------------------------
    # 2. EXTRACT SITE NAME (Excludes Date/Metadata values)
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        k_lower = key.lower()

        if any(sk in k_lower for sk in ["site_name", "farm_name", "site", "farm_id", "plot_name"]):

            # Check key is not metadata and value isn't a date string (e.g. YYYY-MM-DD)
            if not any(ign in k_lower for ign in ignored_metadata_keys + ["date", "time"]):

                if val and isinstance(val, str) and not (len(val) == 10 and val.count("-") == 2):

                    site_name = val.strip()

                    break


    # --------------------------------------------------------
    # 3. EXTRACT DATE PLANTED
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        k_lower = key.lower()

        if "plant" in k_lower or "date_planted" in k_lower or "planting_date" in k_lower:

            if val and isinstance(val, str):

                date_planted = val.strip()

                break


    # --------------------------------------------------------
    # 4. EXTRACT SOIL TYPE
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        if "soil" in key.lower():

            if val and isinstance(val, str):

                soil_type = val.strip()

                break


    # --------------------------------------------------------
    # 5. EXTRACT SEEDLING / CROP TYPE
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        if any(ck in key.lower() for ck in ["seedling", "crop"]):

            if val and isinstance(val, str):

                seedling_crop_type = val.strip()

                break


    # --------------------------------------------------------
    # 6. EXTRACT REGION / LOCATION
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        if any(rk in key.lower() for rk in ["region", "province", "location", "district", "area", "town"]):

            if val and isinstance(val, str):

                region_location = val.strip()

                break

    if region_location == "Not specified" and "_geolocation" in payload:

        geo = payload.get("_geolocation")

        if geo and isinstance(geo, list) and len(geo) >= 2:

            region_location = f"GPS: {geo[0]}, {geo[1]}"


    # --------------------------------------------------------
    # 7. EXTRACT WEEKLY OBSERVATIONS / SITE ISSUES
    # --------------------------------------------------------

    for key, val in flat_payload.items():

        k_lower = key.lower()

        if any(ok in k_lower for ok in ["observation", "issue", "notes", "description", "problem", "comment"]):

            # Ensure value is descriptive text, not a date or ID key
            if not any(ign in k_lower for ign in ignored_metadata_keys + ["date", "time"]):

                if val and isinstance(val, str) and not (len(val) == 10 and val.count("-") == 2):

                    weekly_observation = val.strip()

                    break


    # --------------------------------------------------------
    # EXTRACT & DOWNLOAD ATTACHED IMAGES
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
    print(f"Date Planted: {date_planted}")
    print(f"Soil Type: {soil_type}")
    print(f"Seedling/Crop Type: {seedling_crop_type}")
    print(f"Weekly Observations: {weekly_observation}")
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

Analyze the following site issue report, soil parameters, and all attached crop images.


SITE / FARM NAME: {site_name}

DATE PLANTED: {date_planted}

SOIL TYPE: {soil_type}

SEEDLING/CROP TYPE: {seedling_crop_type}

FARM LOCATION / REGION: {region_location}

FIELD OBSERVATION / ISSUE REPORTED: {weekly_observation}


TASK:

Provide a comprehensive agricultural assessment. 

Reference the site name ({site_name}) and tailor your diagnostic, soil management, and climate-related advice specifically to the regional conditions of {region_location} in South Africa.


Include:

1. Primary Issue / Pests / Diseases identified across the attached photos and observation

2. Severity Rating (Mild, Moderate, or Severe)

3. Region-Specific Advisory & Practical Actions for the Farmer at {site_name} (taking into account the soil type: {soil_type} and crop: {seedling_crop_type})

4. Preventative Measures & Next Week Monitoring

5. Confidence Level
"""


    # --------------------------------------------------------
    # PREPARE & CALL GEMINI
    # --------------------------------------------------------

    contents = [prompt_text] + image_parts


    try:

        print("--> Calling Gemini API with multi-image, site, soil, and regional context...")

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
                soil_type,
                seedling_crop_type,
                diagnostic_report
            )

        else:

            print("WARNING: No email address extracted from Kobo submission. Skipping email dispatch.")


    except Exception as error:

        print("ERROR: Gemini processing failed:", str(error))


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def home():

    return {
        "status": "Live",
        "service": "Agricultural AI Assistant (Site Issues Extraction & Diagnostics)"
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
