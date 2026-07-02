import json
import re
import os
import openai
from openai import OpenAI
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.database.connection import db
from src.core.config import settings

router = APIRouter()

class NarrativeResponse(BaseModel):
    cust_info_id: str
    narrative: str
    status: str


@router.get("/customer/{cust_info_id}/payload")
async def get_payload(
    cust_info_id: str,
    country_code: str,
    inst_code: str,
    day_date: str
):
    """Fetch the full customer JSON payload (KYC, metrics, boundaries) from database."""
    sql_fetch = """
        SELECT AI_PAYLOAD 
        FROM BI_DWH.PIO_COLL_AI_NBA_ACTIONS
        WHERE CUST_INFO_ID = :cust_info_id
          AND COUNTRY_CODE = :country_code
          AND INST_CODE = :inst_code
          AND DAY_DATE = TO_DATE(:day_date, 'YYYY-MM-DD')
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_fetch, {
                "cust_info_id": cust_info_id,
                "country_code": country_code,
                "inst_code": inst_code,
                "day_date": day_date
            })
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Customer action record not found for given date.")
            
            ai_payload = row[0]
            if hasattr(ai_payload, 'read'):
                ai_payload = ai_payload.read()
                
            if not ai_payload:
                raise HTTPException(status_code=404, detail="AI_PAYLOAD column is empty for this customer.")
                
            # Parse database string as a clean JSON response
            if isinstance(ai_payload, str):
                try:
                    payload_dict = json.loads(ai_payload)
                    return payload_dict
                except Exception as json_err:
                    raise HTTPException(status_code=500, detail=f"Failed to parse database AI_PAYLOAD as JSON: {json_err}")
            return ai_payload
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


def clean_llm_response(raw_text: str) -> str:
    """Strip internal reasoning / scratchpad blocks from LLM output.

    Removes content enclosed in <scratchpad>...</scratchpad> and
    <think>...</think> tags (case-insensitive, dotall) before the
    narrative is returned to the caller. This prevents Qwen-style chain-of-
    thought leakage from reaching the UI or being cached in the database.

    Args:
        raw_text (str): The raw string returned by the LLM.

    Returns:
        str: Clean narrative text, stripped of all scratchpad/think blocks.
    """
    # Strip <scratchpad>...</scratchpad>
    clean = re.sub(r"<scratchpad>.*?</scratchpad>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
    # Strip <think>...</think> (Qwen3 reasoning tag)
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL | re.IGNORECASE)
    # Collapse excessive blank lines left by removal
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def _build_llm_client() -> tuple[OpenAI, str]:
    """Build the correct OpenAI-compatible client based on configuration.

    Returns:
        tuple[OpenAI, str]: (client instance, model name to use)
    """
    if settings.USE_OPENAI_API:
        client = OpenAI(api_key=settings.OPENAI_API_KEY.get_secret_value())
        model_name = settings.OPENAI_MODEL_NAME
    else:
        client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY.get_secret_value()
        )
        model_name = settings.LLM_MODEL_NAME
    return client, model_name


@router.get("/customer/{cust_info_id}/narrative", response_model=NarrativeResponse)
async def get_narrative(
    cust_info_id: str,
    country_code: str,
    inst_code: str,
    day_date: str
):
    """Lazy-load the LLM narrative for a specific customer.

    If the narrative is already generated and cached in the database, it
    returns the cached version immediately. If the record is PENDING, it
    invokes the configured LLM (OpenAI or LM Studio), applies scratchpad
    cleaning, caches the result, and returns the final narrative.
    """

    sql_fetch = """
        SELECT AI_PAYLOAD, AI_NARRATIVE 
        FROM BI_DWH.PIO_COLL_AI_NBA_ACTIONS
        WHERE CUST_INFO_ID = :cust_info_id
          AND COUNTRY_CODE = :country_code
          AND INST_CODE = :inst_code
          AND DAY_DATE = TO_DATE(:day_date, 'YYYY-MM-DD')
    """

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_fetch, {
                "cust_info_id": cust_info_id,
                "country_code": country_code,
                "inst_code": inst_code,
                "day_date": day_date
            })
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Customer action not found for given date.")

            ai_payload, ai_narrative = row

            # Convert Oracle CLOBs to Python strings
            if hasattr(ai_narrative, 'read'):
                ai_narrative = ai_narrative.read()
            if hasattr(ai_payload, 'read'):
                ai_payload = ai_payload.read()

            # 1. Return cached narrative if already generated
            if ai_narrative and ai_narrative != 'PENDING':
                return NarrativeResponse(
                    cust_info_id=cust_info_id,
                    narrative=ai_narrative,
                    status="CACHED"
                )

            # 2. Load system prompt from disk
            prompt_path = os.path.join(settings.BASE_DIR, "explainability", "llm_system_prompt.md")
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
            except Exception as read_exc:
                raise HTTPException(status_code=500, detail=f"Failed to read system prompt: {read_exc}")

            # 3. Call LLM (OpenAI or LM Studio based on USE_OPENAI_API toggle)
            try:
                client, model_name = _build_llm_client()

                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": str(ai_payload)}
                    ],
                    temperature=0.4,        # Balanced: structured output without sampler loops
                    max_tokens=1200,        # Enough for all 5 sections without runaway generation
                    frequency_penalty=0.1,  # Discourage repetitive phrasing
                )
                raw_narrative = response.choices[0].message.content or ""

                # 4. Strip internal scratchpad / chain-of-thought leakage
                generated_narrative = clean_llm_response(raw_narrative)

            except openai.APIConnectionError:
                backend = "OpenAI API" if settings.USE_OPENAI_API else "local LLM server (LM Studio)"
                generated_narrative = f"Narrative generation unavailable. Please check {backend}."
            except Exception as llm_exc:
                generated_narrative = f"Error generating narrative: {llm_exc}"

            # 5. Persist generated narrative to DB (CLOB)
            sql_update = """
                UPDATE BI_DWH.PIO_COLL_AI_NBA_ACTIONS
                SET AI_NARRATIVE = :narrative
                WHERE CUST_INFO_ID = :cust_info_id
                  AND COUNTRY_CODE = :country_code
                  AND INST_CODE = :inst_code
                  AND DAY_DATE = TO_DATE(:day_date, 'YYYY-MM-DD')
            """

            import oracledb
            cursor.setinputsizes(narrative=oracledb.DB_TYPE_CLOB)
            cursor.execute(sql_update, {
                "narrative": generated_narrative,
                "cust_info_id": cust_info_id,
                "country_code": country_code,
                "inst_code": inst_code,
                "day_date": day_date
            })
            conn.commit()

            return NarrativeResponse(
                cust_info_id=cust_info_id,
                narrative=generated_narrative,
                status="GENERATED"
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

