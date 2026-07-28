import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import requests

from legal_documents import (
    LEGAL_DOCUMENT_STATUS_EN,
    LEGAL_DOCUMENT_STATUS_JA,
    PATIENT_TERMS_VERSION,
    PRIVACY_POLICY_VERSION,
    build_service_consent_record,
    patient_terms_markdown,
    privacy_policy_markdown,
)


APP_TITLE = "Shirabeo Labs | Patient Insight"

CSV_PATH_ADCT = Path("data/rd_adct_responses.csv")
CSV_PATH_DLQI = Path("data/rd_dlqi_responses.csv")
CSV_PATH_UCT = Path("data/rd_uct_responses.csv")

ADMIN_EMAIL = "komura@shirabeo.com"
CONTACT_EMAIL = "contact@shirabeo.com"

APP_VERSION = "Patient Insight v0.10.0"

# Facility / project classification
# These can be overridden in Render Environment for each deployed site.
SITE_ID = os.getenv("SITE_ID", "KRCH_DERM")
SITE_NAME = os.getenv("SITE_NAME", "Department of Dermatology, Kanazawa Red Cross Hospital")
PROJECT_ID = os.getenv("PROJECT_ID", "RD_PRO_PILOT_2026")
PROJECT_PHASE = os.getenv("PROJECT_PHASE", "RD")
RESEARCH_MODE = (
    os.getenv("RESEARCH_MODE", "true").strip().lower()
    not in {"0", "false", "no", "off"}
)
EXTERNAL_FACILITY_MODE = False
LEGAL_REVIEW_MODE = (
    os.getenv("LEGAL_REVIEW_MODE", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
ALLOWED_SCALES = ("ADCT", "DLQI", "UCT")
FACILITY_CONTACT = os.getenv("FACILITY_CONTACT", CONTACT_EMAIL)
SERVICE_PROVIDER_NAME = os.getenv("SERVICE_PROVIDER_NAME", "Shirabeo Labs")
DATA_HOSTING_REGION = os.getenv(
    "DATA_HOSTING_REGION",
    "Oregon, United States",
)

JST = timezone(timedelta(hours=9))


def send_to_google_form(row):
    url = "https://docs.google.com/forms/d/e/1FAIpQLScC3M0830zqkGnnNsD8D_lOFoRwzyqFrd0ljMP6tAB530Jp1w/formResponse"

    data = {
        "entry.1599902592": row.get("visit_code", ""),
        "entry.1495391757": row.get("total_score", ""),
        "entry.1432435158": row.get("decision", ""),
        "entry.1577092948": row.get("timestamp", ""),
    }

    try:
        res = requests.post(url, data=data, timeout=10)
        print("FORM STATUS:", res.status_code)
        return res.status_code in [200, 302]
    except Exception as e:
        print("FORM ERROR:", e)
        return False


def send_to_google_sheet(row):
    """Send one submission row to Google Apps Script Web App.

    MASTERシート1本運用用。
    - ADCT入力時は adct_* のみ埋める
    - UCT入力時は uct_* のみ埋める
    - DLQI入力時は dlqi_* のみ埋める

    Google Sheet側の想定ヘッダー：
    timestamp, anonymous_id, facility_id, disease, scale,
    adct_q1 ... adct_q6, adct_total,
    input_time_seconds, input_support, input_ease, research_consent,
    doctor_check, treatment, treatment_changed, memo,
    uct_q1 ... uct_q4, uct_total,
    dlqi_q1 ... dlqi_q10, dlqi_total,
    visit_date, max_score
    """
    url = os.getenv("GOOGLE_SCRIPT_URL")

    if not url:
        print("GOOGLE_SCRIPT_URL is not set")
        return False

    def pick(*keys, default=""):
        """Return the first non-empty value found in row."""
        for key in keys:
            value = row.get(key, "")
            if value is not None and value != "":
                return value
        return default

    def item_score(n: int):
        """Return item score from either normalized or RD4 internal keys."""
        return pick(f"q{n}_score", f"q{n}")

    timestamp = str(pick("timestamp", "input_submitted_at"))
    visit_date = timestamp[:10] if timestamp else ""
    scale = str(pick("scale", "instrument")).upper()
    total_score = pick("total_score", "total")
    max_score = pick("max_score")

    payload = {
        "timestamp": timestamp,
        "anonymous_id": pick("anonymous_id", "visit_code"),
        "facility_id": pick("facility_id", "site_id", default=SITE_ID),
        "disease": pick("disease"),
        "scale": scale,

        "adct_q1": "",
        "adct_q2": "",
        "adct_q3": "",
        "adct_q4": "",
        "adct_q5": "",
        "adct_q6": "",
        "adct_total": "",

        "input_time_seconds": pick("input_time_seconds", "input_duration_seconds"),
        "input_support": pick("input_support"),
        "input_ease": pick("input_ease"),
        "research_consent": pick("research_consent", "research_consent_checked"),
        "doctor_check": pick("doctor_check", "decision"),
        "treatment": pick("treatment"),
        "treatment_changed": pick("treatment_changed"),
        "memo": pick("memo", "decision_reasons"),

        "uct_q1": "",
        "uct_q2": "",
        "uct_q3": "",
        "uct_q4": "",
        "uct_total": "",

        "dlqi_q1": "",
        "dlqi_q2": "",
        "dlqi_q3": "",
        "dlqi_q4": "",
        "dlqi_q5": "",
        "dlqi_q6": "",
        "dlqi_q7": "",
        "dlqi_q8": "",
        "dlqi_q9": "",
        "dlqi_q10": "",
        "dlqi_total": "",

        "visit_date": visit_date,
        "max_score": max_score,
    }

    if scale == "ADCT":
        for i in range(1, 7):
            payload[f"adct_q{i}"] = item_score(i)
        payload["adct_total"] = total_score

    elif scale == "UCT":
        for i in range(1, 5):
            payload[f"uct_q{i}"] = item_score(i)
        payload["uct_total"] = total_score

    elif scale == "DLQI":
        for i in range(1, 11):
            payload[f"dlqi_q{i}"] = item_score(i)
        payload["dlqi_total"] = total_score

    else:
        print("Unknown scale:", scale)

    try:
        print("===== GOOGLE SHEET PAYLOAD =====")
        print(payload)

        res = requests.post(
            url,
            json=payload,
            timeout=20,
            allow_redirects=True,
        )

        print("===== GOOGLE SHEET RESPONSE =====")
        print(res.status_code)
        print(res.text[:1000])

        if res.status_code != 200:
            return False

        try:
            body = res.json()
            return body.get("result") == "success"
        except Exception:
            return '"success"' in res.text

    except Exception as e:
        print("===== GOOGLE SHEET ERROR =====")
        print(e)
        return False


DLQI_QUESTIONS_JA = [
    "この1週間で、皮膚のかゆみ・痛み・ヒリヒリ感・しみる感じはどの程度ありましたか？",
    "この1週間で、皮膚のために恥ずかしい、または人目が気になると感じたことはどの程度ありましたか？",
    "この1週間で、皮膚のために買い物、家事、庭仕事などにどの程度支障がありましたか？",
    "この1週間で、皮膚のために着る服にどの程度影響がありましたか？",
    "この1週間で、皮膚のために社交・余暇活動にどの程度影響がありましたか？",
    "この1週間で、皮膚のためにスポーツがどの程度困難でしたか？",
    "この1週間で、皮膚のために仕事や勉強ができませんでしたか？",
    "この1週間で、皮膚のために配偶者、友人、家族との関係にどの程度問題がありましたか？",
    "この1週間で、皮膚のために性的な困難がどの程度ありましたか？",
    "この1週間で、皮膚の治療がどの程度問題になりましたか？ 例：家が汚れる、時間がかかるなど。",
]

DLQI_QUESTIONS_EN = [
    "Over the last week, how itchy, sore, painful or stinging has your skin been?",
    "Over the last week, how embarrassed or self-conscious have you been because of your skin?",
    "Over the last week, how much has your skin interfered with you going shopping or looking after your home or garden?",
    "Over the last week, how much has your skin influenced the clothes you wear?",
    "Over the last week, how much has your skin affected any social or leisure activities?",
    "Over the last week, how much has your skin made it difficult for you to do any sport?",
    "Over the last week, has your skin prevented you from working or studying?",
    "Over the last week, how much has your skin created problems with your partner or any of your close friends or relatives?",
    "Over the last week, how much has your skin caused any sexual difficulties?",
    "Over the last week, how much of a problem has the treatment for your skin been, for example by making your home messy, or by taking up time?",
]

DLQI_OPTIONS_JA = {
    "全くない / 該当しない": 0,
    "少し": 1,
    "かなり": 2,
    "非常に": 3,
}

DLQI_OPTIONS_EN = {
    "Not at all / Not relevant": 0,
    "A little": 1,
    "A lot": 2,
    "Very much": 3,
}

DLQI_Q7_OPTIONS_JA = {
    "はい、仕事または勉強ができなかった": 3,
    "いいえ、ただし仕事または勉強に支障があった": 2,
    "いいえ": 0,
    "該当しない": 0,
}

DLQI_Q7_OPTIONS_EN = {
    "Yes — prevented work or studying": 3,
    "No, but skin was a problem at work or studying": 2,
    "No": 0,
    "Not relevant": 0,
}


ADCT_TITLE_JA = "アトピー性皮膚炎のコントロール状態に関する調査票（ADCT）"
ADCT_TITLE_EN = "Atopic Dermatitis Control Tool"

ADCT_INSTRUCTION_JA = "アトピー性皮膚炎のコントロール状態について、以下の質問にお答えください。"
ADCT_INSTRUCTION_EN = 'Please answer the following questions thinking about your experiences with eczema, sometimes called “atopic dermatitis.”'

ADCT_COPYRIGHT_JA = (
    "© Atopic Dermatitis Control Tool_Version 1, 05 Sep 2019 "
    "Sanofi Group and Regeneron Pharmaceuticals Inc. All Rights Reserved."
)
ADCT_COPYRIGHT_EN = (
    "© Atopic Dermatitis Control Tool_Version 1, 27 Nov 2018 "
    "Sanofi Group and Regeneron Pharmaceuticals Inc. All Rights Reserved."
)

ADCT_MAPI_NOTICE_JA = (
    "For any information on the use of the ADCT, please contact "
    "Mapi Research Trust, Lyon, France.\n"
    "Internet: https://eprovide.mapi-trust.org"
)
ADCT_MAPI_NOTICE_EN = ADCT_MAPI_NOTICE_JA

ADCT_QUESTIONS_JA = [
    "この 1 週間、アトピー性皮膚炎の症状はどの程度でしたか（例えば、かゆみ、乾燥、発疹）。",
    "この 1 週間、アトピー性皮膚炎のために激しいかゆみが起こったことは何日ありましたか。",
    "この 1 週間、アトピー性皮膚炎にどの程度悩まされましたか。",
    "この 1 週間、アトピー性皮膚炎のためになかなか寝付けなかったり、途中で目が覚めたりすることが何晩ありましたか。",
    "この 1 週間、アトピー性皮膚炎がどの程度日常の活動に影響しましたか。",
    "この 1 週間、アトピー性皮膚炎がどの程度気分や感情に影響しましたか。",
]

ADCT_QUESTIONS_EN = [
    "Over the last week, how would you rate your eczema-related symptoms (for example, itching, dry skin, skin rash)?",
    "Over the last week, how many days did you have intense episodes of itching because of your eczema?",
    "Over the last week, how bothered have you been by your eczema?",
    "Over the last week, how many nights did you have trouble falling or staying asleep because of your eczema?",
    "Over the last week, how much did your eczema affect your daily activities?",
    "Over the last week, how much did your eczema affect your mood or emotions?",
]

ADCT_OPTIONS_JA = [
    {"0　なし": 0, "1　軽い": 1, "2　中くらい": 2, "3　ひどい": 3, "4　かなりひどい": 4},
    {"0　全くなかった": 0, "1　1～2 日": 1, "2　3～4 日": 2, "3　5～6 日": 3, "4　毎日": 4},
    {"0　全くなかった": 0, "1　少し": 1, "2　ある程度": 2, "3　とても": 3, "4　極めて": 4},
    {"0　全くなかった": 0, "1　1～2 晩": 1, "2　3～4 晩": 2, "3　5～6 晩": 3, "4　毎晩": 4},
    {"0　全くなかった": 0, "1　少し": 1, "2　ある程度": 2, "3　とても": 3, "4　極めて": 4},
    {"0　全くなかった": 0, "1　少し": 1, "2　ある程度": 2, "3　とても": 3, "4　極めて": 4},
]

ADCT_OPTIONS_EN = [
    {"0　None": 0, "1　Mild": 1, "2　Moderate": 2, "3　Severe": 3, "4　Very Severe": 4},
    {"0　Not at all": 0, "1　1-2 days": 1, "2　3-4 days": 2, "3　5-6 days": 3, "4　Every day": 4},
    {"0　Not at all": 0, "1　A little": 1, "2　Moderately": 2, "3　Very": 3, "4　Extremely": 4},
    {"0　No nights": 0, "1　1-2 nights": 1, "2　3-4 nights": 2, "3　5-6 nights": 3, "4　Every night": 4},
    {"0　Not at all": 0, "1　A little": 1, "2　Moderately": 2, "3　A lot": 3, "4　Extremely": 4},
    {"0　Not at all": 0, "1　A little": 1, "2　Moderately": 2, "3　A lot": 3, "4　Extremely": 4},
]

UCT_TITLE_JA = "蕁麻疹状況調査\nUrticaria Control Test"
UCT_TITLE_EN = "Urticaria Control Test (UCT)"

UCT_INSTRUCTION_JA = (
    "蕁麻疹の患者さんにお尋ねします。以下の質問は、あなたの現在の症状をお聞きするものです。\n"
    "各質問をよく読んで、5 つの選択肢の中からあなたの状態に最もあてはまるものを選んでください。\n"
    "直近の 4 週間についてお答えください。あまり長い時間考え込まないようにして、すべての質問に１つだけ回答を選んでお答えください。"
)
UCT_INSTRUCTION_EN = (
    "Please read each question carefully and choose the one answer from the five options "
    "that best applies to your condition. Please answer based on the last 4 weeks."
)

UCT_COPYRIGHT_JA = (
    "This document must not be copied or used without the permission of MOXIE GmbH. "
    "For scientific or commercial use or in case a translation / cross cultural adaptation is intended, "
    "please check the terms and conditions on www.moxie-gmbh.de."
)
UCT_COPYRIGHT_EN = UCT_COPYRIGHT_JA

UCT_QUESTIONS_JA = [
    "この 4 週間に、蕁麻疹による症状(痒み、膨疹※、腫れ)がどのくらいありましたか？",
    "この 4 週間に、蕁麻疹によってあなたの生活の質はどのくらい損なわれましたか？",
    "この 4 週間に、蕁麻疹の治療があなたの症状を抑えるのに十分でなかったことがどのくらいありましたか？",
    "全体として、この 4 週間にあなたの蕁麻疹はどのくらい良い状態に保たれていましたか？",
]

UCT_QUESTION_NOTES_JA = [
    "※膨疹：蚊に刺された時やミミズ腫れのような皮膚の膨らみ",
    "",
    "",
    "",
]

UCT_QUESTIONS_EN = [
    "Over the last 4 weeks, how much have you had urticaria symptoms such as itching, wheals, or swelling?",
    "Over the last 4 weeks, how much was your quality of life impaired by urticaria?",
    "Over the last 4 weeks, how often was the treatment for your urticaria not enough to control your symptoms?",
    "Overall, over the last 4 weeks, how well has your urticaria been controlled?",
]

UCT_QUESTION_NOTES_EN = [
    "",
    "",
    "",
    "",
]

UCT_OPTIONS_JA = [
    {"非常に強い": 0, "強い": 1, "ある程度": 2, "わずか": 3, "全くない": 4},
    {"非常に強い": 0, "強い": 1, "ある程度": 2, "わずか": 3, "全くない": 4},
    {"非常に頻繁": 0, "頻繁": 1, "時々": 2, "まれに": 3, "全くない": 4},
    {
        "全く(保たれていなかった)": 0,
        "わずかに(しか保たれていなかった)": 1,
        "ある程度（保たれていた）": 2,
        "良く(保たれていた)": 3,
        "完全に（保たれていた）": 4,
    },
]

UCT_OPTIONS_EN = [
    {"Very much": 0, "Much": 1, "Somewhat": 2, "A little": 3, "Not at all": 4},
    {"Very much": 0, "Much": 1, "Somewhat": 2, "A little": 3, "Not at all": 4},
    {"Very often": 0, "Often": 1, "Sometimes": 2, "Rarely": 3, "Not at all": 4},
    {"Not controlled at all": 0, "A little controlled": 1, "Somewhat controlled": 2, "Well controlled": 3, "Completely controlled": 4},
]


def get_secret(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


def t(language: str, ja: str, en: str) -> str:
    return ja if language == "日本語" else en


def interpret_dlqi(score: int, language: str) -> tuple[str, str]:
    if score <= 1:
        return (
            t(language, "影響なし", "No effect"),
            t(language, "生活への明らかな影響はほとんどありません。", "No measurable effect on the patient's life."),
        )
    if score <= 5:
        return (
            t(language, "軽度の影響", "Small effect"),
            t(language, "生活への影響は軽度です。", "Small effect on the patient's life."),
        )
    if score <= 10:
        return (
            t(language, "中等度の影響", "Moderate effect"),
            t(language, "生活への影響は中等度です。", "Moderate effect on the patient's life."),
        )
    if score <= 20:
        return (
            t(language, "非常に大きな影響", "Very large effect"),
            t(language, "生活への影響は非常に大きい状態です。", "Very large effect on the patient's life."),
        )
    return (
        t(language, "極めて大きな影響", "Extremely large effect"),
        t(language, "生活への影響は極めて大きい状態です。", "Extremely large effect on the patient's life."),
    )


def interpret_adct(score: int, language: str) -> tuple[str, str]:
    if score >= 7:
        return (
            t(language, "コントロール不十分の可能性", "Possible uncontrolled atopic dermatitis"),
            t(
                language,
                "ADCTが7点以上です。症状、睡眠、日常生活への影響を医療者が確認してください。",
                "ADCT is 7 or higher. A qualified clinician should review symptoms, sleep, and daily-life impact.",
            ),
        )
    return (
        t(language, "比較的コントロール良好", "Relatively controlled"),
        t(
            language,
            "ADCTは7点未満です。通常診療の中で医療者が確認を継続してください。",
            "ADCT is below 7. Continue routine assessment by a qualified clinician.",
        ),
    )


def interpret_uct(score: int, language: str) -> tuple[str, str]:
    if score < 12:
        return (
            t(language, "コントロール不良の可能性", "Possible uncontrolled urticaria"),
            t(
                language,
                "UCTが12点未満です。症状、生活への影響、治療状況を医療者が確認してください。",
                "UCT is below 12. A qualified clinician should review symptoms, quality-of-life impact, and treatment status.",
            ),
        )
    if score < 16:
        return (
            t(language, "比較的コントロール良好", "Relatively controlled"),
            t(
                language,
                "UCTは12点以上です。通常診療の中で医療者が確認を継続してください。",
                "UCT is 12 or higher. Continue routine assessment by a qualified clinician.",
            ),
        )
    return (
        t(language, "完全にコントロール良好", "Completely controlled"),
        t(
            language,
            "UCTは16点です。通常診療の中で医療者が確認を継続してください。",
            "UCT is 16. Continue routine assessment by a qualified clinician.",
        ),
    )


def get_csv_path(instrument: str) -> Path:
    if instrument == "ADCT":
        return CSV_PATH_ADCT
    if instrument == "UCT":
        return CSV_PATH_UCT
    return CSV_PATH_DLQI


def save_result(row: dict):
    csv_path = get_csv_path(row.get("instrument", ""))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])

    if csv_path.exists():
        df.to_csv(csv_path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def get_previous_adct(patient_code: str):
    if not patient_code or not CSV_PATH_ADCT.exists():
        return None

    try:
        df = pd.read_csv(CSV_PATH_ADCT, on_bad_lines="skip")
    except Exception:
        return None

    if "visit_code" not in df.columns or "total_score" not in df.columns:
        return None

    df_ad = df[df["visit_code"].astype(str) == str(patient_code)]

    if df_ad.empty:
        return None

    last_row = df_ad.sort_values("timestamp").iloc[-1]
    return int(last_row["total_score"])


def judge_adct_control(current: int, previous: int | None, scores: list[int], language: str) -> dict:
    reasons_ja = []
    reasons_en = []

    if current >= 7:
        reasons_ja.append("ADCT総スコアが7点以上")
        reasons_en.append("ADCT total score is 7 or higher")

    if previous is not None and (current - previous) >= 5:
        reasons_ja.append("前回から5点以上増加")
        reasons_en.append("Increase of 5 points or more from previous ADCT")

    uncontrolled = len(reasons_ja) > 0

    if uncontrolled:
        return {
            "decision": "非維持",
            "display_title": t(
                language,
                "コントロール不十分の可能性",
                "Possible uncontrolled atopic dermatitis",
            ),
            "message": t(
                language,
                "ADCTの結果から、アトピー性皮膚炎のコントロールが不十分な可能性があります。医療者による確認を推奨します。",
                "Based on the ADCT result, atopic dermatitis may be insufficiently controlled. Review by a qualified clinician is recommended.",
            ),
            "reasons": reasons_ja if language == "日本語" else reasons_en,
        }

    return {
        "decision": "維持",
        "display_title": t(
            language,
            "比較的コントロール良好",
            "Relatively controlled",
        ),
        "message": t(
            language,
            "ADCTは7点未満で、前回から5点以上の増加もありません。通常診療の中で確認を継続してください。",
            "ADCT is below 7 and has not increased by 5 points or more from the previous score. Continue routine clinical review.",
        ),
        "reasons": [],
    }

def build_email_body(row: dict, result: dict) -> str:
    lines = [
        "New questionnaire submission",
        "",
        f"App: {APP_TITLE}",
        f"Version: {APP_VERSION}",
        f"Site ID: {row.get('site_id', '')}",
        f"Site name: {row.get('site_name', '')}",
        f"Project ID: {row.get('project_id', '')}",
        f"Project phase: {row.get('project_phase', '')}",
        f"Timestamp: {row.get('timestamp', '')}",
        f"Language: {row.get('language', '')}",
        f"Disease: {row.get('disease', '')}",
        f"Instrument: {row.get('instrument', '')}",
        f"Anonymous visit code: {row.get('visit_code', '') or '(blank)'}",
        f"Total score: {row.get('total_score', '')} / {row.get('max_score', '')}",
        f"Severity / interpretation: {row.get('severity', '')}",
        f"Decision support display: {row.get('decision', '')}",
        f"Decision reasons: {row.get('decision_reasons', '')}",
        f"Previous ADCT: {row.get('previous_adct', '')}",
        f"Delta ADCT: {row.get('delta_adct', '')}",
        "",
        "Item scores:",
    ]

    for i, score in enumerate(result["scores"], start=1):
        answer = result["answers"][i - 1]
        lines.append(f"Q{i}: {score} | {answer}")

    lines.extend([
        "",
        "Important notes:",
        "- This message is intended for clinical support only.",
        "- This app does not provide diagnosis or treatment instructions.",
        "- Final clinical decisions must be made by a qualified healthcare professional.",
        "- No direct personal identifiers should be entered into this app.",
    ])
    return "\n".join(lines)


def send_admin_email(row: dict, result: dict) -> tuple[bool, str]:
    smtp_host = get_secret("SMTP_HOST")
    smtp_port = int(get_secret("SMTP_PORT", "587"))
    smtp_user = get_secret("SMTP_USER")
    smtp_password = get_secret("SMTP_PASSWORD")
    smtp_from = get_secret("SMTP_FROM", smtp_user or ADMIN_EMAIL)

    missing = [
        name for name, value in {
            "SMTP_HOST": smtp_host,
            "SMTP_USER": smtp_user,
            "SMTP_PASSWORD": smtp_password,
            "SMTP_FROM": smtp_from,
        }.items() if not value
    ]

    if missing:
        return False, "Missing email settings: " + ", ".join(missing)

    subject = f"[Shirabeo Patient Insight] New {row['instrument']} Submission: {row['total_score']}/{row['max_score']}"
    body = build_email_body(row, result)

    msg = MIMEMultipart()
    msg["From"] = smtp_from
    msg["To"] = ADMIN_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [ADMIN_EMAIL], msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False, f"Email sending failed: {e}"


def render_legal_notice(language: str):
    service_description_ja = (
        "研究・試験運用中の診療支援ツール"
        if RESEARCH_MODE
        else "医療機関向けに提供される診療・問診支援サービス"
    )
    service_description_en = (
        "a clinical-support tool in research or pilot operation"
        if RESEARCH_MODE
        else "a clinical and questionnaire-support service provided to medical institutions"
    )
    st.warning(
        t(
            language,
            f"本アプリは、{service_description_ja}です。診断、治療方針、薬剤選択、治療継続・中止を自動的に決定するものではありません。最終的な診療判断は、必ず医師その他の資格を有する医療者が行ってください。緊急時には使用せず、医療機関へ直接連絡してください。",
            f"This application is {service_description_en}. It does not provide diagnosis, determine treatment plans, select medications, or automatically decide whether treatment should be continued or stopped. Final clinical decisions must always be made by a qualified healthcare professional. Do not use it for emergencies; contact the medical institution directly.",
        )
    )

    st.caption(
        t(
            language,
            f"{LEGAL_DOCUMENT_STATUS_JA}：患者向け利用規約 {PATIENT_TERMS_VERSION}／プライバシーポリシー {PRIVACY_POLICY_VERSION}",
            f"{LEGAL_DOCUMENT_STATUS_EN}: Patient Terms {PATIENT_TERMS_VERSION} / Privacy Policy {PRIVACY_POLICY_VERSION}",
        )
    )

    with st.expander(
        t(
            language,
            "患者向け利用規約（ドラフト）を確認",
            "Review the Patient Terms (draft)",
        )
    ):
        st.markdown(
            patient_terms_markdown(
                language,
                service_provider=SERVICE_PROVIDER_NAME,
                facility_name=SITE_NAME,
                contact_email=FACILITY_CONTACT,
            )
        )

    with st.expander(
        t(
            language,
            "プライバシーポリシー（ドラフト）を確認",
            "Review the Privacy Policy (draft)",
        )
    ):
        st.markdown(
            privacy_policy_markdown(
                language,
                service_provider=SERVICE_PROVIDER_NAME,
                facility_name=SITE_NAME,
                contact_email=FACILITY_CONTACT,
                hosting_region=DATA_HOSTING_REGION,
            )
        )


def render_research_consent_notice(language: str):
    st.markdown("---")
    st.markdown(
        t(
            language,
            "**研究参加について**",
            "**Research participation**",
        )
    )
    st.info(
        t(
            language,
            "本入力内容は、アトピー性皮膚炎におけるADCTのデジタル入力支援ツールの実装可能性を評価する研究に使用される場合があります。研究では、ADCT回答、入力時間、入力のしやすさ、入力者情報、医療者による確認状況などを、個人が特定されない形で解析します。",
            "The information entered here may be used for a research study evaluating the feasibility of a digital ADCT input-support tool for atopic dermatitis. The study may analyze ADCT responses, input duration, ease of input, who entered the responses, and clinician review status in a form that does not directly identify individuals.",
        )
    )
    st.caption(
        t(
            language,
            "診療内容は担当医が通常診療として判断し、本アプリが診断・治療方針を自動決定するものではありません。研究参加は任意であり、同意しない場合でも診療上の不利益はありません。",
            "Clinical care will be determined by the treating clinician as part of routine practice. This application does not automatically determine diagnosis or treatment policy. Research participation is voluntary, and refusal to participate will not result in any disadvantage in clinical care.",
        )
    )


def render_credit_footer(language: str):
    st.markdown("---")
    st.caption(
        t(
            language,
            f"{APP_VERSION} | {PROJECT_PHASE}. Site: {SITE_ID} / {SITE_NAME}. Contact: {FACILITY_CONTACT}.",
            f"{APP_VERSION} | {PROJECT_PHASE}. Site: {SITE_ID} / {SITE_NAME}. Contact: {FACILITY_CONTACT}.",
        )
    )
    st.caption(
        t(
            language,
            "本アプリは診療補助・問診支援を目的とし、診断・治療方針・薬剤選択・治療継続または中止を自動決定するものではありません。最終的な診療判断は医療者が行ってください。",
            "This application supports clinical workflows and questionnaires. It does not automatically determine diagnosis, treatment plans, medication selection, or treatment continuation/discontinuation. Final clinical decisions should be made by a qualified healthcare professional.",
        )
    )

def render_adct_partner_notice(language: str):
    # ADCT copyright and Mapi contact notice are displayed within the ADCT block itself.
    # Avoid duplicating them again in the general app footer.
    return

def render_dlqi(language: str):
    questions = DLQI_QUESTIONS_JA if language == "日本語" else DLQI_QUESTIONS_EN
    options_common = DLQI_OPTIONS_JA if language == "日本語" else DLQI_OPTIONS_EN
    q7_options = DLQI_Q7_OPTIONS_JA if language == "日本語" else DLQI_Q7_OPTIONS_EN

    scores = []
    answers = []

    for i, q in enumerate(questions, start=1):
        st.markdown(f"**Q{i}. {q}**")
        opts = q7_options if i == 7 else options_common
        answer = st.radio(
            t(language, f"Q{i}の回答", f"Answer Q{i}"),
            list(opts.keys()),
            key=f"dlqi_{language}_{i}",
            label_visibility="collapsed",
        )
        scores.append(opts[answer])
        answers.append(answer)
        st.write("")

    total = int(sum(scores))
    severity, interpretation = interpret_dlqi(total, language)

    return {
        "instrument": "DLQI",
        "disease": "Psoriasis",
        "total_score": total,
        "max_score": 30,
        "severity": severity,
        "interpretation": interpretation,
        "scores": scores,
        "answers": answers,
    }


def render_uct(language: str):
    questions = UCT_QUESTIONS_JA if language == "日本語" else UCT_QUESTIONS_EN
    question_notes = UCT_QUESTION_NOTES_JA if language == "日本語" else UCT_QUESTION_NOTES_EN
    options_list = UCT_OPTIONS_JA if language == "日本語" else UCT_OPTIONS_EN
    uct_title = UCT_TITLE_JA if language == "日本語" else UCT_TITLE_EN
    uct_instruction = UCT_INSTRUCTION_JA if language == "日本語" else UCT_INSTRUCTION_EN
    uct_copyright = UCT_COPYRIGHT_JA if language == "日本語" else UCT_COPYRIGHT_EN

    scores = []
    answers = []

    st.markdown(f"### {uct_title}")
    st.write(uct_instruction)

    for i, q in enumerate(questions, start=1):
        st.markdown(f"**{i}. {q}**")
        note = question_notes[i - 1]
        if note:
            st.caption(note)

        opts = options_list[i - 1]
        answer = st.radio(
            t(language, f"Q{i}の回答", f"Answer Q{i}"),
            list(opts.keys()),
            index=None,
            key=f"uct_{language}_{i}",
            label_visibility="collapsed",
        )
        if answer is None:
            scores.append(None)
            answers.append("")
        else:
            scores.append(opts[answer])
            answers.append(answer)
        st.write("")

    has_missing_uct = any(score is None for score in scores)

    if has_missing_uct:
        st.warning(
            t(
                language,
                "UCTの全4項目に回答してください。",
                "Please answer all 4 UCT items.",
            )
        )

    # Display MOXIE copyright notice once at the bottom of the UCT questionnaire block.
    st.caption(uct_copyright)

    total = int(sum(score for score in scores if score is not None))
    severity, interpretation = interpret_uct(total, language)

    return {
        "instrument": "UCT",
        "disease": "Urticaria",
        "total_score": total,
        "max_score": 16,
        "severity": severity,
        "interpretation": interpretation,
        "scores": scores,
        "answers": answers,
        "is_complete": not has_missing_uct,
    }


def render_adct(language: str):
    questions = ADCT_QUESTIONS_JA if language == "日本語" else ADCT_QUESTIONS_EN
    options_list = ADCT_OPTIONS_JA if language == "日本語" else ADCT_OPTIONS_EN
    adct_title = ADCT_TITLE_JA if language == "日本語" else ADCT_TITLE_EN
    adct_instruction = ADCT_INSTRUCTION_JA if language == "日本語" else ADCT_INSTRUCTION_EN
    adct_copyright = ADCT_COPYRIGHT_JA if language == "日本語" else ADCT_COPYRIGHT_EN
    adct_mapi_notice = ADCT_MAPI_NOTICE_JA if language == "日本語" else ADCT_MAPI_NOTICE_EN

    scores = []
    answers = []

    st.markdown(f"### {adct_title}")
    st.write(adct_instruction)

    for i, q in enumerate(questions, start=1):
        st.markdown(f"**{i}. {q}**")
        opts = options_list[i - 1]
        answer = st.radio(
            t(language, f"Q{i}の回答", f"Answer Q{i}"),
            list(opts.keys()),
            index=None,
            key=f"adct_{language}_{i}",
            label_visibility="collapsed",
        )
        if answer is None:
            scores.append(None)
            answers.append("")
        else:
            scores.append(opts[answer])
            answers.append(answer)
        st.write("")

    # Display owner copyright notice once at the bottom of the ADCT questionnaire block.
    st.caption(adct_copyright)

    # Display Mapi contact notice as plain text. Do not render the URL as an active link.
    st.markdown("---")
    st.text(adct_mapi_notice)

    st.markdown("---")
    st.markdown(
        t(
            language,
            "**試験運用に関する確認項目**",
            "**Pilot-operation questions**",
        )
    )

    input_support_options = [
        t(language, "自分で最後まで入力した", "Completed all entries by myself"),
        t(language, "病院スタッフの説明・補助を受けながら、自分で入力した", "Completed by myself with explanation or support from hospital staff"),
        t(language, "病院スタッフが代わりに入力した", "Hospital staff entered the responses on my behalf"),
        t(language, "家族・付き添いの方が代わりに入力した", "A family member or accompanying person entered the responses on my behalf"),
    ]
    input_support = st.radio(
        t(
            language,
            "この質問票の入力はどのように行いましたか？",
            "How was this questionnaire entered?",
        ),
        input_support_options,
        index=None,
        key=f"adct_input_support_{language}",
    )

    input_ease_options = [
        t(language, "とても簡単だった", "Very easy"),
        t(language, "簡単だった", "Easy"),
        t(language, "やや難しかった", "Somewhat difficult"),
        t(language, "難しかった", "Difficult"),
    ]
    input_ease = st.radio(
        t(
            language,
            "今回の入力はどう感じましたか？",
            "How easy or difficult was this entry process?",
        ),
        input_ease_options,
        index=None,
        key=f"adct_input_ease_{language}",
    )

    has_missing_adct = any(score is None for score in scores)
    has_missing_pilot_questions = input_support is None or input_ease is None

    if has_missing_adct:
        st.warning(
            t(
                language,
                "ADCTの全6項目に回答してください。",
                "Please answer all 6 ADCT items.",
            )
        )

    if has_missing_pilot_questions:
        st.warning(
            t(
                language,
                "試験運用に関する確認項目にも回答してください。",
                "Please also answer the pilot-operation questions.",
            )
        )

    total = int(sum(score for score in scores if score is not None))
    severity, interpretation = interpret_adct(total, language)

    return {
        "instrument": "ADCT",
        "disease": "Atopic dermatitis",
        "total_score": total,
        "max_score": 24,
        "severity": severity,
        "interpretation": interpretation,
        "scores": scores,
        "answers": answers,
        "input_support": input_support or "",
        "input_ease": input_ease or "",
        "is_complete": not has_missing_adct and not has_missing_pilot_questions,
    }


def clinician_priority_label(row: pd.Series, instrument_label: str) -> tuple[str, str]:
    decision = str(row.get("decision", "") or "")
    try:
        total_score = int(float(row.get("total_score", 0)))
    except Exception:
        total_score = 0

    if instrument_label == "ADCT":
        if decision == "非維持" or total_score >= 7:
            return "確認優先", "🔴"
        return "通常確認", "🟢"

    if instrument_label == "UCT":
        if total_score < 12:
            return "確認優先", "🔴"
        if total_score == 16:
            return "完全コントロール", "🟢"
        return "通常確認", "🟢"

    if total_score >= 21:
        return "生活影響：極めて大", "🔴"
    if total_score >= 11:
        return "生活影響：大", "🟠"
    if total_score >= 6:
        return "生活影響：中等度", "🟡"
    return "通常確認", "🟢"


def format_clinician_value(value) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def inject_clinician_ui_css():
    st.markdown(
        """
        <style>
        .clinician-card {
            border: 1px solid rgba(120, 120, 120, 0.25);
            border-radius: 16px;
            padding: 18px 18px 14px 18px;
            margin: 14px 0 18px 0;
            background: rgba(250, 250, 250, 0.78);
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        }
        .clinician-card-priority {
            border-left: 8px solid #d93025;
            background: rgba(255, 245, 245, 0.88);
        }
        .clinician-card-normal {
            border-left: 8px solid #188038;
            background: rgba(246, 252, 248, 0.88);
        }
        .clinician-card-impact-high {
            border-left: 8px solid #f29900;
            background: rgba(255, 250, 240, 0.88);
        }
        .clinician-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }
        .clinician-title {
            font-size: 1.15rem;
            font-weight: 800;
            line-height: 1.3;
        }
        .clinician-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 5px 12px;
            font-size: 0.86rem;
            font-weight: 700;
            background: rgba(0,0,0,0.07);
            white-space: nowrap;
        }
        .clinician-meta {
            color: rgba(49, 51, 63, 0.72);
            font-size: 0.92rem;
            margin: 0 0 10px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_clinician_submission_card(row: pd.Series, instrument_label: str, index: int):
    priority_text, priority_icon = clinician_priority_label(row, instrument_label)

    timestamp = format_clinician_value(row.get("timestamp", ""))
    visit_code = format_clinician_value(row.get("visit_code", ""))
    total_score = format_clinician_value(row.get("total_score", ""))
    max_score = format_clinician_value(row.get("max_score", ""))
    severity = format_clinician_value(row.get("severity", ""))
    decision = format_clinician_value(row.get("decision", ""))
    previous_adct = format_clinician_value(row.get("previous_adct", ""))
    delta_adct = format_clinician_value(row.get("delta_adct", ""))
    decision_reasons = format_clinician_value(row.get("decision_reasons", ""))

    is_priority = priority_text != "通常確認"
    if instrument_label in ["ADCT", "UCT"]:
        card_class = "clinician-card-priority" if is_priority else "clinician-card-normal"
    else:
        card_class = "clinician-card-impact-high" if is_priority else "clinician-card-normal"

    st.markdown(
        f"""
        <div class="clinician-card {card_class}">
            <div class="clinician-header">
                <div class="clinician-title">{priority_icon} {priority_text}</div>
                <div class="clinician-badge">{instrument_label} #{index + 1}</div>
            </div>
            <div class="clinician-meta">送信日時：{timestamp or "—"}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.1, 1.1, 1.8])
    c1.metric("匿名コード", visit_code or "未入力")
    c2.metric("スコア", f"{total_score} / {max_score}")
    c3.metric("結果", decision or severity or "—")

    if instrument_label == "ADCT":
        h1, h2 = st.columns(2)
        h1.metric("前回ADCT", previous_adct or "初回/不明")
        h2.metric("変化量 Δ", delta_adct or "—")

        if decision_reasons:
            st.error(f"確認理由：{decision_reasons}")
        elif decision == "維持":
            st.success("非維持条件には該当していません。通常診療の中で確認してください。")
        else:
            st.info("ADCTの結果を通常診療の中で確認してください。")
    elif instrument_label == "UCT":
        if severity:
            st.info(f"UCT解釈：{severity}")
        if total_score:
            try:
                if int(float(total_score)) < 12:
                    st.error("UCTが12点未満です。症状、生活への影響、治療状況を確認してください。")
                else:
                    st.success("UCTは12点以上です。通常診療の中で確認してください。")
            except Exception:
                pass
    else:
        if severity:
            st.info(f"DLQI解釈：{severity}")

    score_cols = [col for col in row.index if re.fullmatch(r"q\d+_score", str(col))]
    score_cols = sorted(score_cols, key=lambda x: int(re.findall(r"\d+", x)[0]))

    if score_cols:
        score_text = "　".join([
            f"{col.replace('_score', '').upper()}={format_clinician_value(row.get(col, ''))}"
            for col in score_cols
        ])
        st.caption("項目別スコア：" + score_text)

    with st.expander("回答詳細を表示"):
        detail_rows = []
        for col in score_cols:
            q_num = re.findall(r"\d+", col)[0]
            answer_col = f"q{q_num}_answer"
            detail_rows.append({
                "項目": f"Q{q_num}",
                "スコア": format_clinician_value(row.get(col, "")),
                "回答": format_clinician_value(row.get(answer_col, "")),
            })

        if detail_rows:
            st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)
        else:
            st.caption("項目別データがありません。")

    st.divider()


def show_csv_tab(label: str, csv_path: Path, file_name: str):
    inject_clinician_ui_css()

    st.subheader(f"{label} 送信結果")
    st.caption("確認が必要な送信を上に出し、匿名コード・日付・優先表示で絞り込めます。")

    if not csv_path.exists():
        st.info(f"{label}データはまだありません。")
        return

    csv_bytes = csv_path.read_bytes()

    try:
        df = pd.read_csv(csv_path, on_bad_lines="skip")
    except Exception as e:
        st.warning(f"{label} CSVの読み込みに失敗しました。")
        st.caption(str(e))
        st.download_button(
            f"{label} CSVをそのままダウンロード",
            data=csv_bytes,
            file_name=file_name,
            mime="text/csv",
            use_container_width=True,
        )
        return

    if df.empty:
        st.info(f"{label}データはまだありません。")
        return

    df = df.copy()

    if "timestamp" in df.columns:
        df["_timestamp_dt"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("_timestamp_dt", ascending=False, na_position="last")
    else:
        df["_timestamp_dt"] = pd.NaT
        df = df.iloc[::-1]

    today = datetime.now(JST).date()
    valid_dates = df["_timestamp_dt"].dropna()

    total_count = len(df)
    today_count = int((df["_timestamp_dt"].dt.date == today).sum()) if not valid_dates.empty else 0
    latest_time = (
        df["_timestamp_dt"].dropna().max().strftime("%Y-%m-%d %H:%M")
        if not valid_dates.empty
        else "不明"
    )

    df["_priority_label"] = df.apply(lambda r: clinician_priority_label(r, label)[0], axis=1)
    df["_priority_icon"] = df.apply(lambda r: clinician_priority_label(r, label)[1], axis=1)
    df["_is_priority"] = df["_priority_label"] != "通常確認"
    priority_count = int(df["_is_priority"].sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("全送信数", total_count)
    m2.metric("本日の送信", today_count)
    m3.metric("確認優先", priority_count)
    m4.metric("最新送信", latest_time)

    latest_row = df.iloc[0]
    latest_label = format_clinician_value(latest_row.get("_priority_label", ""))
    latest_code = format_clinician_value(latest_row.get("visit_code", ""))
    latest_score = format_clinician_value(latest_row.get("total_score", ""))
    latest_max = format_clinician_value(latest_row.get("max_score", ""))
    latest_timestamp = format_clinician_value(latest_row.get("timestamp", ""))

    st.markdown("#### 最新1件")
    st.info(
        f"{label} / {latest_label} / 匿名コード：{latest_code or '未入力'} / "
        f"スコア：{latest_score}/{latest_max} / {latest_timestamp or '日時不明'}"
    )

    with st.expander("CSVダウンロード"):
        st.download_button(
            f"{label} CSVダウンロード",
            data=csv_bytes,
            file_name=file_name,
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("#### 絞り込み")
    f1, f2 = st.columns([1.2, 1])

    visit_query = f1.text_input(
        "匿名コードで検索",
        placeholder="例：AD001",
        key=f"{label}_visit_query",
    )

    priority_only = f2.checkbox(
        "確認優先のみ表示",
        key=f"{label}_priority_only",
    )

    filtered = df.copy()

    if visit_query and "visit_code" in filtered.columns:
        filtered = filtered[
            filtered["visit_code"].astype(str).str.contains(visit_query, case=False, na=False)
        ]

    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()
        date_range = st.date_input(
            "日付範囲",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key=f"{label}_date_range",
        )

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                (filtered["_timestamp_dt"].dt.date >= start_date)
                & (filtered["_timestamp_dt"].dt.date <= end_date)
            ]

    if priority_only:
        filtered = filtered[filtered["_is_priority"]]

    filtered = filtered.sort_values(
        by=["_is_priority", "_timestamp_dt"],
        ascending=[False, False],
        na_position="last",
    )

    st.caption(f"表示件数：{len(filtered)} / {len(df)}")

    st.markdown("#### 一覧サマリー")

    summary_cols = [
        "_priority_icon",
        "_priority_label",
        "site_id",
        "timestamp",
        "visit_code",
        "total_score",
        "max_score",
        "decision",
        "severity",
        "previous_adct",
        "delta_adct",
    ]
    existing_cols = [c for c in summary_cols if c in filtered.columns]

    summary_df = filtered[existing_cols].copy()
    rename_map = {
        "_priority_icon": "",
        "_priority_label": "確認区分",
        "site_id": "施設ID",
        "timestamp": "送信日時",
        "visit_code": "匿名コード",
        "total_score": "スコア",
        "max_score": "満点",
        "decision": "判定",
        "severity": "解釈",
        "previous_adct": "前回ADCT",
        "delta_adct": "Δ",
    }
    summary_df = summary_df.rename(columns=rename_map)

    st.dataframe(summary_df, hide_index=True, use_container_width=True)

    st.markdown("#### カード表示")

    max_cards = min(20, len(filtered))
    if max_cards == 0:
        st.info("条件に一致する送信結果はありません。")
    else:
        if max_cards == 1:
            display_count = 1
            st.caption("カード表示件数：1件")
        else:
            display_count = st.slider(
                "カード表示件数",
                min_value=1,
                max_value=max_cards,
                value=min(5, max_cards),
                key=f"{label}_display_count",
            )

        for i, (_, row) in enumerate(filtered.head(display_count).iterrows()):
            render_clinician_submission_card(row, label, i)

    with st.expander("全CSV列を確認する"):
        display_df = filtered.drop(
            columns=["_timestamp_dt", "_priority_label", "_priority_icon", "_is_priority"],
            errors="ignore",
        )
        st.dataframe(display_df, use_container_width=True)

    st.caption(
        "この画面は送信結果を見やすく整理するための医療者向け確認画面です。"
        "患者入力・保存データ・判定ロジックは変更していません。"
    )


def get_code_prefix_and_disease_name(disease_mode: str, language: str):
    if "ADCT" in disease_mode:
        return "AD", "アトピー性皮膚炎", "atopic dermatitis"
    if "UCT" in disease_mode:
        return "UC", "蕁麻疹", "urticaria"
    return "PS", "乾癬", "psoriasis"


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📝", layout="centered")

    if st.session_state.get("submission_complete"):
        print("SUBMIT_STAGE=completion_screen", flush=True)
        saved = st.session_state.get("saved_result", {})
        language = saved.get("language", "日本語")
        instrument = saved.get("instrument", "")
        total_score = saved.get("total_score", "")
        max_score = saved.get("max_score", "")

        st.success(t(language, "送信されました。", "Submitted successfully."))
        if instrument:
            st.metric(
                instrument + " " + t(language, "合計点", "total score"),
                f"{total_score} / {max_score}",
            )

        if instrument == "ADCT":
            decision = saved.get("decision", "")
            previous_adct = saved.get("previous_adct")
            delta_adct = saved.get("delta_adct")
            st.markdown("---")
            if decision == "維持":
                st.markdown("<h1 style='text-align:center; color:green;'>🟢 維持</h1>", unsafe_allow_html=True)
            else:
                st.markdown("<h1 style='text-align:center; color:red;'>🔴 非維持</h1>", unsafe_allow_html=True)
            if previous_adct is not None:
                st.markdown(
                    f"<p style='text-align:center;'>ADCT: {total_score}（前回 {previous_adct}） / Δ {delta_adct}</p>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<p style='text-align:center;'>ADCT: {total_score}（初回）</p>",
                    unsafe_allow_html=True,
                )

        st.info(
            t(
                language,
                "入力内容は保存されました。この画面を受付または医療者にお見せください。",
                "Your responses have been saved. Please show this screen to clinic staff.",
            )
        )
        st.stop()

    st.title(APP_TITLE)
    st.caption("DLQI for psoriasis / ADCT for atopic dermatitis / UCT for urticaria")
    st.caption(APP_VERSION)
    st.caption("RD4 MASTER Sheet version / ADCT-DLQI-UCT unified payload")

    language = st.sidebar.radio("Language / 言語", ["日本語", "English"], index=0)

    if LEGAL_REVIEW_MODE:
        st.info(
            t(
                language,
                "これは弁護士レビュー用の確認環境です。入力内容は送信・保存されません。",
                "This is a legal-review environment. Entries cannot be submitted or saved.",
            )
        )

    render_legal_notice(language)

    disease_param = str(st.query_params.get("disease", "ad")).lower()
    preferred_scale = "ADCT"
    if disease_param in ["psoriasis", "ps", "dlqi"]:
        preferred_scale = "DLQI"
    elif disease_param in ["urticaria", "uc", "uct"]:
        preferred_scale = "UCT"

    mode_definitions = [
        (
            "DLQI",
            t(language, "乾癬：DLQI", "Psoriasis: DLQI"),
        ),
        (
            "ADCT",
            t(
                language,
                "アトピー性皮膚炎：ADCT",
                "Atopic dermatitis: ADCT",
            ),
        ),
        (
            "UCT",
            t(language, "蕁麻疹：UCT", "Urticaria: UCT"),
        ),
    ]
    available_modes = [
        (scale, label)
        for scale, label in mode_definitions
        if scale in set(ALLOWED_SCALES)
    ]
    if not available_modes:
        st.error(
            t(
                language,
                "この施設で利用可能な質問票が設定されていません。",
                "No questionnaire is enabled for this facility.",
            )
        )
        st.stop()
    available_scales = [scale for scale, _ in available_modes]
    default_index = (
        available_scales.index(preferred_scale)
        if preferred_scale in available_scales
        else 0
    )
    disease_mode = st.sidebar.radio(
        t(language, "疾患・質問票", "Disease / questionnaire"),
        [label for _, label in available_modes],
        index=default_index,
    )

    st.info(
        t(
            language,
            "選択された質問票の指定期間を振り返って回答してください。氏名・生年月日・住所・患者ID・診察券番号などの直接個人情報は入力しないでください。",
            "Please answer based on the recall period specified by the selected questionnaire. Do not enter direct personal identifiers such as name, date of birth, address, patient ID, or medical record number.",
        )
    )

    if (
        "questionnaire_started_at" not in st.session_state
        or st.session_state.get("questionnaire_timer_disease_mode") != disease_mode
    ):
        st.session_state["questionnaire_started_at"] = datetime.now(JST).isoformat()
        st.session_state["questionnaire_timer_disease_mode"] = disease_mode

    visit_code_digits = ""
    visit_code = ""

    with st.form("questionnaire_form", clear_on_submit=False):
        code_prefix, disease_name_ja, disease_name_en = get_code_prefix_and_disease_name(disease_mode, language)

        visit_code_digits = st.text_input(
            t(
                language,
                f"匿名コード（{code_prefix} + 半角数字3桁）",
                f"Anonymous code ({code_prefix} + 3 digits)",
            ),
            max_chars=3,
            placeholder=t(language, "例：001", "Example: 001"),
            help=t(
                language,
                f"{disease_name_ja}では、患者さんは半角数字3桁のみを入力してください。アプリ側で自動的に {code_prefix}001 のような匿名コードとして保存します。氏名、患者ID、診察券番号は入力しないでください。",
                f"For {disease_name_en}, enter 3 half-width digits only. The app will automatically save it as an anonymous code such as {code_prefix}001. Do not enter name, patient ID, or medical record number.",
            ),
        )

        if visit_code_digits and re.fullmatch(r"[0-9]{3}", visit_code_digits):
            visit_code = f"{code_prefix}{visit_code_digits}"
            st.caption(
                t(
                    language,
                    f"保存される匿名コード：{visit_code}",
                    f"Anonymous code to be saved: {visit_code}",
                )
            )
        elif visit_code_digits:
            visit_code = ""
            st.error(
                t(
                    language,
                    "匿名コードは半角数字3桁で入力してください。例：001",
                    "Please enter exactly 3 half-width digits. Example: 001",
                )
            )
        else:
            visit_code = ""
            st.caption(
                t(
                    language,
                    "受付で案内された半角数字3桁を入力してください。",
                    "Please enter the 3-digit number provided by the clinic.",
                )
            )

        st.divider()

        if "DLQI" in disease_mode:
            result = render_dlqi(language)
        elif "UCT" in disease_mode:
            result = render_uct(language)
        else:
            result = render_adct(language)

        st.markdown("---")
        st.markdown(
            t(
                language,
                "**サービス利用に関する同意（必須）**",
                "**Service agreement (required)**",
            )
        )
        st.caption(
            t(
                language,
                f"画面上部の患者向け利用規約（{PATIENT_TERMS_VERSION}）とプライバシーポリシー（{PRIVACY_POLICY_VERSION}）をご確認ください。",
                f"Please review the Patient Terms ({PATIENT_TERMS_VERSION}) and Privacy Policy ({PRIVACY_POLICY_VERSION}) displayed above.",
            )
        )
        terms_consent = st.checkbox(
            t(
                language,
                "患者向け利用規約およびプライバシーポリシーを確認し、同意します。",
                "I have reviewed and agree to the Patient Terms and Privacy Policy.",
            ),
            key=f"terms_consent_{language}_{result['instrument']}",
        )

        research_consent = False
        if result["instrument"] == "ADCT" and RESEARCH_MODE:
            render_research_consent_notice(language)
            research_consent = st.checkbox(
                t(
                    language,
                    "上記の説明を確認し、本研究への参加に同意します。",
                    "I have reviewed the explanation above and agree to participate in this research study.",
                ),
                key=f"research_consent_{language}_{result['instrument']}",
            )

        submitted = st.form_submit_button(
            t(
                language,
                "レビュー環境のため送信できません"
                if LEGAL_REVIEW_MODE
                else "送信",
                "Submission disabled in review environment"
                if LEGAL_REVIEW_MODE
                else "Submit",
            ),
            use_container_width=True,
            disabled=LEGAL_REVIEW_MODE,
        )

    if submitted:
        if not terms_consent:
            st.error(
                t(
                    language,
                    "送信するには、患者向け利用規約とプライバシーポリシーを確認し、サービス利用に関する同意欄にチェックしてください。",
                    "To submit, please review the Patient Terms and Privacy Policy and check the service agreement box.",
                )
            )
            st.stop()

        if (
            result["instrument"] == "ADCT"
            and RESEARCH_MODE
            and not research_consent
        ):
            st.error(
                t(
                    language,
                    "この研究用入力を送信するには、研究参加に関する説明を確認し、研究同意欄にチェックしてください。研究参加を希望しない場合は、担当医療者へお申し出ください。",
                    "To submit this research entry, please review the research explanation and check the research-consent box. If you do not wish to participate, please tell your healthcare professional.",
                )
            )
            st.stop()

        if not re.fullmatch(r"[0-9]{3}", visit_code_digits or ""):
            st.error(
                t(
                    language,
                    "匿名コードは、半角数字3桁のみで入力してください。例：001",
                    "Please enter exactly 3 half-width digits. Example: 001",
                )
            )
            st.stop()

        if result["instrument"] == "ADCT" and any(score is None for score in result.get("scores", [])):
            st.error(
                t(
                    language,
                    "ADCTのすべての質問に回答してください。",
                    "Please answer all ADCT questions.",
                )
            )
            st.stop()

        if result["instrument"] == "UCT" and not result.get("is_complete", True):
            st.error(
                t(
                    language,
                    "UCTのすべての質問に回答してください。",
                    "Please answer all UCT questions.",
                )
            )
            st.stop()

        prefix_map = {
            "ADCT": "AD",
            "DLQI": "PS",
            "UCT": "UC",
        }
        visit_code = prefix_map[result["instrument"]] + visit_code_digits

        now_dt = datetime.now(JST)
        now = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        input_started_at = st.session_state.get("questionnaire_started_at", "")
        input_duration_seconds = None
        input_duration_minutes = None

        if input_started_at:
            try:
                started_dt = datetime.fromisoformat(str(input_started_at))
                input_duration_seconds = round((now_dt - started_dt).total_seconds(), 1)
                input_duration_minutes = round(input_duration_seconds / 60, 2)
            except Exception:
                input_duration_seconds = None
                input_duration_minutes = None

        previous_adct = None
        delta_adct = None
        decision = ""
        decision_reasons = ""
        adct_judgement = None

        if result.get("instrument") == "ADCT" and not result.get("is_complete", True):
            st.error(
                t(
                    language,
                    "ADCTの全項目と試験運用に関する確認項目に回答してから送信してください。",
                    "Please answer all ADCT items and pilot-operation questions before submitting.",
                )
            )
            st.stop()

        if result["instrument"] == "ADCT":
            previous_adct = get_previous_adct(visit_code)
            adct_judgement = judge_adct_control(
                result["total_score"],
                previous_adct,
                result["scores"],
                language,
            )
            decision = adct_judgement["decision"]
            decision_reasons = " / ".join(adct_judgement["reasons"])

            if previous_adct is not None:
                delta_adct = result["total_score"] - previous_adct

        row = {
            "timestamp": now,
            "app_version": APP_VERSION,
            "site_id": SITE_ID,
            "site_name": SITE_NAME,
            "project_id": PROJECT_ID,
            "project_phase": PROJECT_PHASE,
            "language": language,
            "disease": result["disease"],
            "instrument": result["instrument"],
            "visit_code": visit_code,
            "total_score": result["total_score"],
            "max_score": result["max_score"],
            "severity": result["severity"],
            "previous_adct": previous_adct,
            "delta_adct": delta_adct,
            "decision": decision,
            "decision_reasons": decision_reasons,
            "input_started_at": input_started_at,
            "input_submitted_at": now,
            "input_duration_seconds": input_duration_seconds,
            "input_duration_minutes": input_duration_minutes,
            "input_support": result.get("input_support", ""),
            "input_ease": result.get("input_ease", ""),
            **build_service_consent_record(now),
            "research_consent_checked": (
                True
                if result["instrument"] == "ADCT" and RESEARCH_MODE
                else ""
            ),
            "research_consent_text_version": (
                "ADCT digital PRO feasibility consent v1.0"
                if result["instrument"] == "ADCT" and RESEARCH_MODE
                else ""
            ),
            "research_consent_timestamp": (
                now
                if result["instrument"] == "ADCT" and RESEARCH_MODE
                else ""
            ),
        }

        for i, score in enumerate(result["scores"], start=1):
            row[f"q{i}_score"] = score
            row[f"q{i}_answer"] = result["answers"][i - 1]

        import time

        print("SUBMIT_STAGE=before_save", flush=True)
        _save_started = time.perf_counter()
        save_result(row)
        print(
            f"SAVE_RESULT_SECONDS={time.perf_counter() - _save_started:.3f}",
            flush=True,
        )
        print("SUBMIT_STAGE=after_save", flush=True)

        st.session_state["saved_result"] = {
            "instrument": result["instrument"],
            "total_score": result["total_score"],
            "max_score": result["max_score"],
            "language": language,
            "decision": decision,
            "previous_adct": previous_adct,
            "delta_adct": delta_adct,
        }
        st.session_state["submission_complete"] = True
        st.session_state["questionnaire_started_at"] = datetime.now(JST).isoformat()
        st.session_state["questionnaire_timer_disease_mode"] = disease_mode
        print("SUBMIT_STAGE=before_rerun", flush=True)
        st.rerun()

        st.success(t(language, "送信されました。", "Submitted successfully."))

        st.metric(
            result["instrument"] + " " + t(language, "合計点", "total score"),
            f"{result['total_score']} / {result['max_score']}",
        )

        st.caption(
            t(
                language,
                "以下の表示は診療補助のための参考情報です。最終的な判断は医療者が行ってください。",
                "The following display is reference information for clinical support. Final decisions should be made by a qualified healthcare professional.",
            )
        )

        if result["instrument"] == "ADCT":
            st.markdown("---")

            if decision == "維持":
                st.markdown(
                    "<h1 style='text-align:center; color:green;'>🟢 維持</h1>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<p style='text-align:center; font-size:20px;'>現在の治療維持が妥当と考えられる可能性があります</p>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<h1 style='text-align:center; color:red;'>🔴 非維持</h1>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<p style='text-align:center; font-size:20px;'>状態の再評価を推奨します</p>",
                    unsafe_allow_html=True,
                )

            if previous_adct is not None:
                st.markdown(
                    f"<p style='text-align:center;'>ADCT: {result['total_score']}（前回 {previous_adct}） / Δ {delta_adct}</p>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<p style='text-align:center;'>ADCT: {result['total_score']}（初回）</p>",
                    unsafe_allow_html=True,
                )

            if adct_judgement is not None:
                st.subheader(adct_judgement["display_title"])
                st.write(adct_judgement["message"])

                if adct_judgement["reasons"]:
                    st.markdown("**判定理由**" if language == "日本語" else "**Reasons for flagging**")
                    for reason in adct_judgement["reasons"]:
                        st.markdown(f"- {reason}")
                else:
                    st.caption(
                        t(
                            language,
                            "ADCT総スコアおよび前回比は、非維持条件には該当しませんでした。",
                            "The total ADCT score and change from previous ADCT did not meet the non-maintenance criteria.",
                        )
                    )

            st.caption(
                t(
                    language,
                    "「維持／非維持」はADCT回答に基づく簡易的な診療補助表示であり、治療継続・変更・中止を自動決定するものではありません。",
                    "The maintenance / non-maintenance display is a simplified clinical-support indicator based on ADCT responses and does not automatically determine whether treatment should be continued, changed, or stopped.",
                )
            )

        elif result["instrument"] == "UCT":
            st.subheader(result["severity"])
            st.write(result["interpretation"])

            if result["total_score"] < 12:
                st.error(
                    t(
                        language,
                        "UCTが12点未満です。じんましんのコントロールが不十分な可能性があります。医療者が症状、生活への影響、治療状況を確認してください。",
                        "UCT is below 12. Urticaria may be insufficiently controlled. A qualified clinician should review symptoms, quality-of-life impact, and treatment status.",
                    )
                )
            elif result["total_score"] == 16:
                st.success(
                    t(
                        language,
                        "UCTは16点です。じんましんは完全にコントロールされている可能性があります。",
                        "UCT is 16. Urticaria may be completely controlled.",
                    )
                )
            else:
                st.success(
                    t(
                        language,
                        "UCTは12点以上です。比較的コントロール良好と考えられます。",
                        "UCT is 12 or higher. Urticaria appears relatively controlled.",
                    )
                )

            st.caption(
                t(
                    language,
                    "UCTの結果はじんましんのコントロール状態を把握するための参考情報です。診療判断は医療者が総合的に行ってください。",
                    "The UCT result is reference information for understanding urticaria control. Clinical decisions should be made comprehensively by a qualified healthcare professional.",
                )
            )

        else:
            st.subheader(result["severity"])
            st.write(result["interpretation"])
            st.caption(
                t(
                    language,
                    "DLQIの結果は生活の質への影響を把握するための参考情報です。診療判断は医療者が総合的に行ってください。",
                    "The DLQI result is reference information for understanding quality-of-life impact. Clinical decisions should be made comprehensively by a qualified healthcare professional.",
                )
            )

    st.divider()

    show_admin = False
    if not EXTERNAL_FACILITY_MODE:
        show_admin = st.checkbox(
            t(language, "医療者モードを表示", "Show clinician mode")
        )

    if show_admin:
        with st.expander(
            t(language, "医療者用：送信結果確認・CSVダウンロード", "Clinician view: submission review and CSV download")
        ):
            admin_password = st.text_input(
                t(language, "管理者パスワード", "Admin password"),
                type="password",
                help=t(
                    language,
                    "RenderのEnvironmentに ADMIN_PASSWORD を設定してください。",
                    "Set ADMIN_PASSWORD in Render Environment.",
                ),
            )

            configured_password = get_secret("ADMIN_PASSWORD")

            if not configured_password:
                st.caption(
                    t(
                        language,
                        "ADMIN_PASSWORD が未設定のため、CSV閲覧は無効です。",
                        "CSV view is disabled because ADMIN_PASSWORD is not configured.",
                    )
                )
            elif admin_password == configured_password:
                tab_adct, tab_dlqi, tab_uct = st.tabs(["ADCT", "DLQI", "UCT"])

                with tab_adct:
                    show_csv_tab("ADCT", CSV_PATH_ADCT, "adct_results.csv")

                with tab_dlqi:
                    show_csv_tab("DLQI", CSV_PATH_DLQI, "dlqi_results.csv")

                with tab_uct:
                    show_csv_tab("UCT", CSV_PATH_UCT, "uct_results.csv")

            elif admin_password:
                st.error(t(language, "パスワードが違います。", "Incorrect password."))

    st.caption(
        t(
            language,
            "このアプリは診療補助目的です。診断、治療方針、薬剤選択、治療継続・中止を自動的に決定するものではありません。最終的な診療判断は医療者が行ってください。",
            "For clinical support only. This app does not provide diagnosis, treatment plans, medication selection, or automatic treatment continuation/discontinuation decisions. Final clinical decisions should be made by a qualified clinician.",
        )
    )

    render_credit_footer(language)

    if "ADCT" in disease_mode:
        render_adct_partner_notice(language)


if __name__ == "__main__":
    main()
