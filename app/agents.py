import json
import math
import random
from typing import Dict, List, Tuple

# Import necessary components from other modules
from .models import ContextMemory, Hypothesis, ResearchGoal
from .utils import (
    call_llm,
    generate_unique_id,
    generate_visjs_data,
    logger,  # Use the logger configured in utils
    similarity_score,
)

# --- Agent-Specific LLM Calls (Moved from main.py/utils.py for better cohesion) ---


# Updated signature to accept temperature
def call_llm_for_generation(prompt: str, num_hypotheses: int = 3, temperature: float = 0.7) -> List[Dict]:
    """Calls LLM for generating hypotheses, handling JSON parsing."""
    logger.info(
        "LLM generation called with prompt: %s, num_hypotheses: %d, temperature: %.2f",
        prompt,
        num_hypotheses,
        temperature,
    )
    full_prompt = (
        prompt
        + "\n\nPlease return the response as a JSON array of objects, where each object has a 'title' and 'text' key."
    )

    # Pass the received temperature down to the actual LLM call
    response = call_llm(full_prompt, temperature=temperature)
    logger.info("LLM generation response: %s", response)

    if response.startswith("Error:") or response.startswith("Authentication with OpenRouter failed"):
        logger.error(f"LLM generation call failed: {response}")
        return [{"title": "Error", "text": response}]

    try:
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        hypotheses_data = json.loads(response)

        if not isinstance(hypotheses_data, list) or not all(
            isinstance(h, dict) and "title" in h and "text" in h for h in hypotheses_data
        ):
            error_message = "Invalid JSON format: Expected a list of objects with 'title' and 'text' keys."
            raise ValueError(error_message)
        logger.info("Parsed generated hypotheses: %s", hypotheses_data)
        return hypotheses_data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Could not parse LLM generation response as JSON: %s", response, exc_info=True)
        return [{"title": "Error", "text": f"Could not parse LLM response: {e}"}]


# Updated signature to accept temperature
def call_llm_for_reflection(hypothesis_text: str, temperature: float = 0.5) -> Dict:
    """Calls LLM for reviewing a hypothesis, handling JSON parsing."""
    logger.info("LLM reflection called with temperature: %.2f", temperature)
    prompt = (
        f"Review the following hypothesis and provide a novelty assessment (HIGH, MEDIUM, or LOW), "
        f"a feasibility assessment (HIGH, MEDIUM, or LOW), a comment, and a list of relevant references in JSON format:\n\n"
        f"Hypothesis: {hypothesis_text}\n\n"
        f"For references, provide arXiv IDs (e.g., '2301.12345'), DOIs, or paper titles with venues that are relevant to this hypothesis. "
        f"Do not provide PubMed IDs (PMIDs) unless this is specifically a biomedical/life sciences hypothesis.\n\n"
        f"Return the response as a JSON object with the following keys: 'novelty_review', 'feasibility_review', 'comment', 'references'."
    )
    # Pass the received temperature down to the actual LLM call
    response = call_llm(prompt, temperature=temperature)
    logger.info("LLM reflection response for hypothesis: %s", response)

    if response.startswith("Error:"):
        logger.error(f"LLM reflection call failed: {response}")
        return {
            "novelty_review": "Not reviewed",
            "feasibility_review": "Not reviewed",
            "comment": f"LLM review failed: {response}",
            "references": [],
        }

    # Default values
    review_data = {
        "novelty_review": "MEDIUM",
        "feasibility_review": "MEDIUM",
        "comment": "Could not parse LLM response.",
        "references": [],
    }

    try:
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        parsed_data = json.loads(response)

        # Update defaults with parsed data, performing basic validation
        novelty = parsed_data.get("novelty_review", "MEDIUM").upper()
        if novelty in ["HIGH", "MEDIUM", "LOW"]:
            review_data["novelty_review"] = novelty
        else:
            logger.warning("Invalid novelty review value received: %s", novelty)

        feasibility = parsed_data.get("feasibility_review", "MEDIUM").upper()
        if feasibility in ["HIGH", "MEDIUM", "LOW"]:
            review_data["feasibility_review"] = feasibility
        else:
            logger.warning("Invalid feasibility review value received: %s", feasibility)

        review_data["comment"] = parsed_data.get("comment", "No comment provided.")
        review_data["references"] = parsed_data.get("references", [])
        if not isinstance(review_data["references"], list):
            logger.warning("Invalid references format received: %s", review_data["references"])
            review_data["references"] = []

    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.warning("Error parsing LLM reflection response: %s", response, exc_info=True)
        review_data["comment"] = f"Could not parse LLM response: {e}"  # Update comment with error

    logger.info("Parsed reflection data: %s", review_data)
    return review_data


# --- Ranking Helpers (Moved from main.py) ---


def run_pairwise_debate(hypoA: Hypothesis, hypoB: Hypothesis) -> Hypothesis:
    """Compares two hypotheses based on novelty and feasibility scores."""

    def score(h: Hypothesis) -> int:
        mapping = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, None: 0, "ERROR": 0}  # Handle ERROR case
        score_novelty = mapping.get(h.novelty_review, 0) if isinstance(h.novelty_review, str) else 0
        score_feasibility = mapping.get(h.feasibility_review, 0) if isinstance(h.feasibility_review, str) else 0
        return score_novelty + score_feasibility

    scoreA = score(hypoA)
    scoreB = score(hypoB)

    if scoreA > scoreB:
        winner = hypoA
    elif scoreB > scoreA:
        winner = hypoB
    else:
        winner = random.choice([hypoA, hypoB])  # Tie-breaker

    logger.info(
        "Debate: %s (score %d) vs %s (score %d) => Winner: %s",
        hypoA.hypothesis_id,
        scoreA,
        hypoB.hypothesis_id,
        scoreB,
        winner.hypothesis_id,
    )
    return winner


def update_elo(winner: Hypothesis, loser: Hypothesis, k_factor: int):
    """Updates Elo scores after a comparison, using provided k_factor."""
    # k_factor is now passed as an argument
    ratingA = winner.elo_score
    ratingB = loser.elo_score
    expectedA = 1 / (1 + math.pow(10, (ratingB - ratingA) / 400))
    expectedB = 1 - expectedA  # Or 1 / (1 + math.pow(10, (ratingA - ratingB) / 400))
    winner.elo_score = ratingA + k_factor * (1 - expectedA)
    loser.elo_score = ratingB + k_factor * (0 - expectedB)  # Loser's score update
    logger.info(
        "Updated Elo: Winner %s -> %.2f, Loser %s -> %.2f",
        winner.hypothesis_id,
        winner.elo_score,
        loser.hypothesis_id,
        loser.elo_score,
    )


# --- Evolution Helper (Moved from main.py) ---


def combine_hypotheses(hypoA: Hypothesis, hypoB: Hypothesis) -> Hypothesis:
    """Combines two hypotheses into a new one."""
    new_id = generate_unique_id("E")  # Use utility function
    combined_title = f"Combined: {hypoA.title} & {hypoB.title}"
    # Consider a more sophisticated combination prompt/logic if needed
    combined_text = f"Combination of:\n1. {hypoA.text}\n2. {hypoB.text}"
    logger.info("Combining hypotheses %s and %s into %s", hypoA.hypothesis_id, hypoB.hypothesis_id, new_id)
    new_hypothesis = Hypothesis(new_id, combined_title, combined_text)
    new_hypothesis.parent_ids = [hypoA.hypothesis_id, hypoB.hypothesis_id]
    return new_hypothesis


###############################################################################
# Agent Implementations
###############################################################################


class GenerationAgent:
    def generate_new_hypotheses(
        self, research_goal: ResearchGoal, context: ContextMemory
    ) -> Tuple[List[Hypothesis], List[str]]:
        """Generates new hypotheses using LLM, based on research_goal settings.

        Returns (hypotheses, errors). Error markers are kept out of the
        hypothesis list (they must not be ranked) but their messages are
        returned so the caller can surface the real failure cause instead of
        letting the run silently end with no rankings (see issue llnl#36).
        """
        # Use settings from research_goal object
        num_to_generate = research_goal.num_hypotheses
        gen_temp = research_goal.generation_temperature

        prompt = (
            f"Research Goal: {research_goal.description}\n"
            f"Constraints: {research_goal.constraints}\n"
            f"Existing Hypothesis IDs: {list(context.hypotheses.keys())}\n"  # Provide context
            f"Please propose {num_to_generate} novel and feasible hypotheses with rationale, avoiding duplication with existing IDs.\n"
        )
        # Pass the specific temperature and num_hypotheses
        raw_output = call_llm_for_generation(prompt, num_hypotheses=num_to_generate, temperature=gen_temp)
        new_hypos = []
        errors = []
        for idea in raw_output:
            # An error response carries the real failure cause; collect it
            # (do not add it to the hypothesis list) so the caller can report it.
            if idea["title"] == "Error":
                logger.error("Hypothesis generation failed: %s", idea["text"])
                errors.append(idea["text"])
                continue

            hypo_id = generate_unique_id("G")
            # Ensure ID is unique within the current context
            while hypo_id in context.hypotheses:
                hypo_id = generate_unique_id("G")
            h = Hypothesis(hypo_id, idea["title"], idea["text"])
            logger.info("Generated hypothesis: %s", h.to_dict())
            new_hypos.append(h)
        return new_hypos, errors


class ReflectionAgent:
    def review_hypotheses(
        self, hypotheses: List[Hypothesis], context: ContextMemory, research_goal: ResearchGoal
    ) -> None:
        """Reviews hypotheses using LLM, based on research_goal settings."""
        # Use reflection temperature from research_goal
        reflect_temp = research_goal.reflection_temperature

        for h in hypotheses:
            # Avoid re-reviewing if already reviewed (optional optimization)
            # if h.novelty_review is not None and h.feasibility_review is not None:
            #    continue
            # Pass the specific temperature
            result = call_llm_for_reflection(h.text, temperature=reflect_temp)
            h.novelty_review = result["novelty_review"]
            h.feasibility_review = result["feasibility_review"]
            # Append comment only if it's not the default error message
            if result["comment"] != "Could not parse LLM response.":
                h.review_comments.append(result["comment"])
            # Only extend references if the list is not empty
            if result["references"]:
                h.references.extend(result["references"])
            logger.info(
                "Reviewed hypothesis: %s, Novelty: %s, Feasibility: %s",
                h.hypothesis_id,
                h.novelty_review,
                h.feasibility_review,
            )


class RankingAgent:
    def run_tournament(self, hypotheses: List[Hypothesis], context: ContextMemory, research_goal: ResearchGoal) -> None:
        """Runs a pairwise tournament to rank hypotheses, using research_goal settings."""
        # Use k_factor from research_goal
        k_factor = research_goal.elo_k_factor

        if len(hypotheses) < 2:
            logger.info("Not enough hypotheses to run a tournament.")
            return

        active_hypotheses = [h for h in hypotheses if h.is_active]
        if len(active_hypotheses) < 2:
            logger.info("Not enough *active* hypotheses to run a tournament.")
            return

        random.shuffle(active_hypotheses)  # Shuffle only active ones

        # Simple round-robin: each active hypothesis debates every other active one once
        pairs = []
        for i in range(len(active_hypotheses)):
            for j in range(i + 1, len(active_hypotheses)):
                pairs.append((active_hypotheses[i], active_hypotheses[j]))

        logger.info(f"Running tournament with {len(pairs)} pairs.")
        for hA, hB in pairs:
            winner = run_pairwise_debate(hA, hB)
            loser = hB if winner == hA else hA
            # Pass the specific k_factor
            update_elo(winner, loser, k_factor=k_factor)
            # Record result in context (consider if this needs iteration info)
            context.tournament_results.append(
                {
                    "iteration": context.iteration_number,  # Add iteration number
                    "winner": winner.hypothesis_id,
                    "loser": loser.hypothesis_id,
                    "winner_score_after": winner.elo_score,
                    "loser_score_after": loser.elo_score,
                }
            )


class EvolutionAgent:
    def evolve_hypotheses(self, context: ContextMemory, research_goal: ResearchGoal) -> List[Hypothesis]:
        """Evolves hypotheses by combining top candidates, using research_goal settings."""
        # Use top_k from research_goal
        top_k = research_goal.top_k_hypotheses
        active = context.get_active_hypotheses()
        if len(active) < 2:
            logger.info("Not enough active hypotheses to perform evolution.")
            return []

        sorted_by_elo = sorted(active, key=lambda h: h.elo_score, reverse=True)
        top_candidates = sorted_by_elo[:top_k]

        new_hypotheses = []
        # Combine the top two for now, could be extended
        if len(top_candidates) >= 2:
            # Optional: Add check to prevent combining very similar hypotheses
            # sim = similarity_score(top_candidates[0].text, top_candidates[1].text)
            # if sim < 0.8: # Example threshold
            new_h = combine_hypotheses(top_candidates[0], top_candidates[1])
            logger.info("Evolved hypothesis created: %s from parents %s", new_h.hypothesis_id, new_h.parent_ids)
            new_hypotheses.append(new_h)
            # else:
            #     logger.info("Skipping evolution: Top 2 hypotheses are too similar (score: %.2f)", sim)

        return new_hypotheses


class ProximityAgent:
    def build_proximity_graph(self, context: ContextMemory) -> Dict:
        """Builds proximity graph data based on hypothesis similarity."""
        active_hypotheses = context.get_active_hypotheses()
        adjacency = {}
        if not active_hypotheses:
            logger.info("No active hypotheses to build proximity graph.")
            return {"adjacency_graph": {}, "nodes": [], "edges": []}

        for i in range(len(active_hypotheses)):
            hypo_i = active_hypotheses[i]
            adjacency[hypo_i.hypothesis_id] = []
            for j in range(len(active_hypotheses)):
                if i == j:
                    continue
                hypo_j = active_hypotheses[j]
                if hypo_i.text and hypo_j.text:
                    sim = similarity_score(hypo_i.text, hypo_j.text)
                    adjacency[hypo_i.hypothesis_id].append({"other_id": hypo_j.hypothesis_id, "similarity": sim})
                else:
                    logger.warning(
                        f"Skipping similarity for {hypo_i.hypothesis_id} or {hypo_j.hypothesis_id} due to empty text."
                    )

        visjs_data = generate_visjs_data(adjacency)  # Use utility function
        logger.info("Built proximity graph adjacency with %d nodes.", len(active_hypotheses))
        return {"adjacency_graph": adjacency, "nodes": visjs_data["nodes"], "edges": visjs_data["edges"]}


class MetaReviewAgent:
    def summarize_and_feedback(self, context: ContextMemory, adjacency: Dict) -> Dict:
        """Summarizes research state and provides feedback."""
        active_hypotheses = context.get_active_hypotheses()
        if not active_hypotheses:
            return {
                "meta_review_critique": ["No active hypotheses."],
                "research_overview": {"top_ranked_hypotheses": [], "suggested_next_steps": []},
            }

        comment_summary = set()
        for h in active_hypotheses:
            # Example critique based on reviews
            if h.novelty_review == "LOW":
                comment_summary.add("Some ideas lack novelty.")
            if h.feasibility_review == "LOW":
                comment_summary.add("Some ideas may have low feasibility.")
            # Could add critiques based on adjacency graph (e.g., clusters, outliers)

        best_hypotheses = sorted(active_hypotheses, key=lambda h: h.elo_score, reverse=True)[:3]
        logger.info("Top hypotheses for meta-review: %s", [h.hypothesis_id for h in best_hypotheses])

        # Example suggested next steps
        next_steps = [
            "Refine top hypotheses based on review comments.",
            "Consider exploring areas with fewer, less connected hypotheses (if any).",
            "Seek external expert feedback on top candidates.",
        ]
        if not comment_summary:
            comment_summary.add("Overall hypothesis quality seems reasonable based on automated review.")

        overview = {
            "meta_review_critique": list(comment_summary),
            "research_overview": {
                "top_ranked_hypotheses": [h.to_dict() for h in best_hypotheses],  # Use to_dict for serialization
                "suggested_next_steps": next_steps,
            },
        }
        context.meta_review_feedback.append(overview)  # Store feedback in context
        logger.info("Meta-review complete: %s", overview)
        return overview


class SupervisorAgent:
    """Orchestrates the Open AI Co-Scientist workflow."""

    def __init__(self):
        self.generation_agent = GenerationAgent()
        self.reflection_agent = ReflectionAgent()
        self.ranking_agent = RankingAgent()
        self.evolution_agent = EvolutionAgent()
        self.proximity_agent = ProximityAgent()
        self.meta_review_agent = MetaReviewAgent()

    def run_cycle(self, research_goal: ResearchGoal, context: ContextMemory) -> Dict:
        """Runs a single cycle of hypothesis generation and refinement."""
        logger.info("--- Starting Cycle %d ---", context.iteration_number + 1)
        cycle_details = {"iteration": context.iteration_number + 1, "steps": {}, "meta_review": {}}

        # 1. Generation
        logger.info("Step 1: Generation")
        new_hypotheses, generation_errors = self.generation_agent.generate_new_hypotheses(research_goal, context)
        for nh in new_hypotheses:
            context.add_hypothesis(nh)  # Add to central context
        cycle_details["steps"]["generation"] = {"hypotheses": [h.to_dict() for h in new_hypotheses]}

        # Propagate LLM errors to top-level errors field for frontend display, so a
        # generation failure surfaces its real cause instead of an empty ranking.
        if generation_errors:
            cycle_details["errors"] = generation_errors

        # Get all active hypotheses for subsequent steps
        active_hypos = context.get_active_hypotheses()

        # 2. Reflection
        logger.info("Step 2: Reflection")
        self.reflection_agent.review_hypotheses(active_hypos, context, research_goal)  # Pass research_goal
        cycle_details["steps"]["reflection"] = {"hypotheses": [h.to_dict() for h in active_hypos]}

        # 3. Ranking (Tournament 1)
        logger.info("Step 3: Ranking 1")
        self.ranking_agent.run_tournament(active_hypos, context, research_goal)  # Pass research_goal
        cycle_details["steps"]["ranking1"] = {"hypotheses": [h.to_dict() for h in active_hypos]}

        # 4. Evolution
        logger.info("Step 4: Evolution")
        evolved_hypotheses = self.evolution_agent.evolve_hypotheses(context, research_goal)  # Pass research_goal
        if evolved_hypotheses:
            for eh in evolved_hypotheses:
                context.add_hypothesis(eh)
            logger.info("Step 4a: Reviewing Evolved Hypotheses")
            self.reflection_agent.review_hypotheses(evolved_hypotheses, context, research_goal)  # Pass research_goal
            active_hypos = context.get_active_hypotheses()  # Update active list
            cycle_details["steps"]["evolution"] = {"hypotheses": [h.to_dict() for h in evolved_hypotheses]}
            # Add explicit step for reviewing evolved hypotheses AFTER evolution
            cycle_details["steps"]["reflection_evolved"] = {"hypotheses": [h.to_dict() for h in evolved_hypotheses]}
        else:
            cycle_details["steps"]["evolution"] = {"hypotheses": []}

        # 5. Ranking (Tournament 2 - includes evolved)
        logger.info("Step 5: Ranking 2")
        self.ranking_agent.run_tournament(active_hypos, context, research_goal)  # Pass research_goal
        cycle_details["steps"]["ranking2"] = {"hypotheses": [h.to_dict() for h in active_hypos]}

        # Ensure context.active_hypotheses reflects the final ranked hypotheses for meta-review
        # Use all hypotheses from the final ranking step (not just active_hypos, which may be filtered)
        final_ranked_hypos = [h for h in active_hypos]
        context.active_hypotheses = {h.hypothesis_id: h for h in final_ranked_hypos}

        # 6. Proximity Analysis
        logger.info("Step 6: Proximity Analysis")
        proximity_result = self.proximity_agent.build_proximity_graph(context)  # Pass context
        cycle_details["steps"]["proximity"] = {
            "adjacency_graph": proximity_result["adjacency_graph"],
            "nodes": proximity_result["nodes"],
            "edges": proximity_result["edges"],
        }

        # 7. Meta-review
        logger.info("Step 7: Meta-Review")
        overview = self.meta_review_agent.summarize_and_feedback(context, proximity_result["adjacency_graph"])
        cycle_details["meta_review"] = overview
        # Add meta-review to steps for consistency
        cycle_details["steps"]["meta_review"] = overview

        # Increment iteration number at the end of the cycle
        context.iteration_number += 1
        logger.info("--- Cycle %d Complete ---", context.iteration_number)
        return cycle_details
