---
pr: pending
branch: feat/165-ai-policy-slice
---
Part of #165: filter restricted app catalog entries from MCP list/get tools and catalog resources before serialization. Health and wellness entries default to display-only while remaining visible to the owner. Explicit policies fail closed unless allowed; legacy non-health catalog metadata remains visible. Manifest schema support, provider-data/model enforcement, consent/local routing and app-detail UI remain unfinished under #165.
