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
    version="1.0"
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

KOBO_TOKEN = os.environ.get("KOBO_TOKEN")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")


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

        # Convert markdown formatted report to simple HTML lines
        html_content = f"""
        <h2>Agricultural Diagnostic Report</h2>
        <div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">
            {diagnostic_report.replace('\n', '<br>')}
        </div>
        """

        response = resend.Emails.send({
            "from": SENDER_EMAIL,
            "to": [clean_email],
            "subject": "Your Crop Assessment Report",
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
        print("        EMAIL DISPATCH ERROR")
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
    print("       NEW FARM REPORT RECEIVED")
    print("==========================================")

    sender_email = ""

    weekly_observation = "No text observation provided."

    image_bytes = None

    image_mime_type = "image/jpeg"


    # --------------------------------------------------------
    # EXTRACT EMAIL & OBSERVATION FROM KOBO PAYLOAD
    # --------------------------------------------------------

    for key, val in payload.items():

        if "email" in key.lower() or "mail" in key.lower():

            if val and "@" in str(val):

                sender_email = str(val)

                break


    for key, val in payload.items():

        if "observation" in key.lower() or "note" in key.lower() or "issue" in key.lower() or "description" in key.lower():

            if val and isinstance(val, str):

                weekly_observation = val

                break


    attachments = payload.get("_attachments", [])

    if attachments and isinstance(attachments, list):

        for attachment in attachments:

            download_url = attachment.get("download_url")

            if download_url:

                image_bytes, image_mime_type = download_kobo_media(download_url)

                if image_bytes:

                    break


    # --------------------------------------------------------
    # DISPLAY EXTRACTED INFORMATION
    # --------------------------------------------------------

    print()
    print("------------------------------------------")
    print(f"Sender Email: {sender_email}")
    print(f"Observation: {weekly_observation}")
    print(f"Has Image Bytes: {bool(image_bytes)}")
    print("------------------------------------------")


    if not client:

        print("ERROR: Gemini client is not configured.")

        return


    # --------------------------------------------------------
    # CREATE AI PROMPT
    # --------------------------------------------------------

    prompt_text = f"""

You are an agricultural support assistant helping smallholder farmers in South Africa.

Analyze the following farm report and, if provided, the attached crop image.


FIELD OBSERVATION:

{weekly_observation}


TASK:

Provide a comprehensive agricultural assessment.

Include:

1. Primary Issue / Pests / Diseases identified

2. Severity Rating (Mild, Moderate, or Severe)

3. Detailed Practical Actions for the Farmer

4. Preventative Measures & Next Week Monitoring

5. Confidence Level

"""


    # --------------------------------------------------------
    # PREPARE & CALL GEMINI
    # --------------------------------------------------------

    contents = [prompt_text]

    if image_bytes:

        try:

            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_mime_type
            )

            contents.append(image_part)

            print("--> Crop image attached for AI analysis.")

        except Exception as error:

            print("--> Could not attach image:", str(error))


    try:

        print("--> Calling Gemini API...")

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents
        )

        diagnostic_report = (
            response.text if response.text else "Gemini did not return an assessment."
        )


        print()
        print("==========================================")
        print("         AI REPORT GENERATED")
        print("==========================================")
        print(diagnostic_report)
        print("==========================================")


        # ----------------------------------------------------
        # DISPATCH REPORT VIA EMAIL
        # ----------------------------------------------------

        if sender_email:

            send_email_message(
                sender_email,
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
        "service": "Agricultural AI Assistant (Kobo to Email)"
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
