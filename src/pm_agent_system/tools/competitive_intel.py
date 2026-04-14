"""Competitive intelligence tool for Agent 1.

Constructs targeted Tavily queries against G2, Capterra, and TrustRadius
to return structured review data: ratings, feature comparisons, user
complaints, and pricing tiers. Reuses the existing TAVILY_API_KEY.

Uses search_depth="advanced" for fuller content from review platforms.
Runs separate pros and cons queries per platform (6 queries total) to
produce distinct positive and negative themes.
"""

import logging
import os
import re

from crewai.tools import BaseTool
from tavily import TavilyClient

logger = logging.getLogger(__name__)

PROS_INDICATORS = [
    "like", "love", "great", "excellent", "best", "strong", "easy",
    "helpful", "intuitive", "reliable", "fast", "useful", "simple",
    "flexible", "efficient", "impressed", "recommend", "favorite",
    "pros:", "advantages:", "likes:", "what users like", "positives:",
]

CONS_INDICATORS = [
    "dislike", "hate", "worst", "slow", "confusing", "lacking", "missing",
    "difficult", "expensive", "frustrating", "clunky", "buggy", "limited",
    "poor", "annoying", "complicated", "unintuitive", "steep learning",
    "cons:", "disadvantages:", "dislikes:", "complaint", "issue", "problem",
    "limitation", "downside", "drawback", "negative", "wish",
]


def _extract_rating(text: str, platform: str) -> tuple[str, str]:
    """Extract rating and review count from a search snippet.

    Returns (rating, review_count) or ("", "") if not found.
    """
    rating = ""
    review_count = ""

    # Patterns like "4.7/5", "4.7 out of 5", "4.7 stars"
    rating_match = re.search(r"(\d\.\d)\s*(?:/\s*5|out of 5|stars)", text, re.IGNORECASE)
    if rating_match:
        rating = f"{rating_match.group(1)}/5"

    # Patterns like "5,200 reviews", "based on 2847 reviews", "(2,100+ reviews)"
    count_match = re.search(r"([\d,]+\+?)\s*reviews?", text, re.IGNORECASE)
    if count_match:
        review_count = f"{count_match.group(1)} reviews"

    return rating, review_count


def _word_overlap(a: str, b: str) -> float:
    """Calculate word overlap ratio between two strings (0.0 to 1.0)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def _deduplicate_themes(themes: list[str]) -> list[str]:
    """Remove near-duplicate themes, keeping the longer version."""
    result: list[str] = []
    for theme in themes:
        is_dup = False
        for i, existing in enumerate(result):
            if _word_overlap(theme, existing) > 0.6:
                # Keep the longer one.
                if len(theme) > len(existing):
                    result[i] = theme
                is_dup = True
                break
        if not is_dup:
            result.append(theme)
    return result


def _extract_themes(snippets: list[str], sentiment: str) -> list[str]:
    """Extract themes from snippets, filtered by sentiment.

    Args:
        snippets: Raw text snippets from Tavily results.
        sentiment: "pros" or "cons" — used to filter by keyword indicators.
    """
    indicators = PROS_INDICATORS if sentiment == "pros" else CONS_INDICATORS
    candidates: list[str] = []
    seen_lower: set[str] = set()

    for snippet in snippets:
        for line in snippet.split("\n"):
            line = line.strip(" -•*")
            if not line or len(line) < 10 or len(line) > 200:
                continue

            # Score by how many indicator words appear in the line.
            line_lower = line.lower()
            score = sum(1 for ind in indicators if ind in line_lower)

            # Accept lines with at least one indicator match.
            if score > 0:
                key = line_lower[:60]
                if key not in seen_lower:
                    seen_lower.add(key)
                    candidates.append(line)

    # If keyword filtering returned too few results, fall back to
    # returning lines from the sentiment-specific snippets unfiltered
    # (the query separation from Part A already biases these snippets).
    if len(candidates) < 2:
        for snippet in snippets:
            for line in snippet.split("\n"):
                line = line.strip(" -•*")
                if not line or len(line) < 10 or len(line) > 200:
                    continue
                key = line.lower()[:60]
                if key not in seen_lower:
                    seen_lower.add(key)
                    candidates.append(line)

    # Deduplicate near-identical themes and return top 5.
    return _deduplicate_themes(candidates)[:5]


def _extract_pricing(snippets: list[str]) -> str:
    """Extract pricing info from snippets."""
    for snippet in snippets:
        # Look for pricing patterns
        pricing_match = re.search(
            r"(?:starts?\s+at|from|pricing|plans?\s+(?:start|begin))"
            r"[^.]*?\$[\d,.]+[^.]*",
            snippet,
            re.IGNORECASE,
        )
        if pricing_match:
            return pricing_match.group(0).strip()

        # Free tier mentions
        free_match = re.search(r"free\s+(?:plan|tier|version|trial)[^.]*", snippet, re.IGNORECASE)
        if free_match:
            return free_match.group(0).strip()

    return ""


def _extract_roles(snippets: list[str]) -> list[str]:
    """Extract common reviewer roles from snippets."""
    role_patterns = [
        r"(?:product|project|program|engineering|marketing|sales|it|hr)\s+manager",
        r"(?:software|senior|lead|staff)\s+engineer",
        r"(?:cto|cio|vp|director|head)\s+(?:of\s+)?(?:\w+)?",
        r"(?:data|business|ux|product)\s+(?:scientist|analyst|researcher|designer)",
        r"(?:devops|sre|platform)\s+engineer",
    ]
    roles: list[str] = []
    seen: set[str] = set()

    for snippet in snippets:
        for pattern in role_patterns:
            matches = re.findall(pattern, snippet, re.IGNORECASE)
            for match in matches:
                title = match.strip().title()
                if title.lower() not in seen:
                    seen.add(title.lower())
                    roles.append(title)

    return roles[:5]


class CompetitiveIntelTool(BaseTool):
    name: str = "competitive_intelligence"
    description: str = (
        "Searches G2, Capterra, and TrustRadius for structured review data "
        "on a competitor product. Returns: overall rating, review count, "
        "top pros, top cons, common reviewer roles, and pricing tier if "
        "available. Use this to enrich competitor analysis with real user "
        "feedback. Input: competitor product name (e.g., 'Notion', 'Jira', "
        "'Asana')."
    )

    def _run(self, product_name: str) -> str:
        """Search review platforms for competitive intelligence on a product.

        Args:
            product_name: The competitor product to research
                (e.g., 'Notion', 'Jira', 'Asana').
        """
        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return (
                "TAVILY_API_KEY is not set. Cannot search review platforms. "
                "Set TAVILY_API_KEY in your .env file."
            )

        client = TavilyClient(api_key=api_key)

        # Run separate queries for ratings, pros, and cons per platform.
        platforms = ["G2", "Capterra", "TrustRadius"]
        platform_data: dict[str, dict] = {}
        all_snippets: list[str] = []
        pros_snippets: list[str] = []
        cons_snippets: list[str] = []

        for platform in platforms:
            # Query 1: Ratings overview
            rating_query = f"{product_name} {platform} reviews rating"
            # Query 2: What users like (pros)
            pros_query = f"{product_name} {platform} reviews what users like best"
            # Query 3: Complaints and limitations (cons)
            cons_query = f"{product_name} {platform} reviews complaints limitations"

            p_snippets: list[str] = []
            platform_pros: list[str] = []
            platform_cons: list[str] = []
            source_url = ""
            rating = ""
            review_count = ""

            for query, query_type in [
                (rating_query, "rating"),
                (pros_query, "pros"),
                (cons_query, "cons"),
            ]:
                try:
                    response = client.search(
                        query=query,
                        max_results=5,
                        search_depth="advanced",
                    )
                    results = response.get("results", [])
                    snippets = [r.get("content", "") for r in results if r.get("content")]
                    p_snippets.extend(snippets)
                    all_snippets.extend(snippets)

                    if query_type == "pros":
                        platform_pros.extend(snippets)
                        pros_snippets.extend(snippets)
                    elif query_type == "cons":
                        platform_cons.extend(snippets)
                        cons_snippets.extend(snippets)

                    # Extract rating from the rating query.
                    if query_type == "rating":
                        combined_text = " ".join(snippets)
                        r, rc = _extract_rating(combined_text, platform)
                        if r:
                            rating = r
                        if rc:
                            review_count = rc

                    # Find a source URL from any query.
                    if not source_url:
                        for r in results:
                            url = r.get("url", "")
                            if platform.lower() in url.lower():
                                source_url = url
                                break

                except Exception as exc:
                    logger.warning(
                        "Tavily search failed for %s on %s (%s): %s",
                        product_name, platform, query_type, exc,
                    )

            platform_data[platform] = {
                "rating": rating,
                "review_count": review_count,
                "source_url": source_url,
                "snippets": p_snippets,
                "pros_snippets": platform_pros,
                "cons_snippets": platform_cons,
            }

        # Build the summary.
        lines = [f"{product_name} — Competitive Intelligence Summary", ""]

        # Ratings section.
        has_ratings = False
        for platform, data in platform_data.items():
            if data.get("rating"):
                count_str = f" ({data['review_count']})" if data.get("review_count") else ""
                lines.append(f"{platform}: {data['rating']}{count_str}")
                has_ratings = True
            elif data.get("snippets"):
                lines.append(f"{platform}: No rating data found")
            else:
                lines.append(f"{platform}: Search failed")

        if not has_ratings:
            lines.append("")
            lines.append(
                f"Note: Limited review data found for {product_name}. "
                f"This may indicate a niche or newer product with few public reviews. "
                f"Consider supplementing with direct web research."
            )

        # Pros — extracted from pros-specific queries.
        lines.append("")
        pros = _extract_themes(pros_snippets, "pros")
        if pros:
            lines.append("Top Pros (from reviews):")
            for pro in pros:
                lines.append(f"- {pro}")
        else:
            lines.append("Top Pros: No clear themes extracted from available snippets.")

        # Cons — extracted from cons-specific queries.
        lines.append("")
        cons = _extract_themes(cons_snippets, "cons")
        if cons:
            lines.append("Top Cons (from reviews):")
            for con in cons:
                lines.append(f"- {con}")
        else:
            lines.append("Top Cons: No clear themes extracted from available snippets.")

        # Reviewer roles.
        roles = _extract_roles(all_snippets)
        if roles:
            lines.append("")
            lines.append(f"Common Reviewer Roles: {', '.join(roles)}")

        # Pricing.
        pricing = _extract_pricing(all_snippets)
        if pricing:
            lines.append("")
            lines.append(f"Pricing: {pricing}")

        # Source URLs.
        source_urls = [
            (p, d["source_url"]) for p, d in platform_data.items() if d.get("source_url")
        ]
        if source_urls:
            lines.append("")
            lines.append("Sources:")
            for platform, url in source_urls:
                lines.append(f"- {platform}: {url}")

        return "\n".join(lines)
