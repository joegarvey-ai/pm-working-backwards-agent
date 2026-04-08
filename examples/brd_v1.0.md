---
type: brd
feature: ecommerce-analytics-dashboard
version: 1.0
date: 2026-04-08
status: draft
based_on_prfaq: prfaq_v1.0.md
target_release: Q4 2026
---

# Business Requirements Document: Self-Service Conversion Analytics Dashboard

## 1. Overview

This document defines the functional and non-functional requirements for a self-service conversion analytics dashboard for mid-market e-commerce merchants on Shopify and WooCommerce. It is the engineering-facing companion to the approved PRFAQ.

## 2. Goals and non-goals

### Goals

- Show conversion funnel data (view → cart → checkout → purchase) with a 5-minute refresh.
- Let merchants drill into the funnel by SKU, traffic source, device, and date range.
- Reduce reporting-related support tickets from 200/month to under 80/month within 6 months of launch.
- Reach 70% weekly active adoption among eligible merchants within 90 days.

### Non-goals (v1)

- Paid attribution modeling.
- LTV cohort analysis.
- Email marketing performance.
- Custom report builder.
- BigCommerce support.

## 3. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Display 4-step funnel: product view, add to cart, checkout start, purchase complete | P0 |
| FR-2 | Filter by date range (today, 7d, 30d, 90d, custom) | P0 |
| FR-3 | Filter by SKU (single or multi-select) | P0 |
| FR-4 | Filter by traffic source (organic, paid, direct, referral, email) | P0 |
| FR-5 | Filter by device (desktop, mobile, tablet) | P0 |
| FR-6 | Period-over-period comparison (vs. prior period of same length) | P0 |
| FR-7 | Anomaly highlighting (>20% change vs. prior period) | P1 |
| FR-8 | Export filtered view to CSV | P0 |
| FR-9 | Shareable view URL (read-only, signed, 7-day expiry) | P1 |
| FR-10 | In-app onboarding tour on first open | P1 |

## 4. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Data freshness | ≤ 5 minutes from event to dashboard |
| NFR-2 | P95 page load | ≤ 2 seconds |
| NFR-3 | Concurrent users supported | 5,000 |
| NFR-4 | Data residency | All data stays in our AWS environment (SOC 2) |
| NFR-5 | Browser support | Last 2 versions of Chrome, Safari, Firefox, Edge |
| NFR-6 | Mobile responsive | Functional on screens ≥ 375px wide |
| NFR-7 | Accessibility | WCAG 2.1 AA |

## 5. Dependencies

- Shopify Admin API (orders, products, customers webhooks). Stable, documented.
- WooCommerce REST API v3. Stable, documented.
- Internal event ingestion service (existing). May need throughput upgrade. Engineering to confirm.
- Internal AWS data warehouse (existing). Schema additions required.

## 6. Out of scope for v1

Listed in Section 2 (non-goals). Plus: any analytics for merchants not on Shopify or WooCommerce.

## 7. Open questions

1. Does the existing event ingestion service handle 5-minute refresh at our merchant volume? Needs engineering benchmark before sprint planning.
2. The 50-merchant validation survey (May 2026) may surface additional P0 requirements. Lock requirements only after survey results.
3. Pricing tier eligibility (Growth and Plus only?) is currently a PM assumption. Needs sign-off from the pricing team.
