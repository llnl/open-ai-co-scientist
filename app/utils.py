import logging
import os
import random
import time
from typing import Dict, List, Optional

import numpy as np
import requests
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Import config loading function and config object
from .config import config

# --- Logging Setup ---
# Configure a root logger or a specific logger for the app
# Using a basic configuration here, can be enhanced
logging.basicConfig(
    level=config.get("logging_level", logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("aicoscientist")  # Use a specific name for the app logger

# Optional: Add file handler based on config (if needed globally)
# log_filename_base = config.get('log_file_name', 'app')
# timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
# file_handler = logging.FileHandler(f"{log_filename_base}_{timestamp}.txt")
# formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
# file_handler.setFormatter(formatter)
# logger.addHandler(file_handler)


# --- Secret Redaction ---
def redact_secrets(text: str) -> str:
    """Removes the API key from text destined for logs or user-facing errors."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key and api_key in text:
        return text.replace(api_key, "***REDACTED***")
    return text


# --- Error Classification ---
def classify_llm_error(error_text: str) -> str:
    """Maps a raw LLM/API error string to a short, user-actionable category.

    Used to turn a silent 'no hypotheses' outcome into a message that names the
    real cause (see GOALS.md theme 1: errors must be actionable, never silent).
    """
    text = (error_text or "").lower()
    # Order matters: most specific first.
    if "api key not set" in text or "401" in text or "authentication with openrouter failed" in text:
        return "Missing or invalid API key"
    if "timed out" in text or "timeout" in text:
        return "Model provider timed out"
    if "rate limit" in text:
        return "Rate limited by the model provider"
    if "model unavailable" in text or "no endpoints found" in text or "not a valid model" in text or "404" in text:
        return "Model unavailable or delisted"
    if "could not parse" in text or "invalid json" in text:
        return "Model returned unparsable output"
    if "model not configured" in text:
        return "LLM model not configured"
    return "LLM/API error"


# --- LLM Interaction ---
# Curated free models tried, in order, when the primary model is unavailable
# or delisted. Keeps the public demo working when a single free model dies
# (issue llnl#26). Fallback candidates are fetched live from OpenRouter (the
# source of truth for what is actually available) rather than hardcoded — a
# static list rots as free models are delisted, which is the very failure this
# fixes. The list below is only a last resort if the live list can't be fetched.
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Bound the number of alternative models tried when the primary is unavailable,
# so a fully-broken OpenRouter doesn't trigger a long chain of calls.
MAX_FALLBACK_ATTEMPTS = 4

# Compact free models to prefer for the public demo. Larger free models can be
# accurate but may not finish a multi-call cycle before the Hugging Face UI
# timeout. The live OpenRouter list is still the source of truth: these IDs are
# tried first only when OpenRouter reports them as currently available.
PREFERRED_FREE_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemma-3-4b-it:free",
    "qwen/qwen3-4b:free",
    "qwen/qwen3-8b:free",
]

# Last-resort static fallback, used only when the live model list is unreachable.
# Kept minimal; verified members can still be delisted, so the live list wins.
STATIC_FALLBACK_MODELS = [
    *PREFERRED_FREE_MODELS,
    "meta-llama/llama-3.3-70b-instruct:free",
]

# Marker prefixes identifying outcomes that a *different* model might fix, so
# call_llm should try another candidate. Auth and missing-key/not-configured
# errors are terminal (a different model won't help) and are NOT listed here.
_MODEL_UNAVAILABLE_PREFIX = "Error: Model unavailable or delisted"
_RATE_LIMIT_PREFIX = "Error: Rate limit exceeded"
_TIMEOUT_PREFIX = "Error: Model provider timed out"
_RECOVERABLE_PREFIXES = (_MODEL_UNAVAILABLE_PREFIX, _RATE_LIMIT_PREFIX, _TIMEOUT_PREFIX, "Error: API call failed")


def _recoverable_with_another_model(result: str) -> bool:
    """True if ``result`` is an error a different model might succeed on."""
    return any(result.startswith(p) for p in _RECOVERABLE_PREFIXES)


# Cache of live free-model IDs (fetched lazily, only when a fallback is needed).
_free_models_cache: Optional[List[str]] = None


def fetch_free_models(force_refresh: bool = False) -> List[str]:
    """Return the currently-available free model IDs from OpenRouter (cached).

    Returns [] on any failure (network, parse) so callers fall back to the
    static list. Never raises. The API key is used if present but not required
    for the public models endpoint.
    """
    global _free_models_cache
    if _free_models_cache is not None and not force_refresh:
        return _free_models_cache
    try:
        headers = {}
        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        ids = [m.get("id") for m in resp.json().get("data", []) if m.get("id")]
        _free_models_cache = filter_free_models(sorted(ids))
        logger.info("Fetched %d free models from OpenRouter for fallback.", len(_free_models_cache))
        return _free_models_cache
    except Exception as e:
        logger.warning("Could not fetch live model list for fallback: %s", redact_secrets(str(e)))
        return []


def order_free_models_for_demo(models: List[str]) -> List[str]:
    """Return free models with compact demo-friendly candidates first.

    ``models`` is normally OpenRouter's live list. We keep only free IDs,
    de-duplicate while preserving input order, then move preferred compact
    models to the front if they are present.
    """
    free_models = []
    for model in filter_free_models(models):
        if model and model not in free_models:
            free_models.append(model)

    ordered = []
    for model in PREFERRED_FREE_MODELS:
        if model in free_models:
            ordered.append(model)
    for model in free_models:
        if model not in ordered:
            ordered.append(model)
    return ordered


def get_fallback_models(primary: Optional[str] = None) -> List[str]:
    """Working free models to try when ``primary`` is unavailable — the live
    OpenRouter list if reachable, else the static last resort — excluding
    ``primary`` itself."""
    source = order_free_models_for_demo(fetch_free_models()) or STATIC_FALLBACK_MODELS
    return [m for m in source if m and m != primary]


def _model_candidates(primary: str, fallbacks: Optional[List[str]]) -> List[str]:
    """Ordered, de-duplicated candidate list: primary first, then fallbacks."""
    ordered = []
    for m in [primary, *(fallbacks or [])]:
        if m and m not in ordered:
            ordered.append(m)
    return ordered


def _is_rate_limit(error_str: str) -> bool:
    """Detect OpenRouter/provider rate-limit errors. Deliberately broad: the API
    reports these as '429', 'Rate limit exceeded', or 'temporarily rate-limited'
    depending on the upstream provider."""
    low = error_str.lower()
    return "429" in error_str or "rate limit" in low or "rate-limited" in low


def _is_timeout(error_str: str) -> bool:
    """Detect SDK, HTTP, and provider timeout messages."""
    low = error_str.lower()
    return "timeout" in low or "timed out" in low or "read timed out" in low


def _attempt_model(
    client: "OpenAI", model: str, prompt: str, temperature: float, max_retries: Optional[int] = None
) -> str:
    """Single-model call with retry/backoff. Returns the content or an
    'Error: ...' string. Model-unavailable and rate-limit outcomes use marker
    prefixes (see _RECOVERABLE_PREFIXES) so the caller can try a different model.
    ``max_retries`` overrides the config default — pass 1 for a quick probe when
    other candidates are available (avoids long backoff on one flaky model)."""
    if max_retries is None:
        max_retries = config.get("max_retries", 3)
    initial_delay = config.get("initial_retry_delay", 1)
    last_error_message = "API call failed after multiple retries."

    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            if completion.choices and len(completion.choices) > 0:
                return completion.choices[0].message.content or ""
            else:
                logger.error("No choices in the LLM response: %s", completion)
                last_error_message = f"No choices in the response: {completion}"

        except Exception as e:
            error_str = redact_secrets(str(e))
            if "401" in error_str or "No auth credentials found" in error_str:
                logger.error(f"Authentication failed (401 Unauthorized): {error_str}")
                return (
                    "Authentication with OpenRouter failed (401 Unauthorized). "
                    "Please check that your OPENROUTER_API_KEY environment variable is set and valid "
                    "in the environment where the server is running. No hypotheses can be generated until this is resolved."
                )
            if "No endpoints found" in error_str or "not a valid model" in error_str or "404" in error_str:
                logger.error(f"Model unavailable: {error_str}")
                return (
                    f"{_MODEL_UNAVAILABLE_PREFIX} ('{model}'). "
                    "The selected model may have been removed from OpenRouter or is temporarily unreachable. "
                    "Try selecting a different model. Details: " + error_str
                )
            if _is_rate_limit(error_str):
                # Return immediately so the caller can try a different free model
                # (they have independent rate limits) rather than waiting here.
                logger.warning(f"Rate limited on '{model}': {error_str}")
                return f"{_RATE_LIMIT_PREFIX} ('{model}'). Details: " + error_str
            if _is_timeout(error_str):
                # A slow free provider should not consume the whole 5-minute
                # Gradio cycle budget. Move to another model immediately.
                logger.warning(f"Provider timed out on '{model}': {error_str}")
                return f"{_TIMEOUT_PREFIX} ('{model}'). Details: " + error_str
            logger.error(f"API call failed on '{model}' (attempt {attempt + 1}/{max_retries}): {error_str}")
            last_error_message = f"API call failed: {error_str}"

            if attempt < max_retries - 1:
                wait_time = initial_delay * (2**attempt)
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error("Max retries reached. Giving up.")
                break

    return f"Error: {last_error_message}"


def call_llm(
    prompt: str,
    temperature: float = 0.7,
    model: Optional[str] = None,
    fallback_models: Optional[List[str]] = None,
) -> str:
    """Calls an LLM via OpenRouter, returning the response text.

    Tries the primary model (``model`` or ``config['llm_model']``) and, if it is
    unavailable, rate-limited, or too slow, automatically falls back to working
    free models (issue llnl#26/#32) so a single bad model does not fail every
    run. Auth/parse/final provider errors still propagate to the caller.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        # openai>=1 raises from the OpenAI() constructor on a missing key, so
        # check before constructing the client.
        logger.error("OPENROUTER_API_KEY environment variable not set.")
        return "Error: OpenRouter API key not set."

    # max_retries=0 disables the OpenAI SDK's own Retry-After backoff (which can
    # block ~30s on a rate-limited free model); call_llm controls retries itself.
    client = OpenAI(
        base_url=config.get("openrouter_base_url"),
        api_key=api_key,
        max_retries=0,
        timeout=config.get("llm_request_timeout_seconds", 30),
    )
    primary = model or config.get("llm_model")
    if not primary:
        logger.error("LLM model not configured in config.yaml")
        return "Error: LLM model not configured."

    # Happy path: try the primary model. No fallback fetch unless it's needed.
    result = _attempt_model(client, primary, prompt, temperature)
    if not _recoverable_with_another_model(result):
        return result  # success, or a terminal error (auth) we must not mask

    # Primary failed with something another model might fix (unavailable, rate
    # limited, provider error): try working free models — the live OpenRouter
    # list (fetched now) unless the caller passed an explicit list. Quick probes
    # (max_retries=1) so we move past a flaky model to the next one fast.
    logger.warning("Primary model '%s' failed (%s); trying other free models.", primary, result[:60])
    fallbacks = fallback_models if fallback_models is not None else get_fallback_models(primary)
    for candidate in _model_candidates(primary, fallbacks)[1 : 1 + MAX_FALLBACK_ATTEMPTS]:
        logger.warning("Trying fallback model '%s'.", candidate)
        result = _attempt_model(client, candidate, prompt, temperature, max_retries=1)
        if not _recoverable_with_another_model(result):
            return result
    # Every candidate failed — surface the last error.
    return result


# --- Environment Detection ---
def is_huggingface_space() -> bool:
    """
    Detect if the application is running in Hugging Face Spaces.
    Returns True if running in HF Spaces, False otherwise.
    """
    # Primary indicators - HF Spaces sets these environment variables
    hf_env_vars = ["SPACE_ID", "SPACE_AUTHOR_NAME", "SPACES_BUILDKIT_VERSION", "HF_HOME"]

    for var in hf_env_vars:
        if os.getenv(var):
            logger.info(f"Detected Hugging Face Spaces environment via {var}")
            return True

    # Secondary indicator - hostname patterns
    hostname = os.getenv("HOSTNAME", "")
    if "huggingface.co" in hostname.lower():
        logger.info(f"Detected Hugging Face Spaces environment via hostname: {hostname}")
        return True

    return False


def get_deployment_environment() -> str:
    """
    Get a string description of the current deployment environment.
    Returns: 'Hugging Face Spaces', 'Local Development', or 'Unknown'
    """
    if is_huggingface_space():
        return "Hugging Face Spaces"
    elif os.getenv("LOCAL_DEV") or not os.getenv("PORT"):
        return "Local Development"
    else:
        return "Unknown"


def filter_free_models(all_models: List[str]) -> List[str]:
    """
    Filters a list of model IDs to include only those with ':free' in their name.
    """
    return [model for model in all_models if ":free" in model]


# --- ID Generation ---
def generate_unique_id(prefix="H") -> str:
    """Generates a unique identifier string."""
    return f"{prefix}{random.randint(1000, 9999)}"


# --- VIS.JS Graph Data Generation ---
def generate_visjs_data(adjacency_graph: Dict) -> Dict[str, list]:
    """Generates node and edge data lists for vis.js graph (for JSON serialization)."""
    nodes = []
    edges = []

    if not isinstance(adjacency_graph, dict):
        logger.error(f"Invalid adjacency_graph type: {type(adjacency_graph)}. Expected dict.")
        return {"nodes": [], "edges": []}

    for node_id, connections in adjacency_graph.items():
        nodes.append({"id": node_id, "label": node_id})
        if isinstance(connections, list):
            for connection in connections:
                if isinstance(connection, dict) and "similarity" in connection and "other_id" in connection:
                    similarity_val = connection.get("similarity")
                    if isinstance(similarity_val, (int, float)) and similarity_val > 0.2:
                        edges.append(
                            {
                                "from": node_id,
                                "to": connection["other_id"],
                                "label": f"{similarity_val:.2f}",
                                "arrows": "to",
                            }
                        )
                else:
                    logger.warning(f"Skipping invalid connection format for node {node_id}: {connection}")
        else:
            logger.warning(f"Skipping invalid connections format for node {node_id}: {connections}")

    return {"nodes": nodes, "edges": edges}


# --- Similarity Calculation ---
_sentence_transformer_model = None


def get_sentence_transformer_model():
    """Loads and returns a singleton instance of the sentence transformer model."""
    global _sentence_transformer_model
    if _sentence_transformer_model is None:
        model_name = config.get("sentence_transformer_model", "all-MiniLM-L6-v2")
        try:
            logger.info(f"Loading sentence transformer model: {model_name}...")
            _sentence_transformer_model = SentenceTransformer(model_name)
            logger.info("Sentence transformer model loaded successfully.")
        except ImportError:
            logger.error("Failed to import sentence_transformers. Please install it: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Failed to load sentence transformer model '{model_name}': {e}")
            raise  # Re-raise after logging
    return _sentence_transformer_model


def similarity_score(textA: str, textB: str) -> float:
    """Calculates cosine similarity between two texts using sentence embeddings."""
    try:
        if not textA.strip() or not textB.strip():
            logger.warning("Empty string provided to similarity_score.")
            return 0.0

        model = get_sentence_transformer_model()
        if model is None:  # Check if model loading failed previously
            return 0.0  # Or handle error appropriately

        embedding_a = model.encode(textA, convert_to_tensor=True)
        embedding_b = model.encode(textB, convert_to_tensor=True)

        # Ensure embeddings are 2D numpy arrays for cosine_similarity
        embedding_a_np = embedding_a.cpu().numpy().reshape(1, -1)
        embedding_b_np = embedding_b.cpu().numpy().reshape(1, -1)

        similarity = cosine_similarity(embedding_a_np, embedding_b_np)[0][0]

        # Clamp the value between 0.0 and 1.0
        similarity = float(np.clip(similarity, 0.0, 1.0))

        # logger.debug(f"Similarity score: {similarity:.4f}") # Use debug level
        return similarity
    except Exception as e:
        logger.error(f"Error calculating similarity score: {e}", exc_info=True)  # Log traceback
        return 0.0  # Return 0 on error instead of 0.5
