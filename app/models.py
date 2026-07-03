from typing import Dict, List, Optional

from pydantic import BaseModel

# Import config to access defaults easily
from .config import config

# Assuming logger is configured elsewhere or passed in if needed within methods
# If models need logging, consider passing a logger instance during initialization
# or using a globally accessible logger configured in utils.py or config.py.
# For simplicity, direct logging calls are removed from models for now.
# logger = logging.getLogger(__name__) # Example if models needed their own logger

###############################################################################
# Data Models
###############################################################################


class Hypothesis:
    def __init__(self, hypothesis_id: str, title: str, text: str):
        self.hypothesis_id = hypothesis_id
        self.title = title
        self.text = text
        self.novelty_review: Optional[str] = None  # "HIGH", "MEDIUM", "LOW"
        self.feasibility_review: Optional[str] = None
        self.elo_score: float = 1200.0  # initial Elo score
        self.review_comments: List[str] = []
        self.references: List[str] = []
        self.is_active: bool = True
        self.parent_ids: List[str] = []  # Store IDs of parent hypotheses

    def to_dict(self) -> dict:
        return {
            "id": self.hypothesis_id,
            "title": self.title,
            "text": self.text,
            "novelty_review": self.novelty_review,
            "feasibility_review": self.feasibility_review,
            "elo_score": self.elo_score,
            "review_comments": self.review_comments,
            "references": self.references,
            "is_active": self.is_active,
            "parent_ids": self.parent_ids,  # Include parent IDs
        }


class ResearchGoal:
    def __init__(
        self,
        description: str,
        constraints: Optional[Dict] = None,
        llm_model: Optional[str] = None,
        num_hypotheses: Optional[int] = None,
        generation_temperature: Optional[float] = None,
        reflection_temperature: Optional[float] = None,
        elo_k_factor: Optional[int] = None,
        top_k_hypotheses: Optional[int] = None,
    ):
        self.description = description
        self.constraints = constraints if constraints else {}
        # Store runtime settings, falling back to config defaults if not provided
        self.llm_model = (
            llm_model if llm_model else config.get("llm_model", "google/gemini-flash-1.5")
        )  # Example default
        self.num_hypotheses = num_hypotheses if num_hypotheses is not None else config.get("num_hypotheses", 3)
        self.generation_temperature = (
            generation_temperature
            if generation_temperature is not None
            else config.get("step_temperatures", {}).get("generation", 0.7)
        )
        self.reflection_temperature = (
            reflection_temperature
            if reflection_temperature is not None
            else config.get("step_temperatures", {}).get("reflection", 0.5)
        )
        self.elo_k_factor = elo_k_factor if elo_k_factor is not None else config.get("elo_k_factor", 32)
        self.top_k_hypotheses = top_k_hypotheses if top_k_hypotheses is not None else config.get("top_k_hypotheses", 2)


class ContextMemory:
    """
    A simple in-memory context storage.
    """

    def __init__(self):
        self.hypotheses: Dict[str, Hypothesis] = {}  # key: hypothesis_id
        self.tournament_results: List[Dict] = []
        self.meta_review_feedback: List[Dict] = []
        self.iteration_number: int = 0

    def add_hypothesis(self, hypothesis: Hypothesis):
        self.hypotheses[hypothesis.hypothesis_id] = hypothesis
        # Consider moving logging out of the model if possible
        # logger.info(f"Added hypothesis {hypothesis.hypothesis_id}")

    def get_active_hypotheses(self) -> List[Hypothesis]:
        return [h for h in self.hypotheses.values() if h.is_active]


###############################################################################
# Pydantic Schemas for API
###############################################################################


class ResearchGoalRequest(BaseModel):
    description: str
    constraints: Optional[Dict] = {}
    # Add optional fields for advanced settings
    llm_model: Optional[str] = None
    num_hypotheses: Optional[int] = None
    generation_temperature: Optional[float] = None
    reflection_temperature: Optional[float] = None
    elo_k_factor: Optional[int] = None
    top_k_hypotheses: Optional[int] = None


class HypothesisResponse(BaseModel):
    id: str
    title: str
    text: str
    novelty_review: Optional[str]
    feasibility_review: Optional[str]
    elo_score: float
    review_comments: List[str]
    references: List[str]
    is_active: bool
    # parent_ids: List[str] # Add if needed in API response


class OverviewResponse(BaseModel):
    iteration: int
    meta_review_critique: List[str]
    top_hypotheses: List[HypothesisResponse]
    suggested_next_steps: List[str]


###############################################################################
# ArXiv Search Models
###############################################################################


class ArxivSearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 10
    categories: Optional[List[str]] = None
    sort_by: Optional[str] = "relevance"  # relevance, lastUpdatedDate, submittedDate
    days_back: Optional[int] = None  # For recent papers search


class ArxivPaper(BaseModel):
    arxiv_id: str
    entry_id: str
    title: str
    abstract: str
    authors: List[str]
    primary_category: str
    categories: List[str]
    published: Optional[str]
    updated: Optional[str]
    doi: Optional[str]
    pdf_url: str
    arxiv_url: str
    comment: Optional[str]
    journal_ref: Optional[str]
    source: str = "arxiv"


class ArxivSearchResponse(BaseModel):
    query: str
    total_results: int
    papers: List[ArxivPaper]
    search_time_ms: Optional[float]


class ArxivTrendsResponse(BaseModel):
    query: str
    total_papers: int
    date_range: str
    top_categories: List[tuple]
    top_authors: List[tuple]
    papers: List[ArxivPaper]
