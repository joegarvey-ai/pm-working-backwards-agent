"""Competitive intelligence tool for Agent 1.

Constructs targeted Tavily queries against G2, Capterra, and TrustRadius
to return structured review data: ratings, feature comparisons, user
complaints, and pricing tiers. Reuses the existing TAVILY_API_KEY.
"""

import logging
import os
import re

from crewai.tools import BaseTool
from tavily import TavilyClient

logger = logging.getLogger(__name__)


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


def _extract_themes(snippets: list[str], label: str) -> list[str]:
    """Extract recurring themes (pros or cons) from review snippets."""
    themes: list[str] = []
    seen_lower: set[str] = set()

    for snippet in snippets:
        # Look for bullet-style items or sentence fragments after "pros:" / "cons:"
        for line in snippet.split("\n"):
            line = line.strip(" -•*")
            if not line or len(line) < 10 or len(line) > 200:
                continue
            key = line.lower()[:60]
            if key not in seen_lower:
                seen_lower.add(key)
                themes.append(line)

    return themes[:5]


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

        # Run targeted queries for each review platform.
        queries = [
            (f"{product_name} G2 reviews rating", "G2"),
            (f"{product_name} Capterra reviews pros cons", "Capterra"),
            (f"{product_name} TrustRadius reviews", "TrustRadius"),
        ]

        platform_data: dict[str, dict] = {}
        all_snippets: list[str] = []

        for query, platform in queries:
            try:
                response = client.search(
                    query=query,
                    max_results=5,
                    search_depth="basic",
                )
                results = response.get("results", [])
                snippets = [r.get("content", "") for r in results if r.get("content")]
                all_snippets.extend(snippets)

                combined_text = " ".join(snippets)
                rating, review_count = _extract_rating(combined_text, platform)

                source_url = ""
                for r in results:
                    url = r.get("url", "")
                    if platform.lower() in url.lower():
                        source_url = url
                        break

                platform_data[platform] = {
                    "rating": rating,
                    "review_count": review_count,
                    "source_url": source_url,
                    "snippets": snippets,
                }
            except Exception as exc:
                logger.warning("Tavily search failed for %s on %s: %s", product_name, platform, exc)
                platform_data[platform] = {
                    "rating": "",
                    "review_count": "",
                    "source_url": "",
                    "snippets": [],
                    "error": str(exc),
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
            elif not data.get("error"):
                lines.append(f"{platform}: No rating data found")
            else:
                lines.append(f"{platform}: Search failed — {data['error']}")

        if not has_ratings:
            lines.append("")
            lines.append(
                f"Note: Limited review data found for {product_name}. "
                f"This may indicate a niche or newer product with few public reviews. "
                f"Consider supplementing with direct web research."
            )

        # Pros and cons.
        lines.append("")
        pros = _extract_themes(all_snippets, "pros")
        if pros:
            lines.append("Top Pros (from reviews):")
            for pro in pros:
                lines.append(f"- {pro}")
        else:
            lines.append("Top Pros: No clear themes extracted from available snippets.")

        lines.append("")
        cons = _extract_themes(all_snippets, "cons")
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
