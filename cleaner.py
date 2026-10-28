"""Lead data cleaner - a Python port of the n8n "Pure JS Data Cleaner" node."""
from __future__ import annotations

import re
import uuid
from datetime import date

import pandas as pd

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

FIELD_ALIASES = {
    "name": ["Raw_Name", "Raw Name", "Name", "Full_Name", "Full Name", "full_name"],
    "email": ["Contact_Email", "Contact Email", "Email", "Email Address", "email"],
    "company": ["Company_Name", "Company Name", "Company", "company_name"],
    "domain": ["Domain", "Company_Domain", "Company Domain", "Website"],
    "budget": ["Claimed_Budget", "Claimed Budget", "Budget", "claimed_budget"],
    "summary": [
        "Project_Details", "Project Details", "Project_Description",
        "Project Description", "Details", "Summary",
    ],
}

OUTPUT_COLUMNS = [
    "Lead_ID", "Date_Added", "Full_Name", "Email", "Company_Name", "Domain",
    "Budget", "Project_Summary", "AI_Fit_Score", "Priority", "AI_Email_Draft",
    "AI_Red_Flags",
]

DEFAULT_EMAIL_TEMPLATE = (
    "Hi {first_name},\n\n"
    "Thank you for reaching out regarding your project. We reviewed your "
    "requirements and would love to schedule a call to discuss how we can "
    "assist you.\n\nBest regards,\n{signature}"
)


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def get_field(row: dict, aliases: list[str]) -> str:
    """Find a value by any alias, ignoring case, spaces and underscores."""
    wanted = {_norm(a) for a in aliases}
    for key, value in row.items():
        if _norm(key) in wanted and value is not None and not pd.isna(value):
            return str(value).strip()
    return ""


def parse_budget(raw: str) -> float:
    """'$5,000 USD' -> 5000, '50k' -> 50000, '-500' -> 0, '' -> 0."""
    raw = raw.lower().strip()
    if not raw:
        return 0.0
    multiplier = 1
    if re.search(r"\d\s*k\b", raw) or raw.endswith("k"):
        multiplier = 1_000
    elif re.search(r"\d\s*m\b", raw):
        multiplier = 1_000_000
    match = re.search(r"-?\d[\d,]*\.?\d*", raw.replace(" ", ""))
    if not match:
        return 0.0
    try:
        num = float(match.group(0).replace(",", ""))
    except ValueError:
        return 0.0
    return num * multiplier if num > 0 else 0.0


def score_lead(budget: float, high: float, mid: float, threshold: int) -> tuple[int, str]:
    if budget >= high:
        score = 90
    elif budget >= mid:
        score = 75
    elif budget > 0:
        score = 60
    else:
        score = 30
    return score, ("HIGH_PRIORITY" if score >= threshold else "STANDARD_NURTURE")


def clean_row(
    row: dict,
    *,
    high_budget: float = 10_000,
    mid_budget: float = 5_000,
    priority_threshold: int = 70,
    email_template: str = DEFAULT_EMAIL_TEMPLATE,
    signature: str = "Sales Team",
) -> dict:
    # Name -> Title Case
    raw_name = get_field(row, FIELD_ALIASES["name"])
    full_name = " ".join(w.capitalize() for w in raw_name.split()) if raw_name else "Unspecified Contact"

    # Email
    raw_email = re.sub(r"\s+", "", get_field(row, FIELD_ALIASES["email"])).lower()
    m = EMAIL_RE.search(raw_email)
    email = m.group(0) if m else ""

    # Company
    raw_company = get_field(row, FIELD_ALIASES["company"])
    company = re.sub(r"\s+", " ", raw_company) if raw_company else "Unknown Company"

    # Domain (fallback: email domain, then company name)
    domain = get_field(row, FIELD_ALIASES["domain"])
    if not domain:
        if "@" in email:
            domain = email.split("@")[1]
        elif company != "Unknown Company":
            domain = re.sub(r"[^a-z0-9]", "", company.lower()) + ".com"

    budget = parse_budget(get_field(row, FIELD_ALIASES["budget"]))
    summary = get_field(row, FIELD_ALIASES["summary"]) or "No description provided."
    score, priority = score_lead(budget, high_budget, mid_budget, priority_threshold)

    flags = []
    if not email:
        flags.append("Invalid/Missing Email")
    if budget == 0:
        flags.append("Zero or Unspecified Budget")
    if company == "Unknown Company":
        flags.append("Missing Company Name")

    first_name = full_name.split(" ")[0]
    draft = email_template.replace("{first_name}", first_name).replace("{signature}", signature)

    return {
        "Lead_ID": "lead_" + uuid.uuid4().hex[:10],
        "Date_Added": date.today().isoformat(),
        "Full_Name": full_name,
        "Email": email,
        "Company_Name": company,
        "Domain": domain,
        "Budget": budget,
        "Project_Summary": summary,
        "AI_Fit_Score": score,
        "Priority": priority,
        "AI_Email_Draft": draft,
        "AI_Red_Flags": "; ".join(flags) if flags else "None",
    }


def clean_dataframe(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    rows = [clean_row(r, **kwargs) for r in df.to_dict(orient="records")]
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


SAMPLE_DATA = pd.DataFrame(
    {
        "Raw_Name": ["  jOHN   doe ", "MARY ann smith", "", "alex  KUMAR"],
        "Contact_Email": ["John.Doe@ Acme.com ", "not-an-email", "sam@startup.io", " ALEX@Kumar-Tech.IN"],
        "Company_Name": ["  acme   corp ", "Smith & Co", "", "Kumar Tech"],
        "Claimed_Budget": ["$5,000 USD", "-500", "50k", "12000"],
        "Project_Details": ["Need a CRM automation", "", "Chatbot for support", "RAG app for internal docs"],
    }
)
