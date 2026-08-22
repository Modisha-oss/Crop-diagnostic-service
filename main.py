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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")

client = genai.Client(api_key=GEMINI_API_KEY)


def send_advisory_email(to_email: str, subject: str, report_body: str):
    print(f"--> Attempting to send email via SMTP to: {to_email}")
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(report_body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        print(f"--> SUCCESS: Report emailed to {to_email}")
    except Exception as e:
        print(f"--> ERROR: SMTP email failed for {to_email}: {e}")


def process_farm_report(payload: dict):
    print(f"--> Incoming Payload Keys: {list(payload.keys())}")

    # Recursive search to find email regardless of Kobo field names or nested groups
    def find_email(data):
        if isinstance(data, dict):
            for k, v in data.items():
                if "email" in k.lower() and isinstance(v, str) and "@" in v:
                    return v.strip()
                res = find_email(v)
                if res:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = find_email(item)
                if res:
                    return res
        return ""

    farmer_email = find_email(payload)
    
    # Extract diagnostic fields
    site_location = payload.get("site_location") or payload.get("location") or "Turfloop"
    region = payload.get("region") or "Limpopo"
    vegetable = payload.get("vegetable") or payload.get("crop") or "Crop"
    weekly_observation = payload.get("weekly_observation") or payload.get("observations") or payload.get("field_notes") or "No field observations provided."

    print(f"--> Extracted Target Email: '{farmer_email}'")

    # Photo download (failsafe)
    attachments = payload.get("_attachments", [])
    image_bytes = None

    if attachments:
        photo_url = attachments[0].get("download_url")
        if photo_url:
            print(f"--> Downloading photo from: {photo_url}")
            try:
                img_res = requests.get(photo_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if img_res.status_code == 200:
                    image_bytes = img_res.content
                    print("--> Photo download successful!")
                else:
                    print(f"--> Photo status code: {img_res.status_code}")
            except Exception as e:
                print(f"--> Photo download exception: {e}")

    # AI Prompt Construction
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

    print("--> Calling Gemini API...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=contents
        )
        diagnostic_report = response.text

        if farmer_email and SENDER_EMAIL and SENDER_PASSWORD:
            subject_line = f"AI Agricultural Assessment - {vegetable} ({site_location})"
            send_advisory_email(farmer_email, subject_line, diagnostic_report)
        else:
            print(f"--> MISSING EMAIL OR ENV VARS: farmer_email='{farmer_email}', SENDER_EMAIL={bool(SENDER_EMAIL)}, SENDER_PASSWORD={bool(SENDER_PASSWORD)}")

    except Exception as err:
        print(f"--> ERROR during Gemini/Email execution: {err}")


@app.get("/")
def home():
    return {"status": "Modisha's Agricultural AI Assistant is live!"}


@app.post("/webhook")
async def handle_kobo_webhook(
    request: Request, background_tasks: BackgroundTasks
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    background_tasks.add_task(process_farm_report, payload)

    return {
        "status": "success",
        "message": "Submission received and queued for analysis.",
    }
