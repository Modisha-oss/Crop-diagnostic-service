import os
import time
import warnings
import requests
import resend

from fastapi import FastAPI, HTTPException, Request

from google import genai
from google.genai import types

from groq import Groq
from supabase import create_client, Client


# ============================================================
# SUPPRESS NON-CRITICAL WARNINGS
# ============================================================

warnings.filterwarnings("ignore")


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Modisha's Agricultural AI Assistant (Groq, Gemini, RunPod & Supabase)",
    version="1.8"
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

KOBO_TOKEN = os.environ.get("KOBO_TOKEN")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

SUPABASE_URL = os.environ.get("SUPABASE_URL")

SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

RUNPOD_TEXT_URL = os.environ.get("RUNPOD_TEXT_URL")

SENDER_EMAIL = os.environ.get(
    "SENDER_EMAIL", 
    "Modisha Crop Diagnostics <reports@modisha-agri.co.za>"
)


# ============================================================
# CLIENT INITIALIZATIONS
# ============================================================

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None
    print("WARNING: GROQ_API_KEY is missing.")


if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    gemini_client = None
    print("WARNING: GEMINI_API_KEY is missing.")


if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
else:
    print("WARNING: RESEND_API_KEY is missing.")


if SUPABASE_URL and SUPABASE_KEY:
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase_client = None
    print("WARNING: SUPABASE_URL or SUPABASE_KEY is missing.")


# ============================================================
# HELPER: FLATTEN NESTED KOBO PAYLOAD
# ============================================================

def flatten_kobo_payload(payload_dict, parent_key=''):
    """
    Recursively flattens KoboToolbox payloads (including nested groups like site_issues)
    so field names like 'site_issues/weekly_observation' can be matched exactly.
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
# HELPER: SANITIZE KOBO EMAIL ADDRESS
# ============================================================

def sanitize_email(raw_val: str) -> str:
    if not raw_val or not isinstance(raw_val, str):
        return ""
    
    val = raw_val.strip()

    if "@" in val and "." in val:
        return val

    if "_gmail_com" in val:
        val = val.replace("_gmail_com", "@gmail.com")
    elif "_yahoo_com" in val:
        val = val.replace("_yahoo_com", "@yahoo.com")
    elif "_outlook_com" in val:
        val = val.replace("_outlook_com", "@outlook.com")
    else:
        parts = val.rsplit('_', 2)
        if len(parts) == 3:
            val = f"{parts[0]}@{parts[1]}.{parts[2]}"

    return val


# ============================================================
# SAVE TO SUPABASE DATABASE
# ============================================================

def save_report_to_supabase(
    sender_email: str,
    site_name: str,
    region_location: str,
    date_planted: str,
    soil_type: str,
    seedling_crop_type: str,
    weekly_observation: str,
    diagnostic_report: str,
    ai_engine_used: str,
    status: str = "resolved"
):

    print()
    print("==========================================")
    print("       SUPABASE DATABASE SAVE STARTED")
    print("==========================================")

    if not supabase_client:
        print("WARNING: Supabase client is not configured. Skipping database record insertion.")
        return

    try:
        print("--> Inserting diagnostic record into Supabase table 'crop_reports'...")

        data = {
            "farmer_email": sender_email,
            "site_name": site_name,
            "region_location": region_location,
            "date_planted": date_planted,
            "soil_type": soil_type,
            "crop_type": seedling_crop_type,
            "observation": weekly_observation,
            "diagnostic_report": diagnostic_report,
            "ai_engine": ai_engine_used,
            "status": status
        }

        response = supabase_client.table("crop_reports").insert(data).execute()

        print()
        print("==========================================")
        print("     SUPABASE RECORD SAVED SUCCESSFUL!")
        print("==========================================")
        print("Record Data:", response.data)

    except Exception as error:
        print()
        print("==========================================")
        print("      SUPABASE RECORD SAVE ERROR")
        print("==========================================")
        print("Error type:", type(error).__name__)
        print("Error message:", str(error))
        print("==========================================")


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
    print("          EMAIL PROCESS STARTED")
    print("==========================================")

    clean_email = str(to_email).strip().lower()

    print(f"Recipient Email: {clean_email}")
    print(f"Sender Email: {SENDER_EMAIL}")

    if not RESEND_API_KEY:
        print("ERROR: RESEND_API_KEY is missing from Environment Variables.")
        return

    if not clean_email or "@" not in clean_email:
        print("ERROR: Recipient email is invalid or empty. Skipping dispatch.")
        return

    try:
        print("--> Dispatching email via Resend...")

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
        print(f"Email ID: {response.get('id')}")

    except Exception as error:
        print()
        print("==========================================")
        print("          EMAIL DISPATCH ERROR")
        print("==========================================")
        print("Error type:", type(error).__name__)
        print("Error message:", str(error))
        print("==========================================")


# ============================================================
# DOWNLOAD KOBO MEDIA FUNCTION
# ============================================================

def download_kobo_media(download_url: str):

    print()
    print("==========================================")
    print("        KOBO MEDIA DOWNLOAD STARTED")
    print("==========================================")
    print(f"Download URL: {download_url}")

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
            print("--> Kobo image download successful!")
            print(f"--> MIME type: {content_type}")
            return res.content, content_type
        else:
            print(f"--> Failed to download Kobo media. HTTP {res.status_code}")
            return None, "image/jpeg"

    except Exception as error:
        print("--> Exception occurred while downloading Kobo media:")
        print(type(error).__name__, str(error))
        return None, "image/jpeg"


# ============================================================
# GENERATE REPORT WITH GROQ
# ============================================================

def generate_report_groq(prompt_text: str):

    if not groq_client:
        print("--> Groq client not configured. Skipping Groq execution.")
        return None

    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            print(f"--> Calling Groq API (Attempt {attempt}/{max_retries})...")

            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an agricultural AI diagnostic assistant helping smallholder farmers."
                    },
                    {
                        "role": "user",
                        "content": prompt_text,
                    }
                ],
                model="llama-3.1-8b-instant",
                temperature=0.3
            )

            if chat_completion and chat_completion.choices:
                return chat_completion.choices[0].message.content

        except Exception as error:
            print(f"--> Groq attempt {attempt} failed: {error}")
            if attempt < max_retries:
                sleep_time = attempt * 2
                print(f"--> Waiting {sleep_time}s before retrying Groq...")
                time.sleep(sleep_time)

    return None


# ============================================================
# GENERATE REPORT WITH GEMINI (FALLBACK)
# ============================================================

def generate_report_gemini(prompt_text: str, image_parts: list):

    if not gemini_client:
        print("--> Gemini client not configured. Skipping Gemini execution.")
        return None

    contents = [prompt_text] + image_parts
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            print(f"--> Calling Gemini API (Attempt {attempt}/{max_retries})...")

            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents
            )

            if response and response.text:
                return response.text

        except Exception as error:
            print(f"--> Gemini attempt {attempt} failed: {error}")
            if attempt < max_retries:
                sleep_time = attempt * 2
                print(f"--> Waiting {sleep_time}s before retrying Gemini...")
                time.sleep(sleep_time)

    return None


# ============================================================
# GENERATE REPORT WITH RUNPOD MODISHA ENGINE (FINAL FALLBACK)
# ============================================================

def generate_report_runpod(prompt_text: str):
    """
    Calls the custom Modisha-Engine text model hosted on RunPod using the dynamic proxy URL.
    """
    if not RUNPOD_TEXT_URL:
        print("--> RunPod URL (RUNPOD_TEXT_URL) not configured. Skipping RunPod execution.")
        return None

    # Ensure proxy endpoint targets chat completions path correctly
    base_url = RUNPOD_TEXT_URL.strip()
    if not base_url.endswith("/v1/chat/completions"):
        endpoint_url = base_url.rstrip("/") + "/v1/chat/completions"
    else:
        endpoint_url = base_url

    payload = {
        "model": "Qwen/Qwen3-0.6B",
        "messages": [
            {
                "role": "system",
                "content": "You are Modisha-Agri-Engine, an expert agricultural advisor analyzing field observations."
            },
            {
                "role": "user",
                "content": prompt_text
            }
        ],
        "max_tokens": 400,
        "temperature": 0.7
    }

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            print(f"--> Calling RunPod Modisha-Engine (Attempt {attempt}/{max_retries}): {endpoint_url}")
            # verify=False bypassed for mobile network & self-signed runpod proxy certs
            response = requests.post(endpoint_url, json=payload, verify=False, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
            else:
                print(f"--> RunPod returned status code {response.status_code}")
        except Exception as error:
            print(f"--> RunPod attempt {attempt} failed: {error}")
            if attempt < max_retries:
                time.sleep(2)

    return None


# ============================================================
# PROCESS FARM REPORT
# ============================================================

def process_farm_report(payload: dict):

    print()
    print("==========================================")
    print("         NEW FARM REPORT RECEIVED")
    print("==========================================")

    flat_payload = flatten_kobo_payload(payload)

    sender_email = ""
    site_name = "Not specified"
    region_location = "Not specified"
    date_planted = "Not specified"
    soil_type = "Not specified"
    seedling_crop_type = "Not specified"
    weekly_observation = "No text observation provided."
    image_parts = []

    # --------------------------------------------------------
    # STRICT SUFFIX EXTRACTION FOR EXACT FIELD MATCHING
    # --------------------------------------------------------

    for key, val in flat_payload.items():
        if not val or not isinstance(val, str):
            continue

        k_lower = key.lower()

        # 1. Email Address
        if k_lower.endswith("farmer_email") or k_lower.endswith("email"):
            sender_email = sanitize_email(val)

        # 2. Weekly Observation
        elif k_lower.endswith("weekly_observation") or k_lower.endswith("observation") or k_lower.endswith("issue_description"):
            weekly_observation = val.strip()

        # 3. Site Name
        elif k_lower.endswith("site_name") or k_lower.endswith("farm_name"):
            site_name = val.strip()

        # 4. Region / Location
        elif k_lower.endswith("location") or k_lower.endswith("region") or k_lower.endswith("province"):
            region_location = val.strip()

        # 5. Soil Type
        elif k_lower.endswith("soil_type") or k_lower.endswith("soil"):
            soil_type = val.strip()

        # 6. Crop / Seedling Type
        elif k_lower.endswith("seedling_crop_type") or k_lower.endswith("crop_type") or k_lower.endswith("seedling"):
            seedling_crop_type = val.strip()

        # 7. Date Planted
        elif "date" in k_lower or "planted" in k_lower:
            date_planted = val.strip()

    # Fallback to GPS if location is still default
    if region_location == "Not specified" and "_geolocation" in payload:
        geo = payload.get("_geolocation")
        if geo and isinstance(geo, list) and len(geo) >= 2:
            region_location = f"GPS: {geo[0]}, {geo[1]}"

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

    # --------------------------------------------------------
    # CREATE AI PROMPT
    # --------------------------------------------------------

    prompt_text = f"""
You are an agricultural expert helping smallholder farmers in South Africa.

Analyze the following site issue report, soil parameters, and crop data.

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
1. Primary Issue / Pests / Diseases identified based on the observation data
2. Severity Rating (Mild, Moderate, or Severe)
3. Region-Specific Advisory & Practical Actions for the Farmer at {site_name} (taking into account the soil type: {soil_type} and crop: {seedling_crop_type})
4. Preventative Measures & Next Week Monitoring
5. Confidence Level
"""

    # --------------------------------------------------------
    # AI EXECUTION ENGINE (GROQ -> GEMINI -> RUNPOD -> QUEUE)
    # --------------------------------------------------------

    diagnostic_report = None
    ai_engine_used = ""
    submission_status = "resolved"

    # Tier 1: Groq AI
    diagnostic_report = generate_report_groq(prompt_text)
    if diagnostic_report:
        ai_engine_used = "Groq (llama-3.1-8b-instant)"
    else:
        print("--> Groq engine failed or unavailable. Falling back to Gemini...")
        
        # Tier 2: Gemini AI
        diagnostic_report = generate_report_gemini(prompt_text, image_parts)
        if diagnostic_report:
            ai_engine_used = "Gemini (gemini-3.6-flash)"
        else:
            print("--> Gemini engine failed or offline. Falling back to RunPod Modisha-Engine...")

            # Tier 3: RunPod Text Engine
            diagnostic_report = generate_report_runpod(prompt_text)
            if diagnostic_report:
                ai_engine_used = "RunPod (Qwen/Qwen3-0.6B)"
            else:
                # Tier 4: Safety Net (All Automated Engines Offline -> Save as Pending)
                print("--> ALL automated models are offline. Saving submission to Supabase as pending review.")
                submission_status = "pending_manual_review"
                diagnostic_report = "Report generation delayed. All automated AI models are currently offline. Your submission has been securely queued for manual processing once the RunPod engine is started."
                ai_engine_used = "Queued for Manual Review"

    # --------------------------------------------------------
    # REPORT DISPATCH & DATABASE PERSISTENCE
    # --------------------------------------------------------

    if diagnostic_report:
        print()
        print("==========================================")
        print("         AI REPORT PROCESSED")
        print("==========================================")
        print(f"Engine Used / Status: {ai_engine_used} [{submission_status}]")
        print("------------------------------------------")
        print(diagnostic_report)
        print("==========================================")

        # 1. SAVE TO SUPABASE
        save_report_to_supabase(
            sender_email=sender_email,
            site_name=site_name,
            region_location=region_location,
            date_planted=date_planted,
            soil_type=soil_type,
            seedling_crop_type=seedling_crop_type,
            weekly_observation=weekly_observation,
            diagnostic_report=diagnostic_report,
            ai_engine_used=ai_engine_used,
            status=submission_status
        )

        # 2. DISPATCH REPORT VIA EMAIL (Only if successfully generated immediately)
        if sender_email and submission_status == "resolved":
            send_email_message(
                sender_email,
                site_name,
                region_location,
                soil_type,
                seedling_crop_type,
                diagnostic_report
            )
        else:
            print("INFO: Submission queued or no valid email. Skipping direct email dispatch until processed.")


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def home():
    return {
        "status": "Live",
        "service": "Modisha's Agricultural AI Assistant (Groq, Gemini, RunPod & Supabase)"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "groq_configured": bool(GROQ_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
        "resend_configured": bool(RESEND_API_KEY),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "runpod_configured": bool(RUNPOD_TEXT_URL),
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
        "message": "Kobo submission processed through multi-tier fallback pipeline."
    }


@app.post("/process-queue")
def process_pending_queue():
    """
    SWITCH BUTTON / ENDPOINT: Click or trigger this after spinning up your RunPod pod 
    to automatically analyze all pending submissions, generate reports, update Supabase, and email farmers.
    """
    if not supabase_client:
        raise HTTPException(status_code=500, detail="Supabase client is not configured.")
    
    if not RUNPOD_TEXT_URL:
        raise HTTPException(status_code=400, detail="RunPod URL (RUNPOD_TEXT_URL) is missing. Update Render environment variables first.")

    try:
        # Fetch pending items from Supabase
        res = supabase_client.table("crop_reports").select("*").eq("status", "pending_manual_review").execute()
        pending_records = res.data

        if not pending_records:
            return {"status": "success", "message": "Queue is empty. No pending submissions found."}

        processed_count = 0
        for item in pending_records:
            record_id = item.get("id")
            site_name = item.get("site_name")
            region_location = item.get("region_location")
            soil_type = item.get("soil_type")
            crop_type = item.get("crop_type")
            weekly_observation = item.get("observation")
            farmer_email = item.get("farmer_email")
            date_planted = item.get("date_planted", "Not specified")

            # Rebuild prompt for the RunPod model
            prompt_text = f"""
You are an agricultural expert helping smallholder farmers in South Africa.
Analyze the following site issue report, soil parameters, and crop data.

SITE / FARM NAME: {site_name}
DATE PLANTED: {date_planted}
SOIL TYPE: {soil_type}
SEEDLING/CROP TYPE: {crop_type}
FARM LOCATION / REGION: {region_location}
FIELD OBSERVATION / ISSUE REPORTED: {weekly_observation}

TASK:
Provide a comprehensive agricultural assessment. 
Reference the site name ({site_name}) and tailor your diagnostic advice specifically to {region_location} in South Africa.
"""

            # Generate report using active RunPod instance
            report = generate_report_runpod(prompt_text)

            if report:
                ai_engine_used = "RunPod (Qwen/Qwen3-0.6B) [Queued Batch]"
                
                # Update Supabase record status to resolved
                supabase_client.table("crop_reports").update({
                    "diagnostic_report": report,
                    "ai_engine": ai_engine_used,
                    "status": "resolved"
                }).eq("id", record_id).execute()

                # Dispatch email to farmer now that report is generated
                if farmer_email:
                    send_email_message(
                        to_email=farmer_email,
                        site_name=site_name,
                        region_location=region_location,
                        soil_type=soil_type,
                        seedling_crop_type=crop_type,
                        diagnostic_report=report
                    )

                processed_count += 1

        return {
            "status": "success", 
            "message": f"Successfully processed {processed_count} pending submissions using the RunPod engine."
        }

    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Error processing queue: {str(error)}")
