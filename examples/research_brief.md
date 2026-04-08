---
type: research_brief
feature: ecommerce-analytics-dashboard
version: 1.0
date: 2026-04-08
status: draft
---

# Research Brief: Self-Service Analytics Dashboard for E-Commerce Merchants

## Problem statement

Mid-market e-commerce merchants (50-500 employees) currently receive static weekly PDF reports of conversion funnel data. The reports arrive on Mondays, are 6 days stale by the end of the week, and require a follow-up email to the support team to answer any clarifying question. Support ticket volume for "reporting questions" is 200/month and growing 8% quarter over quarter.

## Market sizing

| Segment | Estimated size | Source |
|---|---|---|
| US mid-market e-commerce merchants on Shopify | ~48,000 | Shopify 2025 annual report, p. 14 |
| US mid-market e-commerce merchants on WooCommerce | ~31,000 | BuiltWith Q1 2026 platform share data |
| Total addressable | ~79,000 | Sum of above |
| Currently on competing analytics tools | ~22,000 (28%) | Triple Whale + Glew customer disclosures |

## Competitive landscape

Three direct competitors offer self-service analytics dashboards in this segment.

| Competitor | Pricing | Notable strength | Notable weakness |
|---|---|---|---|
| Triple Whale | $129-$999/mo | Pixel-based attribution | Overwhelming UI for non-technical merchants |
| Glew | $79-$499/mo | Pre-built reports | Slow data refresh (24h) |
| Polar Analytics | $300+/mo | White-glove onboarding | Price out of reach for smaller merchants |

Two adjacent competitors (Lifetimely, Peel) offer LTV-only dashboards and could expand.

## Customer evidence

Direct quotes from internal interviews (n=12, March 2026) and public G2 reviews (n=47).

> "I get the PDF on Monday and by Wednesday I'm emailing support to ask if Tuesday's spike was real or a tracking glitch. I just want to look it up myself."
> — Operations lead, mid-market apparel merchant, internal interview

> "Triple Whale has everything but I need a data analyst to interpret it. I am the data analyst now and I have other things to do."
> — Founder, mid-market home goods merchant, G2 review (4 stars)

> "We pay $499/month for Glew and use maybe 10% of it. The dashboards are pretty but I can't drill into a specific SKU's funnel."
> — Marketing director, mid-market beauty merchant, internal interview

73% of interviewed merchants said "real-time funnel visibility" was either their #1 or #2 unmet need (n=12).

## Demand signals

- Search volume for "Shopify conversion funnel dashboard" up 34% YoY (Google Trends, March 2025 to March 2026).
- 14 inbound prospect calls in Q1 2026 specifically asked about real-time reporting before mentioning any other feature.
- Support ticket category "reporting questions" grew from 154/month (Q1 2025) to 200/month (Q1 2026).

## Constraints and dependencies

- Must integrate with Shopify Admin API and WooCommerce REST API. Both are stable and well-documented.
- Data must remain in our AWS environment (SOC 2 Type II requirement).
- No third-party BI vendor is acceptable per legal review (March 2026, ticket LEG-1147).

## Gaps and open questions

1. We do not have data on what happens to merchants who churn. Are they switching to competitors, going DIY, or giving up on analytics entirely?
2. We have not validated willingness to pay. The interviews asked about features, not price.
3. The 73% "top unmet need" figure comes from a small sample (n=12). A larger survey would tighten the confidence interval.
4. We have not talked to any merchants on platforms other than Shopify and WooCommerce. BigCommerce represents ~9% of the segment and is unrepresented in our research.

## Sources

1. Shopify Inc., 2025 Annual Report, March 2026.
2. BuiltWith.com, E-commerce Platform Share Q1 2026.
3. Internal customer interviews, March 2026, 12 participants.
4. G2 reviews of Triple Whale, Glew, and Polar Analytics, accessed April 2026.
5. Google Trends, query "Shopify conversion funnel dashboard," 12-month window.
6. Internal support ticket database, category "reporting," Q1 2025 - Q1 2026.
7. Legal review LEG-1147, March 2026.
