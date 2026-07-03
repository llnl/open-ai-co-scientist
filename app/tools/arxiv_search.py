import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import arxiv

logger = logging.getLogger(__name__)


class ArxivSearchTool:
    """Tool for searching and retrieving papers from arXiv"""

    def __init__(self, max_results: int = 10):
        self.max_results = max_results
        self.client = arxiv.Client()

    def search_papers(
        self,
        query: str,
        max_results: Optional[int] = None,
        categories: Optional[List[str]] = None,
        sort_by: str = "relevance",
    ) -> List[Dict]:
        """
        Search arXiv for papers matching query

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            categories: List of arXiv categories to filter by (e.g., ['cs.AI', 'cs.LG'])
            sort_by: Sort criteria ('relevance', 'lastUpdatedDate', 'submittedDate')

        Returns:
            List of paper dictionaries with metadata
        """
        if max_results is None:
            max_results = self.max_results

        # Build search query with category filter if provided
        search_query = query
        if categories:
            category_filter = " OR ".join([f"cat:{cat}" for cat in categories])
            search_query = f"({query}) AND ({category_filter})"

        # Set sort criteria
        sort_criterion = arxiv.SortCriterion.Relevance
        if sort_by == "lastUpdatedDate":
            sort_criterion = arxiv.SortCriterion.LastUpdatedDate
        elif sort_by == "submittedDate":
            sort_criterion = arxiv.SortCriterion.SubmittedDate

        # Log search parameters
        logger.info(
            f"ArXiv search initiated - Query: '{query}', Max Results: {max_results}, "
            f"Categories: {categories}, Sort: {sort_by}"
        )
        if search_query != query:
            logger.debug(f"Expanded search query: '{search_query}'")

        try:
            import time

            start_time = time.time()

            search = arxiv.Search(
                query=search_query,
                max_results=max_results,
                sort_by=sort_criterion,
                sort_order=arxiv.SortOrder.Descending,
            )

            papers = []
            for paper in self.client.results(search):
                papers.append(self._format_paper(paper))

            search_time = (time.time() - start_time) * 1000  # Convert to ms

            # Enhanced logging with performance metrics
            logger.info(
                f"ArXiv search completed - Found {len(papers)} papers for query: '{query}' in {search_time:.2f}ms"
            )

            # Log paper details at debug level
            if papers and logger.isEnabledFor(logging.DEBUG):
                logger.debug("ArXiv papers found:")
                for i, paper in enumerate(papers[:3], 1):  # Log first 3 papers
                    logger.debug(f"  {i}. {paper['title']} ({paper['arxiv_id']}) - Published: {paper['published']}")
                if len(papers) > 3:
                    logger.debug(f"  ... and {len(papers) - 3} more papers")

            # Log categories distribution
            if papers:
                categories_count = {}
                for paper in papers:
                    for cat in paper.get("categories", []):
                        categories_count[cat] = categories_count.get(cat, 0) + 1
                top_categories = sorted(categories_count.items(), key=lambda x: x[1], reverse=True)[:5]
                logger.info(f"ArXiv search result categories: {dict(top_categories)}")

            return papers

        except Exception as e:
            logger.error(f"ArXiv search failed for query '{query}': {e}", exc_info=True)
            return []

    def search_by_author(self, author_name: str, max_results: Optional[int] = None) -> List[Dict]:
        """Search for papers by a specific author"""
        query = f"au:{author_name}"
        return self.search_papers(query, max_results)

    def search_recent_papers(self, query: str, days_back: int = 7, max_results: Optional[int] = None) -> List[Dict]:
        """Search for recent papers within specified time frame"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Format dates for arXiv search
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # Add date filter to query
        date_query = f"({query}) AND submittedDate:[{start_str} TO {end_str}]"
        return self.search_papers(date_query, max_results, sort_by="submittedDate")

    def search_by_category(
        self, category: str, max_results: Optional[int] = None, days_back: Optional[int] = None
    ) -> List[Dict]:
        """Search papers in a specific arXiv category"""
        query = f"cat:{category}"

        if days_back:
            return self.search_recent_papers(query, days_back, max_results)
        else:
            return self.search_papers(query, max_results)

    def get_paper_details(self, arxiv_id: str) -> Optional[Dict]:
        """Get detailed information for a specific paper by arXiv ID"""
        logger.info(f"Fetching arXiv paper details for ID: {arxiv_id}")
        try:
            import time

            start_time = time.time()

            search = arxiv.Search(id_list=[arxiv_id])
            papers = list(self.client.results(search))

            fetch_time = (time.time() - start_time) * 1000

            if papers:
                paper = self._format_paper(papers[0])
                logger.info(f"Successfully retrieved paper '{paper['title']}' ({arxiv_id}) in {fetch_time:.2f}ms")
                return paper
            else:
                logger.warning(f"No paper found with arXiv ID: {arxiv_id}")
                return None

        except Exception as e:
            logger.error(f"Error retrieving paper {arxiv_id}: {e}", exc_info=True)
            return None

    def _format_paper(self, paper: arxiv.Result) -> Dict:
        """Format arXiv paper result into a standardized dictionary"""
        # Extract arXiv ID from entry_id URL
        arxiv_id = paper.get_short_id()

        # Clean and format abstract
        abstract = self._clean_text(paper.summary)

        # Format authors
        authors = [str(author) for author in paper.authors]

        # Extract DOI if available
        doi = None
        if paper.doi:
            doi = paper.doi

        # Format categories
        categories = paper.categories if paper.categories else []

        return {
            "arxiv_id": arxiv_id,
            "entry_id": paper.entry_id,
            "title": self._clean_text(paper.title),
            "abstract": abstract,
            "authors": authors,
            "primary_category": paper.primary_category,
            "categories": categories,
            "published": paper.published.isoformat() if paper.published else None,
            "updated": paper.updated.isoformat() if paper.updated else None,
            "doi": doi,
            "pdf_url": paper.pdf_url,
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
            "comment": paper.comment,
            "journal_ref": paper.journal_ref,
            "source": "arxiv",
        }

    def _clean_text(self, text: str) -> str:
        """Clean text by removing extra whitespace and newlines"""
        if not text:
            return ""
        # Replace multiple whitespace with single space
        cleaned = re.sub(r"\s+", " ", text)
        return cleaned.strip()

    def analyze_research_trends(self, query: str, days_back: int = 30) -> Dict:
        """Analyze research trends for a given topic"""
        logger.info(f"Starting arXiv trends analysis for '{query}' over last {days_back} days")

        papers = self.search_recent_papers(query, days_back, max_results=50)

        if not papers:
            logger.warning(f"No papers found for trends analysis of '{query}' in last {days_back} days")
            return {"total_papers": 0, "categories": {}, "top_authors": {}, "papers": []}

        # Analyze categories
        category_counts = {}
        author_counts = {}

        for paper in papers:
            # Count categories
            for category in paper.get("categories", []):
                category_counts[category] = category_counts.get(category, 0) + 1

            # Count authors
            for author in paper.get("authors", []):
                author_counts[author] = author_counts.get(author, 0) + 1

        # Sort by frequency
        top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Log trends analysis results
        logger.info(
            f"ArXiv trends analysis completed for '{query}': {len(papers)} papers, "
            f"top categories: {dict(top_categories[:3])}"
        )
        if top_authors:
            logger.info(f"Most active authors: {dict(top_authors[:3])}")

        return {
            "total_papers": len(papers),
            "date_range": f"Last {days_back} days",
            "top_categories": top_categories,
            "top_authors": top_authors,
            "papers": papers,
        }


# Common arXiv categories for different fields
ARXIV_CATEGORIES = {
    "computer_science": [
        "cs.AI",  # Artificial Intelligence
        "cs.LG",  # Machine Learning
        "cs.CL",  # Computation and Language
        "cs.CV",  # Computer Vision
        "cs.RO",  # Robotics
        "cs.NE",  # Neural and Evolutionary Computing
    ],
    "physics": [
        "physics.data-an",  # Data Analysis
        "physics.comp-ph",  # Computational Physics
        "cond-mat.stat-mech",  # Statistical Mechanics
    ],
    "mathematics": [
        "math.ST",  # Statistics Theory
        "math.OC",  # Optimization and Control
        "math.PR",  # Probability
    ],
    "quantitative_biology": [
        "q-bio.QM",  # Quantitative Methods
        "q-bio.GN",  # Genomics
        "q-bio.BM",  # Biomolecules
    ],
}


def get_categories_for_field(field: str) -> List[str]:
    """Get relevant arXiv categories for a research field"""
    return ARXIV_CATEGORIES.get(field.lower(), [])
