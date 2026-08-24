import os
import warnings
import requests

from fastapi import FastAPI, HTTPException, Query, Request, Response

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

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")

WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")

WHATSAPP_VERIFY_TOKEN = os.environ.get(
    "WHATSAPP_VERIFY_TOKEN", 
    "modisha_agri_webhook_pass"
)

KOBO_TOKEN = os.environ.get("KOBO_TOKEN")


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
# SEND WHATSAPP MESSAGE FUNCTION
# ============================================================

def send_whatsapp_message(
    to_phone_number: str,
    message_text: str
):

    print()
    print("==========================================")
    print("        WHATSAPP OUTBOUND PROCESS STARTED")
    print("==========================================")

    # Clean up phone number format (ensure no leading + or spaces)
    clean_phone = str(to_phone_number).strip().replace("+", "").replace(" ", "")

    print(
        f"Recipient: {clean_phone}"
    )

    print(
        f"WhatsApp Token configured: "
        f"{bool(WHATSAPP_TOKEN)}"
    )

    print(
        f"WhatsApp Phone ID configured: "
        f"{bool(WHATSAPP_PHONE_ID)}"
    )


    # --------------------------------------------------------
    # CHECK WHATSAPP CONFIGURATION
    # --------------------------------------------------------

    if not WHATSAPP_TOKEN:

        print(
            "ERROR: WHATSAPP_TOKEN is missing "
            "from Render Environment Variables."
        )

        return


    if not WHATSAPP_PHONE_ID:

        print(
            "ERROR: WHATSAPP_PHONE_ID is missing "
            "from Render Environment Variables."
        )

        return


    if not clean_phone:

        print(
            "ERROR: Recipient phone number is empty."
        )

        return


    # --------------------------------------------------------
    # PREPARE WHATSAPP API REQUEST
    # --------------------------------------------------------

    url = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }


    # --------------------------------------------------------
    # SEND WHATSAPP MESSAGE
    # --------------------------------------------------------

    try:

        print(
            "--> Sending WhatsApp reply via Graph API..."
        )

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )


        if response.status_code == 200:

            print()
            print("==========================================")
            print("     WHATSAPP MESSAGE SENT SUCCESSFULLY!")
            print("==========================================")

            print(
                f"Message sent to: {clean_phone}"
            )

        else:

            print()
            print("==========================================")
            print("       WHATSAPP API ERROR RESPONSE")
            print("==========================================")

            print(
                f"HTTP Status: {response.status_code}"
            )

            print(
                f"Response body: {response.text}"
            )


    # --------------------------------------------------------
    # WHATSAPP API EXCEPTION
    # --------------------------------------------------------

    except Exception as error:

        print()
        print("==========================================")
        print("          WHATSAPP SEND ERROR")
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
# DOWNLOAD META MEDIA FUNCTION
# ============================================================

def download_meta_media(media_id: str):

    print()
    print("==========================================")
    print("       META MEDIA DOWNLOAD STARTED")
    print("==========================================")

    print(
        f"Media ID: {media_id}"
    )


    if not WHATSAPP_TOKEN:

        print(
            "ERROR: WHATSAPP_TOKEN is missing for media download."
        )

        return None, "image/jpeg"


    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }


    try:

        meta_url = f"https://graph.facebook.com/v20.0/{media_id}"

        res = requests.get(
            meta_url,
            headers=headers,
            timeout=30
        )


        if res.status_code != 200:

            print(
                f"--> Failed to fetch media URL. HTTP {res.status_code}"
            )

            return None, "image/jpeg"


        media_data = res.json()

        download_url = media_data.get("url")

        mime_type = media_data.get("mime_type", "image/jpeg")


        if not download_url:

            print(
                "--> Download URL not found in Meta response."
            )

            return None, mime_type


        print(
            f"--> Downloading media binary content..."
        )

        media_res = requests.get(
            download_url,
            headers=headers,
            timeout=30
        )


        if media_res.status_code == 200:

            print(
                "--> Media download successful!"
            )

            return media_res.content, mime_type

        else:

            print(
                f"--> Binary download failed. HTTP {media_res.status_code}"
            )

            return None, mime_type


    except Exception as error:

        print(
            "--> Exception occurred while downloading media:"
        )

        print(
            type(error).__name__,
            str(error)
        )

        return None, "image/jpeg"


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


    # ========================================================
    # DETECT SOURCE & PARSE PAYLOAD
    # ========================================================

    source = "UNKNOWN"

    sender_phone = ""

    weekly_observation = "No text observation provided."

    image_bytes = None

    image_mime_type = "image/jpeg"


    # --------------------------------------------------------
    # 1. CHECK IF WHATSAPP CLOUD API PAYLOAD
    # --------------------------------------------------------

    if "entry" in payload and isinstance(payload["entry"], list):

        source = "WHATSAPP"

        try:

            entry = payload["entry"][0]

            changes = entry["changes"][0]

            value = changes["value"]

            messages = value.get("messages", [])


            if not messages:

                print(
                    "--> WhatsApp status update received (no message body)."
                )

                return


            message = messages[0]

            sender_phone = message.get("from", "")

            msg_type = message.get("type", "")


            if msg_type == "text":

                weekly_observation = message.get("text", {}).get("body", "")

            elif msg_type == "image":

                image_obj = message.get("image", {})

                weekly_observation = image_obj.get("caption", "Uploaded crop image.")

                media_id = image_obj.get("id")


                if media_id:

                    image_bytes, image_mime_type = download_meta_media(media_id)


        except (KeyError, IndexError) as parse_error:

            print(
                "--> WhatsApp parsing error:",
                str(parse_error)
            )

            return


    # --------------------------------------------------------
    # 2. CHECK IF KOBOTOOLBOX PAYLOAD
    # --------------------------------------------------------

    else:

        source = "KOBO"

        # Dynamically search for phone number field in Kobo payload
        for key, val in payload.items():

            if "phone" in key.lower() or "mobile" in key.lower() or "contact" in key.lower():

                if val:

                    sender_phone = str(val)

                    break


        # Dynamically search for observation text
        for key, val in payload.items():

            if "observation" in key.lower() or "note" in key.lower() or "issue" in key.lower() or "description" in key.lower():

                if val and isinstance(val, str):

                    weekly_observation = val

                    break


        # Extract image attachments from Kobo
        attachments = payload.get("_attachments", [])

        if attachments and isinstance(attachments, list):

            for attachment in attachments:

                download_url = attachment.get("download_url")

                if download_url:

                    image_bytes, image_mime_type = download_kobo_media(download_url)

                    if image_bytes:

                        break


    # ========================================================
    # DISPLAY EXTRACTED INFORMATION
    # ========================================================

    print()
    print(
        "------------------------------------------"
    )

    print(
        f"Source: {source}"
    )

    print(
        f"Sender Phone: {sender_phone}"
    )

    print(
        f"Observation: {weekly_observation}"
    )

    print(
        f"Has Image Bytes: {bool(image_bytes)}"
    )

    print(
        "------------------------------------------"
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

            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_mime_type
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
            "         AI REPORT GENERATED"
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
        # SEND WHATSAPP MESSAGE TO FARMER
        # ====================================================

        if sender_phone:

            print()

            print(
                f"--> Valid phone number detected ({sender_phone}). Dispatching WhatsApp report..."
            )

            send_whatsapp_message(
                sender_phone,
                diagnostic_report
            )

        else:

            print()

            print(
                "=========================================="
            )

            print(
                "  NO SENDER PHONE FOUND IN REPORT SUBMISSION"
            )

            print(
                "=========================================="
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
            "           GEMINI PROCESS ERROR"
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

        "whatsapp_configured":
        bool(
            WHATSAPP_TOKEN
            and
            WHATSAPP_PHONE_ID
        ),

        "kobo_configured":
        bool(KOBO_TOKEN)

    }


# ============================================================
# WHATSAPP VERIFICATION WEBHOOK (GET)
# ============================================================

@app.get("/webhook/whatsapp")
@app.get("/webhook")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):

    print()
    print("==========================================")
    print("     WHATSAPP WEBHOOK VERIFICATION REQUEST")
    print("==========================================")


    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:

        print(
            "--> Verification successful! Returning hub.challenge..."
        )

        return Response(
            content=hub_challenge, 
            media_type="text/plain"
        )


    print(
        "--> Verification failed: token mismatch or invalid mode."
    )

    raise HTTPException(
        status_code=403, 
        detail="Verification failed"
    )


# ============================================================
# UNIFIED INBOUND WEBHOOK (POST)
# Accepts both KoboToolbox and WhatsApp Submissions
# ============================================================

@app.post("/webhook/kobo")
@app.post("/webhook/whatsapp")
@app.post("/webhook")
async def handle_inbound_webhook(
    request: Request
):

    # ========================================================
    # RECEIVE DATA
    # ========================================================

    try:

        payload = await request.json()

    except Exception:

        raise HTTPException(

            status_code=400,

            detail="Invalid JSON payload"

        )


    # ========================================================
    # CONFIRM SUBMISSION
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "       INBOUND SUBMISSION RECEIVED"
    )

    print(
        "=========================================="
    )


    # ========================================================
    # START FARM REPORT PROCESS
    # ========================================================

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
            "        FARM REPORT PROCESSING ERROR"
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

    return {

        "status":
        "success",

        "message":
        "Farm report processed successfully."

    }
