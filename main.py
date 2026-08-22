import os
import smtplib
import warnings
import requests

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
    title="Modisha's Agricultural AI Assistant",
    version="1.0"
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")


# ============================================================
# GEMINI CLIENT
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


# ============================================================
# EMAIL FUNCTION
# ============================================================

def send_advisory_email(
    to_email: str,
    subject: str,
    report_body: str
):

    print()
    print("==========================================")
    print("          EMAIL PROCESS STARTED")
    print("==========================================")

    print(
        f"Recipient: {to_email}"
    )

    print(
        f"Sender configured: "
        f"{bool(SENDER_EMAIL)}"
    )

    print(
        f"Sender password configured: "
        f"{bool(SENDER_PASSWORD)}"
    )


    # --------------------------------------------------------
    # CHECK EMAIL SETTINGS
    # --------------------------------------------------------

    if not SENDER_EMAIL:

        print(
            "ERROR: SENDER_EMAIL is missing "
            "from Render Environment Variables."
        )

        return


    if not SENDER_PASSWORD:

        print(
            "ERROR: SENDER_PASSWORD is missing "
            "from Render Environment Variables."
        )

        return


    if not to_email:

        print(
            "ERROR: Farmer email address is empty."
        )

        return


    # --------------------------------------------------------
    # CREATE EMAIL
    # --------------------------------------------------------

    msg = MIMEMultipart()

    msg["From"] = SENDER_EMAIL

    msg["To"] = to_email

    msg["Subject"] = subject

    msg.attach(
        MIMEText(
            report_body,
            "plain"
        )
    )


    # --------------------------------------------------------
    # CONNECT TO GMAIL
    # --------------------------------------------------------

    try:

        print(
            "--> Connecting to Gmail SMTP..."
        )


        with smtplib.STARTTLS(
            "smtp.gmail.com",
            587,
            timeout=30
        ) as server:


            print(
                "--> Connected to Gmail SMTP."
            )


            # ------------------------------------------------
            # LOGIN
            # ------------------------------------------------

            print(
                "--> Logging into Gmail..."
            )


            server.login(
                SENDER_EMAIL,
                SENDER_PASSWORD
            )


            print(
                "--> Gmail login successful."
            )


            # ------------------------------------------------
            # SEND EMAIL
            # ------------------------------------------------

            print(
                "--> Sending agricultural report..."
            )


            server.sendmail(
                SENDER_EMAIL,
                to_email,
                msg.as_string()
            )


            print()
            print(
                "=========================================="
            )

            print(
                "       EMAIL SENT SUCCESSFULLY!"
            )

            print(
                "=========================================="
            )

            print(
                f"Report sent to: {to_email}"
            )


    # --------------------------------------------------------
    # EMAIL ERROR
    # --------------------------------------------------------

    except Exception as error:

        print()
        print(
            "=========================================="
        )

        print(
            "             EMAIL ERROR"
        )

        print(
            "=========================================="
        )

        print(
            "Error type:",
            type(error).__name__
        )

        print(
            "Error message:",
            str(error)
        )

        print(
            "=========================================="
        )


# ============================================================
# PROCESS FARM REPORT
# ============================================================

def process_farm_report(payload: dict):

    print()
    print("==========================================")
    print("       NEW FARM REPORT RECEIVED")
    print("==========================================")


    print(
        f"Incoming Payload Keys: "
        f"{list(payload.keys())}"
    )


    # ========================================================
    # FIND FARMER EMAIL
    # ========================================================

    def find_email(data):

        if isinstance(data, dict):

            for key, value in data.items():

                # ------------------------------------------------
                # CHECK FIELD NAME FOR EMAIL
                # ------------------------------------------------

                if (
                    "email" in key.lower()
                    and isinstance(value, str)
                    and "@" in value
                ):

                    return value.strip()


                # ------------------------------------------------
                # SEARCH NESTED DATA
                # ------------------------------------------------

                result = find_email(value)

                if result:

                    return result


        elif isinstance(data, list):

            for item in data:

                result = find_email(item)

                if result:

                    return result


        return ""


    farmer_email = find_email(
        payload
    )


    # ========================================================
    # EXTRACT FARM INFORMATION
    # ========================================================

    site_location = (

        payload.get("site_location")

        or payload.get("location")

        or "Turfloop"
    )


    region = (

        payload.get("region")

        or "Limpopo"
    )


    vegetable = (

        payload.get("vegetable")

        or payload.get("crop")

        or "Crop"
    )


    weekly_observation = (

        payload.get("weekly_observation")

        or payload.get("observations")

        or payload.get("field_notes")

        or "No field observations provided."
    )


    # ========================================================
    # DISPLAY EXTRACTED INFORMATION
    # ========================================================

    print()
    print(
        "------------------------------------------"
    )

    print(
        f"Site Location: {site_location}"
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Vegetable/Crop: {vegetable}"
    )

    print(
        f"Observation: {weekly_observation}"
    )

    print(
        f"Extracted Farmer Email: '{farmer_email}'"
    )

    print(
        "------------------------------------------"
    )


    # ========================================================
    # DOWNLOAD KOBO IMAGE
    # ========================================================

    attachments = payload.get(
        "_attachments",
        []
    )

    image_bytes = None

    image_mime_type = "image/jpeg"


    if attachments:

        print(
            f"--> Number of attachments: "
            f"{len(attachments)}"
        )


        # ----------------------------------------------------
        # FIRST ATTACHMENT
        # ----------------------------------------------------

        first_attachment = attachments[0]

        photo_url = (
            first_attachment.get(
                "download_url"
            )
        )


        if photo_url:

            print(
                f"--> Downloading photo from: "
                f"{photo_url}"
            )


            try:

                img_res = requests.get(

                    photo_url,

                    headers={
                        "User-Agent":
                        "Mozilla/5.0"
                    },

                    timeout=30
                )


                # ------------------------------------------------
                # CHECK DOWNLOAD
                # ------------------------------------------------

                if img_res.status_code == 200:

                    image_bytes = (
                        img_res.content
                    )


                    # --------------------------------------------
                    # DETECT IMAGE TYPE
                    # --------------------------------------------

                    content_type = (
                        img_res.headers.get(
                            "Content-Type",
                            ""
                        )
                    )


                    if content_type.startswith(
                        "image/"
                    ):

                        image_mime_type = (
                            content_type
                        )


                    print(
                        "--> Photo download successful!"
                    )

                    print(
                        f"--> Image type: "
                        f"{image_mime_type}"
                    )

                    print(
                        f"--> Image size: "
                        f"{len(image_bytes)} bytes"
                    )


                else:

                    print(
                        "--> Photo download failed."
                    )

                    print(
                        f"--> HTTP status: "
                        f"{img_res.status_code}"
                    )


            except Exception as error:

                print(
                    "--> Photo download exception:"
                )

                print(
                    type(error).__name__,
                    str(error)
                )


        else:

            print(
                "--> Attachment found, "
                "but no download_url was provided."
            )


    else:

        print(
            "--> No crop photograph "
            "was found in this submission."
        )


    # ========================================================
    # CHECK GEMINI
    # ========================================================

    if not client:

        print(
            "ERROR: Gemini client is not configured."
        )

        return


    # ========================================================
    # CREATE AI PROMPT
    # ========================================================

    prompt_text = f"""

You are an agricultural support assistant
helping smallholder farmers in South Africa.

Analyze the following farm report and,
if provided, the attached crop image.

SITE DETAILS:

Site Location:
{site_location}

Region:
{region}


CROP DETAILS:

Crop:
{vegetable}


FIELD OBSERVATION:

{weekly_observation}


TASK:

Provide a practical agricultural assessment
for the farmer.

Include:

1. Possible causes or issues

2. Possible pests

3. Possible diseases

4. Possible nutrient deficiencies

5. Possible environmental causes

6. Severity:
   Mild, Moderate, or Severe

7. Recommended practical actions

8. What the farmer should monitor next week

9. Confidence level:
   High, Medium, or Low


IMPORTANT:

Do not claim that a diagnosis is certain
when there is insufficient evidence.

Clearly explain uncertainty.

Do not recommend dangerous or illegal
agricultural chemical use.

Where appropriate, recommend consultation
with an agricultural extension officer,
agronomist, or appropriate professional.

Give practical recommendations suitable
for smallholder farmers in South Africa.

Do NOT include sales, financial,
or inventory analysis.

"""


    # ========================================================
    # PREPARE GEMINI CONTENT
    # ========================================================

    contents = [
        prompt_text
    ]


    # ========================================================
    # ADD IMAGE IF AVAILABLE
    # ========================================================

    if image_bytes:

        try:

            image_part = (
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=image_mime_type
                )
            )


            contents.append(
                image_part
            )


            print(
                "--> Crop image added to Gemini analysis."
            )


        except Exception as error:

            print(
                "--> Could not attach image to Gemini:"
            )

            print(
                type(error).__name__,
                str(error)
            )


    # ========================================================
    # CALL GEMINI
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "--> Calling Gemini API..."
    )

    print(
        "=========================================="
    )


    try:

        response = client.models.generate_content(

            model="gemini-3.6-flash",

            contents=contents

        )


        diagnostic_report = (

            response.text

            if response.text

            else

            "Gemini did not return an assessment."

        )


        # ====================================================
        # DISPLAY AI REPORT
        # ====================================================

        print()

        print(
            "=========================================="
        )

        print(
            "       AI REPORT GENERATED"
        )

        print(
            "=========================================="
        )

        print(
            diagnostic_report
        )

        print(
            "=========================================="
        )


        # ====================================================
        # SEND EMAIL
        # ====================================================

        if farmer_email:

            print()

            print(
                "--> Farmer email detected."
            )


            subject_line = (

                "AI Agricultural Assessment - "

                f"{vegetable} "

                f"({site_location})"

            )


            send_advisory_email(

                farmer_email,

                subject_line,

                diagnostic_report

            )


        else:

            print()

            print(
                "=========================================="
            )

            print(
                "       NO FARMER EMAIL FOUND"
            )

            print(
                "=========================================="
            )

            print(
                "The Kobo submission did not contain "
                "a usable email address."
            )


    # ========================================================
    # GEMINI ERROR
    # ========================================================

    except Exception as error:

        print()

        print(
            "=========================================="
        )

        print(
            "          GEMINI PROCESS ERROR"
        )

        print(
            "=========================================="
        )

        print(
            "Error type:",
            type(error).__name__
        )

        print(
            "Error message:",
            str(error)
        )

        print(
            "=========================================="
        )


# ============================================================
# HOME PAGE
# ============================================================

@app.get("/")
def home():

    return {

        "status":
        "Modisha's Agricultural AI Assistant is live!",

        "service":
        "SEF Agricultural AI Assistant"

    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {

        "status": "healthy",

        "gemini_configured":
        bool(GEMINI_API_KEY),

        "email_configured":
        bool(
            SENDER_EMAIL
            and
            SENDER_PASSWORD
        )

    }


# ============================================================
# KOBO WEBHOOK
# ============================================================

@app.post("/webhook")
async def handle_kobo_webhook(
    request: Request
):

    # ========================================================
    # RECEIVE KOBO DATA
    # ========================================================

    try:

        payload = await request.json()

    except Exception:

        raise HTTPException(

            status_code=400,

            detail="Invalid JSON payload"

        )


    # ========================================================
    # CONFIRM KOBO SUBMISSION
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "       KOBO SUBMISSION RECEIVED"
    )

    print(
        "=========================================="
    )


    # ========================================================
    # SHOW PAYLOAD KEYS
    # ========================================================

    print(
        f"Payload keys: "
        f"{list(payload.keys())}"
    )


    # ========================================================
    # START FARM REPORT PROCESS
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "       STARTING FARM REPORT PROCESS"
    )

    print(
        "=========================================="
    )


    try:

        process_farm_report(
            payload
        )


    except Exception as error:

        print()

        print(
            "=========================================="
        )

        print(
            "       FARM REPORT PROCESSING ERROR"
        )

        print(
            "=========================================="
        )

        print(
            "Error type:",
            type(error).__name__
        )

        print(
            "Error message:",
            str(error)
        )

        print(
            "=========================================="
        )


        raise HTTPException(

            status_code=500,

            detail=
            "Farm report processing failed"

        )


    # ========================================================
    # SUCCESS RESPONSE
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "       FARM REPORT PROCESS COMPLETED"
    )

    print(
        "=========================================="
    )


    return {

        "status":
        "success",

        "message":
        "Farm report analysed successfully."

    }
