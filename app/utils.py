import logging
import os
import random
import time
from typing import Dict, List, Optional

import numpy as np
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
# (issue llnl#26). Ordered rather than random so behavior is deterministic and
# testable; the intent of "randomly select a working free model" is resilience
# across a pool, which this delivers.
DEFAULT_FREE_FALLBACK_MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-chat:free",
    "mistralai/mistral-7b-instruct:free",
]

# Marker prefix identifying a model-unavailable outcome (drives fallback).
_MODEL_UNAVAILABLE_PREFIX = "Error: Model unavailable or delisted"


def _model_candidates(primary: str, fallbacks: Optional[List[str]]) -> List[str]:
    """Ordered, de-duplicated candidate list: primary first, then fallbacks."""
    candidates = [primary, *(fallbacks if fallbacks is not None else DEFAULT_FREE_FALLBACK_MODELS)]
    ordered = []
    for m in candidates:
        if m and m not in ordered:
            ordered.append(m)
    return ordered


def _attempt_model(client: "OpenAI", model: str, prompt: str, temperature: float) -> str:
    """Single-model call with the existing retry/backoff. Returns the content or
    an 'Error: ...' string; a model-unavailable result uses the marker prefix so
    the caller can fall back to another model."""
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
            if "Rate limit exceeded" in error_str:
                logger.warning(f"Rate limit exceeded (attempt {attempt + 1}/{max_retries}): {error_str}")
                last_error_message = f"Rate limit exceeded: {error_str}"
            else:
                logger.error(f"API call failed (attempt {attempt + 1}/{max_retries}): {error_str}")
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
    unavailable/delisted, automatically falls back to working free models
    (issue llnl#26) so a single delisted model does not fail every run. Falls
    back only on model-unavailable — not on auth (same key won't help) or
    rate-limit (transient, already retried). Auth/parse/other errors and the
    final model-unavailable error still propagate to the caller.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        # openai>=1 raises from the OpenAI() constructor on a missing key, so
        # check before constructing the client.
        logger.error("OPENROUTER_API_KEY environment variable not set.")
        return "Error: OpenRouter API key not set."

    client = OpenAI(
        base_url=config.get("openrouter_base_url"),
        api_key=api_key,
    )
    primary = model or config.get("llm_model")
    if not primary:
        logger.error("LLM model not configured in config.yaml")
        return "Error: LLM model not configured."

    candidates = _model_candidates(primary, fallback_models)
    result = f"{_MODEL_UNAVAILABLE_PREFIX} (no candidates)."
    for candidate in candidates:
        result = _attempt_model(client, candidate, prompt, temperature)
        if result.startswith(_MODEL_UNAVAILABLE_PREFIX):
            logger.warning("Model '%s' unavailable; trying next fallback.", candidate)
            continue
        return result  # success, or a non-availability error we must not mask
    # Every candidate was unavailable — surface the last model-unavailable error.
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
