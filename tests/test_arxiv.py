"""Tests for the arXiv integration.

Category-mapping logic is pure and runs offline; everything hitting the live
arXiv API is marked `network` (run with `make test-all`).
"""

import pytest

from app.tools.arxiv_search import ArxivSearchTool, get_categories_for_field

# --- Offline: pure category-mapping logic ---


def test_known_fields_map_to_categories():
    assert len(get_categories_for_field("computer_science")) > 0
    assert len(get_categories_for_field("physics")) > 0


# --- Live arXiv API ---


@pytest.mark.network
def test_basic_search_returns_papers_with_metadata():
    tool = ArxivSearchTool(max_results=5)
    papers = tool.search_papers("machine learning", max_results=3)

    assert len(papers) > 0
    for paper in papers:
        assert paper["title"]
        assert paper["arxiv_id"]
        assert isinstance(paper["authors"], list)
        assert isinstance(paper["categories"], list)


@pytest.mark.network
def test_category_filtered_search():
    tool = ArxivSearchTool(max_results=3)
    papers = tool.search_papers("neural networks", categories=["cs.AI", "cs.LG"])
    assert len(papers) > 0


@pytest.mark.network
def test_recent_papers_search_does_not_error():
    tool = ArxivSearchTool(max_results=3)
    papers = tool.search_recent_papers("transformer", days_back=30)
    assert isinstance(papers, list)  # may legitimately be empty


@pytest.mark.network
def test_specific_paper_retrieval():
    tool = ArxivSearchTool()
    paper = tool.get_paper_details("1706.03762")  # Attention Is All You Need
    assert paper is not None
    assert "attention" in paper["title"].lower()


@pytest.mark.network
def test_trends_analysis_shape():
    tool = ArxivSearchTool()
    trends = tool.analyze_research_trends("quantum computing", days_back=60)
    assert "total_papers" in trends
    assert "top_categories" in trends
    assert "top_authors" in trends
