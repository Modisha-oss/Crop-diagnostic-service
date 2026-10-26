import os
import time
import json
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
    version="1.9"
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
# HELPER: FLATTEN PAYLOAD (KOBO & JOTFORM COMPATIBLE)
# ============================================================

def flatten_kobo_payload(payload_dict, parent_key=''):
    """
    Recursively flattens KoboToolbox and Jotform payloads
    so nested groups and unique field names can be matched easily.
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
# HELPER: SAFE JOTFORM WIDGET LIST PARSER
# ============================================================

def parse_jotform_list(val):
    """Safely parses Jotform Configurable List data whether it arrives as a list, dict, or JSON string."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") or val.startswith("{"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict):
                    return [parsed]
            except:
                pass
    return []


# ============================================================
# HELPER: SANITIZE EMAIL ADDRESS
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
# SAVE TO SUPABASE DATABASE (SITE ISSUES)
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
    print("        SUPABASE DATABASE SAVE STARTED")
    print("==========================================")

    if not supabase_client:
        print("WARNING: Supabase client is not configured. Skipping database record insertion.")
        return

    try:
        print("--> Inserting diagnostic record into Supabase table 'farm_reports'...")

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

        response = supabase_client.table("farm_reports").insert(data).execute()

        print()
        print("==========================================")
        print("     SUPABASE RECORD SAVED SUCCESSFUL!")
        print("==========================================")
        print("Record Data:", response.data)

    except Exception as error:
        print()
        print("==========================================")
        print("       SUPABASE RECORD SAVE ERROR")
        print("==========================================")
        print("Error type:", type(error).__name__)
        print("Error message:", str(error))
        print("==========================================")


# ============================================================
# SAVE WEEKLY REPORT TO RELATIONAL SUPABASE TABLES
# ============================================================

def save_weekly_report_to_supabase(payload: dict):
    print()
    print("==========================================")
    print("    WEEKLY REPORT SUPABASE SAVE STARTED")
    print("==========================================")

    if not supabase_client:
        print("WARNING: Supabase client is not configured. Skipping weekly report storage.")
        return

    try:
        flat_payload = flatten_kobo_payload(payload)

        site_location = "Not specified"
        region = "Not specified"

        for key, val in flat_payload.items():
            if not val or not isinstance(val, str):
                continue
            k_lower = key.lower()
            if "site_location" in k_lower or "site_name" in k_lower or "farm_name" in k_lower:
                site_location = val.strip()
            elif ("region" in k_lower or "location" in k_lower or "province" in k_lower) and "site" not in k_lower:
                region = val.strip()

        # 1. Insert Main Weekly Site Report
        main_report_data = {
            "site_location": site_location,
            "region": region
        }

        main_res = supabase_client.table("weekly_site_reports").insert(main_report_data).execute()

        if not main_res.data:
            print("--> Failed to create main weekly report record.")
            return

        report_id = main_res.data[0]["id"]
        print(f"--> Main weekly report created with ID: {report_id}")

        def extract_all_lists(data):
            found_lists = []
            if isinstance(data, list):
                found_lists.append(data)
                for item in data:
                    found_lists.extend(extract_all_lists(item))
            elif isinstance(data, dict):
                for k, v in data.items():
                    found_lists.extend(extract_all_lists(v))
            return found_lists

        all_payload_lists = extract_all_lists(payload)

        seedling_records = []
        donation_records = []
        sales_records = []

        for lst_raw in all_payload_lists:
            lst = parse_jotform_list(lst_raw)
            for item in lst:
                if isinstance(item, dict):
                    f_item = flatten_kobo_payload(item)
                    keys_string = " ".join([str(k).lower() for k in f_item.keys()])

                    # Check for Seedlings
                    if any(kw in keys_string for kw in ["seedling", "quantity_received", "qty_received"]):
                        receipt_date, seedlings_type, qty = "Not specified", "Not specified", 0
                        for k, v in f_item.items():
                            kl = k.lower()
                            if "date" in kl:
                                receipt_date = str(v)
                            elif "seedling" in kl or "type" in kl:
                                seedlings_type = str(v)
                            elif "quantity" in kl or "qty" in kl:
                                try:
                                    qty = int(v)
                                except:
                                    qty = 0
                        seedling_records.append({
                            "report_id": report_id,
                            "receipt_date": receipt_date,
                            "seedlings_type": seedlings_type,
                            "quantity_received": qty
                        })

                    # Check for Donations
                    elif any(kw in keys_string for kw in ["donation", "donated", "beneficiary", "organization", "contact"]):
                        d_date, veg_type, qty_donated, orgs, org_name, direct_b, contacts, indirect_b = "Not specified", "Not specified", 0.0, "", "", 0, "", 0
                        for k, v in f_item.items():
                            kl = k.lower()
                            if "date" in kl:
                                d_date = str(v)
                            elif "vegetable" in kl or "veg" in kl:
                                veg_type = str(v)
                            elif "quantity_donated" in kl or "qunatity_donated" in kl:
                                try:
                                    qty_donated = float(v)
                                except:
                                    qty_donated = 0.0
                            elif "organizations" in kl and "name" not in kl:
                                orgs = str(v)
                            elif "name_of_organization" in kl or "name_of_orgainzation" in kl:
                                org_name = str(v)
                            elif "direct_beneficiary" in kl:
                                try:
                                    direct_b = int(v)
                                except:
                                    direct_b = 0
                            elif "contact" in kl:
                                contacts = str(v)
                            elif "indirect_beneficiary" in kl:
                                try:
                                    indirect_b = int(v)
                                except:
                                    indirect_b = 0
                        donation_records.append({
                            "report_id": report_id,
                            "donation_date": d_date,
                            "vegetable_type": veg_type,
                            "quantity_donated": qty_donated,
                            "organizations": orgs,
                            "name_of_organization": org_name,
                            "direct_beneficiaries": direct_b,
                            "contact_numbers": contacts,
                            "indirect_beneficiaries": indirect_b
                        })

                    # Check for Sales
                    elif any(kw in keys_string for kw in ["sold", "unit_price", "sales_date"]):
                        s_date, veg_type, qty_sold, unit_price = "Not specified", "Not specified", 0.0, 0.0
                        for k, v in f_item.items():
                            kl = k.lower()
                            if "date" in kl:
                                s_date = str(v)
                            elif "vegetable" in kl or "vegatable" in kl:
                                veg_type = str(v)
                            elif "quantity_sold" in kl:
                                try:
                                    qty_sold = float(v)
                                except:
                                    qty_sold = 0.0
                            elif "unit_price" in kl:
                                try:
                                    unit_price = float(v)
                                except:
                                    unit_price = 0.0
                        sales_records.append({
                            "report_id": report_id,
                            "sales_date": s_date,
                            "vegetable_type": veg_type,
                            "quantity_sold": qty_sold,
                            "unit_price": unit_price
                        })

        if seedling_records:
            supabase_client.table("weekly_seedlings_received").insert(seedling_records).execute()
            print(f"--> Inserted {len(seedling_records)} seedling records.")
        if donation_records:
            supabase_client.table("weekly_site_donations").insert(donation_records).execute()
            print(f"--> Inserted {len(donation_records)} donation records.")
        if sales_records:
            supabase_client.table("weekly_site_sales").insert(sales_records).execute()
            print(f"--> Inserted {len(sales_records)} sales records.")

        print("==========================================")
        print("    WEEKLY REPORT SAVED SUCCESSFULLY!")
        print("==========================================")

    except Exception as error:
        print("==========================================")
        print("     WEEKLY REPORT SUPABASE SAVE ERROR")
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
# DOWNLOAD MEDIA FUNCTION (KOBO & JOTFORM)
# ============================================================

def download_kobo_media(download_url: str):

    print()
    print("==========================================")
    print("        MEDIA DOWNLOAD STARTED")
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
            print("--> Image download successful!")
            print(f"--> MIME type: {content_type}")
            return res.content, content_type
        else:
            print(f"--> Failed to download media. HTTP {res.status_code}")
            return None, "image/jpeg"

    except Exception as error:
        print("--> Exception occurred while downloading media:")
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
# PROCESS FARM REPORT (SITE ISSUES)
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

    for key, val in flat_payload.items():
        if val is None:
            continue
        val_str = str(val).strip()
        k_lower = key.lower()

        if "email" in k_lower:
            sender_email = sanitize_email(val_str)
        elif "observation" in k_lower or "description" in k_lower or "issue" in k_lower:
            weekly_observation = val_str
        elif "site_name" in k_lower or "farm_name" in k_lower:
            site_name = val_str
        elif ("location" in k_lower or "region" in k_lower or "province" in k_lower) and "site" not in k_lower:
            region_location = val_str
        elif "soil" in k_lower:
            soil_type = val_str
        elif "crop" in k_lower or "seedling" in k_lower:
            seedling_crop_type = val_str
        elif "date" in k_lower or "planted" in k_lower:
            date_planted = val_str

    if region_location == "Not specified" and "_geolocation" in payload:
        geo = payload.get("_geolocation")
        if geo and isinstance(geo, list) and len(geo) >= 2:
            region_location = f"GPS: {geo[0]}, {geo[1]}"

    # Extract attached images from Jotform or Kobo
    def extract_image_urls(data):
        urls = []
        if isinstance(data, list):
            for item in data:
                urls.extend(extract_image_urls(item))
        elif isinstance(data, dict):
            for k, v in data.items():
                if "image" in str(k).lower() or "file" in str(k).lower() or isinstance(v, (list, dict)):
                    urls.extend(extract_image_urls(v))
                elif isinstance(v, str) and (v.startswith("http://") or v.startswith("https://")) and any(ext in v.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    urls.append(v)
        return urls

    image_urls = extract_image_urls(payload)
    attachments = payload.get("_attachments", [])
    if isinstance(attachments, list):
        for att in attachments:
            url = att.get("download_url")
            if url:
                image_urls.append(url)

    for url in image_urls:
        img_bytes, img_mime = download_kobo_media(url)
        if img_bytes:
            try:
                part = types.Part.from_bytes(data=img_bytes, mime_type=img_mime)
                image_parts.append(part)
                print(f"--> Successfully prepared image attachment {len(image_parts)}")
            except Exception as error:
                print("--> Failed to format image part:", str(error))

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
Reference the site name ({site_name}) and tailor your diagnostic advice specifically to {region_location} in South Africa.
"""

    diagnostic_report = None
    ai_engine_used = ""
    submission_status = "resolved"

    # Tier 1: Groq AI
    diagnostic_report = generate_report_groq(prompt_text)
    if diagnostic_report:
        ai_engine_used = "Groq (llama-3.1-8b-instant)"
    else:
        # Tier 2: Gemini AI
        diagnostic_report = generate_report_gemini(prompt_text, image_parts)
        if diagnostic_report:
            ai_engine_used = "Gemini (gemini-3.6-flash)"
        else:
            # Tier 3: RunPod Text Engine
            diagnostic_report = generate_report_runpod(prompt_text)
            if diagnostic_report:
                ai_engine_used = "RunPod (Qwen/Qwen3-0.6B)"
            else:
                submission_status = "pending_manual_review"
                diagnostic_report = "Report generation delayed. All automated AI models are currently offline. Queued for manual processing."
                ai_engine_used = "Queued for Manual Review"

    if diagnostic_report:
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

        if sender_email and submission_status == "resolved":
            send_email_message(
                sender_email,
                site_name,
                region_location,
                soil_type,
                seedling_crop_type,
                diagnostic_report
            )


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
async def handle_webhook(request: Request):
    payload = {}

    # 1. Try parsing JSON body
    try:
        payload = await request.json()
    except Exception:
        pass

    # 2. Fallback to Form Data if JSON is empty (Jotform standard behavior)
    if not payload:
        try:
            form_data = await request.form()
            payload = dict(form_data)
        except Exception:
            payload = {}

    # 3. Parse Jotform's nested rawRequest string if available
    if isinstance(payload, dict) and "rawRequest" in payload:
        raw_req = payload["rawRequest"]
        if isinstance(raw_req, str):
            try:
                payload = json.loads(raw_req)
            except Exception:
                pass

    if not payload:
        print("--> Warning: Received empty or unparseable webhook payload", flush=True)
        return {"status": "error", "message": "Payload was empty or unparseable"}

    flat_payload = flatten_kobo_payload(payload)

    # Extract all report type selections (supports checkboxes / lists / comma-separated strings)
    report_types = []
    for k, v in flat_payload.items():
        if "report_type" in k.lower() or "reporttype" in k.lower():
            if isinstance(v, list):
                report_types.extend([str(item).lower() for item in v])
            elif isinstance(v, str):
                parts = [p.strip().lower() for p in v.split(",")]
                report_types.extend(parts)

    print(f"--> Incoming Webhook Submission | Detected Report Types: {report_types}", flush=True)

    processed_actions = []

    # 1. ROUTE WEEKLY SITE REPORTING -> RELATIONAL TABLES
    if any("weekly" in rt for rt in report_types):
        save_weekly_report_to_supabase(payload)
        processed_actions.append("Weekly Site Reporting saved to relational tables")

    # 2. ROUTE SITE ISSUES -> FARM_REPORTS (AI PIPELINE)
    if any("issue" in rt for rt in report_types):
        process_farm_report(payload)
        processed_actions.append("Site Issues processed through AI pipeline and saved to farm_reports")

    # Fallback if Report_type unique name wasn't detected: execute default pipeline
    if not processed_actions:
        print("--> Fallback: No specific Report_type matched, routing payload to process_farm_report", flush=True)
        process_farm_report(payload)
        processed_actions.append("Processed via default farm report pipeline")

    return {
        "status": "success",
        "message": " | ".join(processed_actions)
    }


@app.post("/process-queue")
def process_pending_queue():
    if not supabase_client:
        raise HTTPException(status_code=500, detail="Supabase client is not configured.")
    
    if not RUNPOD_TEXT_URL:
        raise HTTPException(status_code=400, detail="RunPod URL (RUNPOD_TEXT_URL) is missing.")

    try:
        res = supabase_client.table("farm_reports").select("*").eq("status", "pending_manual_review").execute()
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

            prompt_text = f"""
You are an agricultural expert helping smallholder farmers in South Africa.
Analyze the following site issue report, soil parameters, and crop data.

SITE / FARM NAME: {site_name}
DATE PLANTED: {date_planted}
SOIL TYPE: {soil_type}
SEEDLING/CROP TYPE: {crop_type}
FARM LOCATION / REGION: {region_location}
FIELD OBSERVATION / ISSUE REPORTED: {weekly_observation}
"""

            report = generate_report_runpod(prompt_text)

            if report:
                ai_engine_used = "RunPod (Qwen/Qwen3-0.6B) [Queued Batch]"
                
                supabase_client.table("farm_reports").update({
                    "diagnostic_report": report,
                    "ai_engine": ai_engine_used,
                    "status": "resolved"
                }).eq("id", record_id).execute()

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
            "message": f"Successfully processed {processed_count} pending submissions using RunPod."
        }

    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Error processing queue: {str(error)}")
