---
inclusion: always
name: tech-stack
description: Technology stack and AWS-first conventions
---

# Technology Stack

## Runtime
- Python 3.11+, CrewAI framework, uv package manager
- Anthropic Claude (Sonnet) as the LLM backbone

## AWS-First Defaults
All technical references default to AWS services:
- Compute: Lambda, ECS, EC2
- Database: DynamoDB, Aurora, RDS
- Auth: Cognito
- API: API Gateway
- Storage: S3
- CDN: CloudFront
- Messaging: SNS, SQS, EventBridge
- AI/ML: Bedrock

Do NOT reference Supabase, Firebase, Vercel, or other non-enterprise services unless the PM's constraints explicitly specify them.

## External Services
- Tavily Search API (market research)
- Dovetail MCP (UX research, optional)
- Obsidian vault (internal docs, optional)
