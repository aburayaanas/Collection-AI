import json
import re
import openai
from openai import OpenAI
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from src.database.connection import db
from src.core.config import settings
from src.core.logger import get_logger
from src.core import paths

logger = get_logger(__name__)

router = APIRouter()


class NarrativeResponse(BaseModel):
    cust_info_id: str
    narrative: str
    status: str  # "CACHED", "GENERATED", or "FAILED"


# Known error prefixes or corrupted strings that must NEVER be treated as valid cache
INVALID_NARRATIVE_PREFIXES = (
    "Error",
    "Narrative generation unavailable",
    "Executive narrative summary is being",
    "Failed to",
    "APIConnectionError",
    "AuthenticationError",
    "RateLimitError",
    "Timeout",
)


def is_valid_narrative(text: Optional[str]) -> bool:
    """Validate whether a narrative string is a complete, usable briefing.

    Returns False for empty strings, 'PENDING', error messages, or broken JSON.
    """
    if not text or not isinstance(text, str):
        return False
    trimmed = text.strip()
    if not trimmed or trimmed.upper() in ("PENDING", "NONE", "NULL", "NAN"):
        return False
    if any(trimmed.startswith(prefix) for prefix in INVALID_NARRATIVE_PREFIXES):
        return False
    # A complete 5-section narrative should be substantive (at least 100 characters)
    if len(trimmed) < 100:
        return False
    # If the model accidentally output broken/truncated JSON
    if trimmed.startswith("{") and not trimmed.endswith("}"):
        return False
    return True


def clean_llm_response(raw_text: str) -> str:
    """Strip internal reasoning, scratchpad tags, and markdown code fences from LLM output.

    Args:
        raw_text (str): The raw string returned by the LLM.

    Returns:
        str: Clean markdown narrative text.
    """
    if not raw_text:
        return ""

    # Strip <scratchpad>...</scratchpad> and unclosed <scratchpad>
    clean = re.sub(r"<scratchpad>.*?</scratchpad>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<scratchpad>.*", "", clean, flags=re.DOTALL | re.IGNORECASE)

    # Strip <think>...</think> and unclosed <think> (reasoning models)
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<think>.*", "", clean, flags=re.DOTALL | re.IGNORECASE)

    # Strip outer code fences if the model wrapped the entire output in ```markdown or ```
    clean = clean.strip()
    if clean.startswith("```"):
        # Remove opening fence
        clean = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", clean)
        # Remove closing fence if present
        clean = re.sub(r"\n?```$", "", clean)

    # Collapse excessive blank lines
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def _build_llm_client() -> tuple[OpenAI, str]:
    """Build the OpenAI-compatible client based on active settings.

    Returns:
        tuple[OpenAI, str]: (client instance, model name to use)
    """
    if settings.USE_OPENAI_API:
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            timeout=45.0
        )
        model_name = settings.OPENAI_MODEL_NAME
    else:
        client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY.get_secret_value(),
            timeout=60.0
        )
        model_name = settings.LLM_MODEL_NAME
    return client, model_name


@router.get("/customer/{cust_info_id}/payload")
async def get_payload(
    cust_info_id: str,
    country_code: str,
    inst_code: str,
    day_date: str
):
    """Fetch the full customer JSON payload (KYC, metrics, boundaries) from database."""
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
                raise HTTPException(status_code=404, detail="Customer action record not found for given date.")
            
            ai_payload, ai_narrative = row
            if hasattr(ai_payload, 'read'):
                ai_payload = ai_payload.read()
            if hasattr(ai_narrative, 'read'):
                ai_narrative = ai_narrative.read()
                
            if not ai_payload:
                raise HTTPException(status_code=404, detail="AI_PAYLOAD column is empty for this customer.")
                
            if isinstance(ai_payload, str):
                try:
                    payload_dict = json.loads(ai_payload)
                    # Automatically attach cached narrative if already generated in DB
                    if is_valid_narrative(ai_narrative):
                        payload_dict["ai_narrative"] = ai_narrative
                    return payload_dict
                except Exception as json_err:
                    raise HTTPException(status_code=500, detail=f"Failed to parse database AI_PAYLOAD as JSON: {json_err}")
            return ai_payload
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer/{cust_info_id}/narrative", response_model=NarrativeResponse)
async def get_narrative(
    cust_info_id: str,
    country_code: str,
    inst_code: str,
    day_date: str,
    force_regenerate: bool = Query(default=False, description="Bypass cache and force fresh generation")
):
    """Lazy-load the LLM narrative for a specific customer with bulletproof caching & validation.

    - If a valid narrative is cached and force_regenerate is False, returns CACHED.
    - If corrupted/error text was stored, it treats it as PENDING and regenerates cleanly.
    - If generation fails, it returns an informative error WITHOUT corrupting the DB cache.
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

            if hasattr(ai_narrative, 'read'):
                ai_narrative = ai_narrative.read()
            if hasattr(ai_payload, 'read'):
                ai_payload = ai_payload.read()

            # 1. Return valid cached narrative if not forcing regeneration
            if not force_regenerate and is_valid_narrative(ai_narrative):
                logger.info(f"Serving valid cached narrative for customer {cust_info_id}")
                return NarrativeResponse(
                    cust_info_id=cust_info_id,
                    narrative=ai_narrative,
                    status="CACHED"
                )

            # 2. Validate payload presence
            if not ai_payload or str(ai_payload).strip() in ("", "None", "NULL"):
                raise HTTPException(status_code=400, detail="Customer AI_PAYLOAD is empty. Cannot generate narrative.")

            # 3. Load optimized system prompt (bundled resource, not app data)
            prompt_path = paths.resource_path("src", "explainability", "llm_system_prompt.md")
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
            except Exception as read_exc:
                logger.error(f"Failed to read system prompt file: {read_exc}")
                raise HTTPException(status_code=500, detail=f"Failed to read system prompt: {read_exc}")

            # 4. Invoke LLM with error isolation
            generated_narrative = ""
            generation_error = None

            try:
                client, model_name = _build_llm_client()
                logger.info(f"Generating narrative for customer {cust_info_id} using model '{model_name}'...")

                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": str(ai_payload)}
                    ],
                    temperature=0.3,
                    max_tokens=3000,
                    frequency_penalty=0.1,
                )

                choice = response.choices[0]
                msg = choice.message
                raw_text = msg.content or ""

                # Support reasoning models that place thinking in reasoning_content
                if not raw_text.strip() and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                    raw_text = msg.reasoning_content

                generated_narrative = clean_llm_response(raw_text)

            except openai.APIConnectionError as conn_err:
                backend = "OpenAI API" if settings.USE_OPENAI_API else "local LLM server (LM Studio)"
                generation_error = f"Narrative generation unavailable. Could not connect to {backend}: {conn_err}"
                logger.warning(generation_error)
            except Exception as llm_exc:
                generation_error = f"Error generating narrative: {llm_exc}"
                logger.error(generation_error)

            # 5. Strictly Validate Before Persisting to Database
            # ZERO ERROR CACHING: Only save if we have a valid, substantial briefing
            if is_valid_narrative(generated_narrative):
                logger.info(f"Persisting valid generated narrative ({len(generated_narrative)} chars) to DB for customer {cust_info_id}")
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

            # If generation failed or produced invalid/empty output:
            # DO NOT overwrite database with errors. Leave DB as PENDING so retry is always possible.
            error_message = generation_error or "LLM generation produced empty or truncated output. Please retry."
            logger.warning(f"Narrative generation unsuccessful for {cust_info_id}. DB state remains PENDING. Error: {error_message}")

            return NarrativeResponse(
                cust_info_id=cust_info_id,
                narrative=error_message,
                status="FAILED"
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Unexpected error in get_narrative endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
