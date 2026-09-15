import os
import warnings
import requests
import resend
import markdown
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
    version="1.3"
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
# SEND EMAIL FUNCTION WITH TENACITY RETRY LOGIC
# ============================================================

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def execute_resend_email_dispatch(
    clean_email: str,
    subject: str,
    html_content: str
):

    print("--> Attempting email dispatch via Resend...")

    response = resend.Emails.send({
        "from": SENDER_EMAIL,
        "to": [clean_email],
        "subject": subject,
        "html": html_content
    })

    return response


def send_email_message(
    to_email: str,
    farmer_name: str,
    site_name: str,
    region_location: str,
    diagnostic_report: str
):

    print()
    print("==========================================")
    print("          EMAIL PROCESS STARTED")
    print("==========================================")

    clean_email = str(to_email).strip().lower()

    print(
        f"Recipient Email: {clean_email}"
    )

    print(
        f"Farmer Name: {farmer_name}"
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


    # Convert raw markdown report to valid HTML
    report_html = markdown.markdown(diagnostic_report)


    # --------------------------------------------------------
    # PERSONALIZED HTML EMAIL TEMPLATE
    # --------------------------------------------------------

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 650px; font-size: 14px; line-height: 1.6; color: #333333; border: 1px solid #e0e0e0; border-radius: 8px; padding: 24px; margin: 0 auto;">
        
        <h2 style="color: #2e7d32; margin-top: 0;">Good day, {farmer_name} 👋</h2>
        
        <p>Please find your automated agricultural diagnostic report for <strong>{site_name}</strong> ({region_location}) below:</p>
        
        <div style="background-color: #f1f8e9; padding: 16px; border-left: 4px solid #2e7d32; margin: 20px 0; border-radius: 4px;">
            {report_html}
        </div>

        <p style="font-size: 0.85em; color: #666666; margin-top: 20px;">
            <em>This report was generated automatically using KoboToolbox field telemetry and AI diagnostic analysis.</em>
        </p>
        
        <hr style="border: 0; border-top: 1px solid #cccccc; margin: 20px 0;">
        
        <p style="margin-bottom: 0;">
            Kind regards,<br>
            <strong>Agricultural Extension & Field Diagnostics Team</strong>
        </p>

    </div>
    """


    try:

        response = execute_resend_email_dispatch(
            clean_email=clean_email,
            subject=f"Agricultural Assessment Report - {site_name}",
            html_content=html_content
        )

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
        print("          EMAIL DISPATCH ERROR")
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
# CALL GEMINI WITH MODEL FALLBACK & RETRIES
# ============================================================

def generate_ai_report_with_fallback(contents: list) -> str:

    models_to_try = [
        "gemini-3.6-flash",
        "gemini-3.5-flash"
    ]

    for model_name in models_to_try:

        try:

            print(f"--> Calling Gemini API using model [{model_name}]...")

            response = client.models.generate_content(
                model=model_name,
                contents=contents
            )

            if response and response.text:

                print(f"--> AI Report generation successful using [{model_name}].")

                return response.text

        except Exception as error:

            print(f"WARNING: Model [{model_name}] failed or experienced high traffic load.")

            print("Error details:", str(error))

            print("--> Switching to fallback model...")


    return "Error: Unable to generate diagnostic assessment due to temporary high system load across AI models."


# ============================================================
# PROCESS FARM REPORT
# ============================================================

def process_farm_report(payload: dict):

    print()
    print("==========================================")
    print("        NEW FARM REPORT RECEIVED")
    print("==========================================")

    farmer_name = "Valued Farmer"

    sender_email = ""

    site_name = "Main Production Site"

    region_location = "Not specified"

    date_planted = "Not specified"

    soil_type = "Not specified"

    seedling_type = "Not specified"

    weekly_observation = "No text observation provided."

    image_parts = []


    # --------------------------------------------------------
    # EXTRACT DATA FIELDS FROM KOBO PAYLOAD
    # --------------------------------------------------------

    # Extract Farmer Name
    for key, val in payload.items():

        if any(name_key in key.lower() for name_key in ["farmer_name", "farmers_name", "farmer", "name"]):

            if val and isinstance(val, str):

                farmer_name = val

                break


    # Extract Farmer Email
    for key, val in payload.items():

        if "email" in key.lower() or "mail" in key.lower():

            if val and "@" in str(val):

                sender_email = str(val)

                break


    # Extract Site Location
    for key, val in payload.items():

        if any(site_key in key.lower() for site_key in ["site", "farm", "plot", "field_name"]):

            if val and isinstance(val, str):

                site_name = val

                break


    # Extract Region / Location
    for key, val in payload.items():

        if any(region_key in key.lower() for region_key in ["region", "province", "location", "district", "area", "town"]):

            if val and isinstance(val, str):

                region_location = val

                break


    # Extract Date Planted
    for key, val in payload.items():

        if "planted" in key.lower() or "plant_date" in key.lower() or "date" in key.lower():

            if val and isinstance(val, str):

                date_planted = val

                break


    # Extract Soil Type
    for key, val in payload.items():

        if "soil" in key.lower():

            if val and isinstance(val, str):

                soil_type = val

                break


    # Extract Seedling / Crop Type
    for key, val in payload.items():

        if "seedling" in key.lower() or "crop" in key.lower() or "variety" in key.lower():

            if val and isinstance(val, str):

                seedling_type = val

                break


    # Extract Weekly Observation / Issue Notes
    for key, val in payload.items():

        if "observation" in key.lower() or "note" in key.lower() or "issue" in key.lower() or "description" in key.lower():

            if val and isinstance(val, str):

                weekly_observation = val

                break


    # Fallback GPS Geolocation
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
    print(f"Farmer Name: {farmer_name}")
    print(f"Sender Email: {sender_email}")
    print(f"Site Name: {site_name}")
    print(f"Region/Location: {region_location}")
    print(f"Date Planted: {date_planted}")
    print(f"Soil Type: {soil_type}")
    print(f"Seedling/Crop Type: {seedling_type}")
    print(f"Observation: {weekly_observation}")
    print(f"Total Images Attached: {len(image_parts)}")
    print("------------------------------------------")


    if not client:

        print("ERROR: Gemini client is not configured.")

        return


    # --------------------------------------------------------
    # CREATE AI PROMPT WITH FULL AGRONOMIC METADATA
    # --------------------------------------------------------

    prompt_text = f"""
You are an expert agricultural specialist assisting smallholder farmers in South Africa.

Analyze the provided crop data, soil properties, planting metadata, location context, and attached field images.

FARMER NAME: {farmer_name}
SITE / FARM NAME: {site_name}
REGION / LOCATION: {region_location}
DATE PLANTED: {date_planted}
SOIL TYPE: {soil_type}
SEEDLING / CROP VARIETY: {seedling_type}
FIELD OBSERVATION / ISSUE NOTES: {weekly_observation}

TASK:
Provide a comprehensive, professional diagnostic assessment. Reference the site ({site_name}) and tailor your agronomic, soil, and pest management advice to the specific crop stage (planted on {date_planted}), soil characteristics ({soil_type}), and regional environment ({region_location}).

Structure your report into the following sections:
1. **Primary Diagnosis**: Identify any diseases, pests, nutrient deficiencies, or environmental stresses visible in the images and described in the notes.
2. **Crop Stage & Soil Evaluation**: Evaluate how the soil type ({soil_type}) and growth stage (since {date_planted}) impact current crop health.
3. **Severity Rating**: Indicate if the issue is Mild, Moderate, or Severe.
4. **Immediate Action Steps**: 2-3 clear, practical actions the farmer can take immediately at {site_name}.
5. **Preventative Measures & Next Week Monitoring**: Long-term actions for sustainable management.
6. **Confidence Level**: High, Medium, or Low.
"""


    # --------------------------------------------------------
    # CALL GEMINI WITH MULTI-MODEL FALLBACK
    # --------------------------------------------------------

    contents = [prompt_text] + image_parts

    diagnostic_report = generate_ai_report_with_fallback(contents)


    print()
    print("==========================================")
    print("          AI REPORT GENERATED")
    print("==========================================")
    print(diagnostic_report)
    print("==========================================")


    # --------------------------------------------------------
    # DISPATCH REPORT VIA EMAIL
    # --------------------------------------------------------

    if sender_email:

        send_email_message(
            sender_email,
            farmer_name,
            site_name,
            region_location,
            diagnostic_report
        )

    else:

        print("WARNING: No email address extracted from Kobo submission.")


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def home():

    return {
        "status": "Live",
        "service": "Agricultural AI Assistant (Multi-Image, Metadata Lookup & Automatic Email Dispatch)"
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
