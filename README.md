# Ontara

Report a local problem, approve the recipient and facts, and follow verified reporting
progress through interruptions and requests for information.

Built for Agents in Context Toronto, Track 3 — Finish the Job. This original hackathon
implementation uses two clearly labelled controlled municipal demo portals. It does
not establish live province-wide integrations or claim that an acknowledged report
has repaired an issue.

- `apps/web`: React 19+, Next.js and Astryx resident interface.
- `services/api`: FastAPI case ledger, approvals, durable jobs and Atlas evidence.
- `services/portals`: independent receiving systems for the controlled demonstration.
- `services/agent` and `services/executor`: bounded LangGraph and Playwright execution.
- `contracts`: generated catalogue, questions, API and research import schemas.
- `data/municipal`: source-backed Roads knowledge and coverage evidence.

See each service's README for setup. Secrets are supplied privately or through hosting
environment variables and must never be committed. Case access is browser-session
scoped. Native Atlas Automated Embedding and scoped Vector Search cover public
published procedures and verified lessons; private case records remain exact state.

Demo and submission links will be added after deployment and verification.
