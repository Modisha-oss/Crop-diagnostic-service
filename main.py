import os
import smtplib
import warnings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException, Request
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


@app.get("/")
def home():
    return {"status": "Modisha's Agricultural AI Assistant is live!"}


@app.post("/webhook")
async def handle_kobo_webhook(request: Request):
    """Webhook listener endpoint for incoming KoboToolbox submissions."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 1. Extract dynamic fields from submission
    site_location = payload.get("site_location", "Unknown Location")
    region = payload.get("region", "South Africa")
    vegetable = payload.get("vegetable", "Crop")
    weekly_observation = (
        payload.get("weekly_observation")
        or payload.get("observations")
        or payload.get("field_notes")
        or "No field observations provided."
    )
    farmer_email = payload.get("farmer_email") or payload.get("Farmers_Email")

    # 2. Extract Photo Attachment (if present)
    attachments = payload.get("_attachments", [])
    image_bytes = None

    if attachments:
        photo_url = attachments[0].get("download_url")
        if photo_url:
            print("Downloading crop photo from submission...")
            img_res = requests.get(photo_url)
            if img_res.status_code == 200:
                image_bytes = img_res.content

    # 3. Build Agricultural Prompt
    prompt_text = f"""
    You are an agricultural support assistant helping smallholder farmers in South Africa.

    Analyse the following farm report and attached crop image (if provided):

    SITE INFORMATION:
    - Site: {site_location}
    - Region: {region}

    CROP INFORMATION:
    - Crop: {vegetable}

    FARMER'S WEEKLY OBSERVATION:
    {weekly_observation}

    Please provide a practical agricultural assessment including:
    1. Possible causes
    2. Possible pests
    3. Possible diseases
    4. Possible nutrient deficiencies
    5. Possible environmental causes
    6. Severity of the problem (Mild / Moderate / Severe)
    7. Recommended actionable treatment steps
    8. What the farmer should monitor
    9. Confidence level (High / Medium / Low)

    IMPORTANT:
    - Do not claim that a diagnosis is certain when there is insufficient information.
    - Clearly explain uncertainty.
    - Give practical recommendations suitable for smallholder farmers in South Africa.
    - Do not recommend dangerous or excessive chemical applications without sufficient evidence.
    """

    # Assemble multimodal content list
    contents = [prompt_text]
    if image_bytes:
        image_part = types.Part.from_bytes(
            data=image_bytes, mime_type="image/jpeg"
        )
        contents.append(image_part)

    # 4. Generate AI Assessment
    print("Generating assessment with Gemini 2.5 Flash...")
    response = client.models.generate_content(
        model="gemini-3.6-flash", contents=contents
    )

    diagnostic_report = response.text

    # 5. Email Report dynamically if email exists
    if farmer_email and SENDER_EMAIL and SENDER_PASSWORD:
        subject_line = f"AI Agricultural Assessment - {vegetable} ({site_location})"
        send_advisory_email(farmer_email, subject_line, diagnostic_report)

    return {
        "status": "success",
        "site": site_location,
        "email_sent_to": farmer_email,
        "report": diagnostic_report,
    }
