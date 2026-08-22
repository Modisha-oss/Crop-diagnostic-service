import os
import smtplib
import warnings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from google import genai
from google.genai import types
import requests

# Suppress SDK warnings
warnings.filterwarnings("ignore")

app = FastAPI(title="Modisha's Agricultural AI Assistant")

# Fetch environment variables from Render settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)


def send_advisory_email(to_email: str, subject: str, report_body: str):
    """Sends the AI diagnostic report to the farmer via Gmail SMTP."""
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(report_body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        print(f"--> Diagnostic report emailed successfully to: {to_email}")
    except Exception as e:
        print(f"--> Failed to send email to {to_email}: {e}")


def process_farm_report(payload: dict):
    """
    Extracts ONLY diagnostic data (observations, email, crop type, location/region)
    and ignores stock/sales/inventory metrics.
    """
    def get_field_value(keys_to_search, default=""):
        for key, value in payload.items():
            for k in keys_to_search:
                if k.lower() in key.lower() and value:
                    return str(value).strip()
        return default

    # 1. Target EXACT fields required for AI analysis
    site_location = get_field_value(["site_location", "site", "location"], "Turfloop")
    region = get_field_value(["region", "province"], "Limpopo")
    vegetable = get_field_value(["vegetable", "crop", "produce"], "Crop")
    weekly_observation = get_field_value(["weekly_observation", "observation", "field_notes", "notes"], "No observations provided.")
    farmer_email = get_field_value(["farmer_email", "email", "contact_email"], "")

    print(f"--> Extracted Target Data: Site='{site_location}', Region='{region}', Crop='{vegetable}', Email='{farmer_email}'")

    # 2. Extract Photo Attachment (if present)
    attachments = payload.get("_attachments", [])
    image_bytes = None

    if attachments:
        photo_url = attachments[0].get("download_url")
        if photo_url:
            print("Downloading crop photo from submission...")
            try:
                img_res = requests.get(photo_url, timeout=10)
                if img_res.status_code == 200:
                    image_bytes = img_res.content
            except Exception as e:
                print(f"Failed to fetch photo: {e}")

    # 3. Build Diagnostic Prompt (Excludes sales/inventory data)
    prompt_text = f"""
    You are an agricultural support assistant for smallholder farmers in South Africa.

    Analyze ONLY the following diagnostic report and attached crop image (if provided):

    SITE DETAILS:
    - Site Location: {site_location}
    - Region: {region}

    CROP DETAILS:
    - Crop: {vegetable}

    FIELD OBSERVATION:
    {weekly_observation}

    Provide a practical agricultural report containing:
    1. Possible Causes / Issues
    2. Pests, Diseases, or Nutrient Deficiencies identified
    3. Severity (Mild / Moderate / Severe)
    4. Actionable treatment steps suited for local farming conditions
    5. What the farmer should monitor next week
    6. Confidence Level (High / Medium / Low)

    Do NOT include or analyze sales, financial, or inventory metrics.
    """

    contents = [prompt_text]
    if image_bytes:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        contents.append(image_part)

    print("Generating targeted assessment with Gemini...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=contents
        )
        diagnostic_report = response.text

        # 4. Email the report directly if an email was captured
        if farmer_email and SENDER_EMAIL and SENDER_PASSWORD:
            subject_line = f"AI Agricultural Assessment - {vegetable} ({site_location})"
            send_advisory_email(farmer_email, subject_line, diagnostic_report)
        else:
            print(f"--> Skipping email: farmer_email='{farmer_email}' | SENDER_EMAIL={bool(SENDER_EMAIL)}")

    except Exception as err:
        print(f"Error during AI analysis: {err}")


@app.get("/")
def home():
    return {"status": "Modisha's Agricultural AI Assistant is live!"}


@app.post("/webhook")
async def handle_kobo_webhook(
    request: Request, background_tasks: BackgroundTasks
):
    """Webhook listener that accepts Kobo submissions instantly."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    background_tasks.add_task(process_farm_report, payload)

    return {
        "status": "success",
        "message": "Submission received and queued for analysis.",
    }
