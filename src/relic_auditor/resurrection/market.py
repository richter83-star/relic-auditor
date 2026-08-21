from __future__ import annotations

import re

from .schemas import MarketContext, SubstantiveSubgraph


class MarketIntelligenceProvider:
    """
    Provides bounded market context for a salvageable substantive subgraph.

    Current v1.0 behavior is intentionally offline-only. The provider maps a
    deterministic code subgraph to a coarse market category and returns a
    static benchmark set. It does not perform live web research, validate
    current competitor status, or verify current pricing.

    EPISTEMIC INVARIANT:
    All output is labeled ``external_market_speculation``. Commercial context
    must never be confused with deterministic AST proof.
    """

    def __init__(self, offline: bool = True, timeout_seconds: float = 10.0):
        self.offline = offline
        self.timeout_seconds = timeout_seconds

    def fetch_market_context(
        self,
        subgraph: SubstantiveSubgraph,
        product_archetype: str = "Developer Tool / Automation Engine",
    ) -> MarketContext:
        category = self._infer_market_category(subgraph, product_archetype)

        # v1.0 has no live research adapter. Even when a caller requests an
        # online-capable mode, fail closed to explicitly labeled offline
        # heuristics instead of implying that current market facts were fetched.
        return self._offline_market_context(category)

    def _infer_market_category(self, subgraph: SubstantiveSubgraph, archetype: str) -> str:
        names = " ".join(s["name"] for s in subgraph.nodes)
        paths = " ".join(subgraph.substantive_paths)
        combined = (names + " " + paths + " " + archetype).lower()

        if re.search(r"security|vulnerability|audit|ast|static|cve|scanner", combined):
            return "Static Application Security Testing (SAST) & Code Audit"
        if re.search(r"billing|stripe|invoice|subscription|payment", combined):
            return "Developer Billing & Usage Metering Infrastructure"
        if re.search(r"queue|worker|job|pipeline|orchestrat|task", combined):
            return "Asynchronous Job & Workflow Automation"
        if re.search(r"data|persist|database|model|schema|prisma", combined):
            return "Database Modeling & Data Layer Tooling"
        if re.search(r"report|export|pdf|dashboard", combined):
            return "Automated Reporting & Compliance Document Generation"
        return "Developer Workflow & Automation Utilities"

    def _offline_market_context(self, category: str) -> MarketContext:
        benchmarks = {
            "Static Application Security Testing (SAST) & Code Audit": {
                "competitors": [
                    {"name": "Semgrep", "model": "Open-core CLI + Paid Enterprise Rules"},
                    {"name": "Snyk Code", "model": "Free Tier + Per-Developer SaaS Subscription"},
                    {"name": "SonarQube", "model": "Self-hosted Community + Commercial Server"},
                ],
                "pricing": ["Historical heuristic: $0 local tooling to roughly $30-$50/dev/month for team cloud features"],
                "demand_signals": ["Heuristic: teams value fast, low-noise static analysis in CI/CD workflows"],
                "risks": ["Crowded incumbent market; accuracy and workflow differentiation would need current validation"],
            },
            "Developer Billing & Usage Metering Infrastructure": {
                "competitors": [
                    {"name": "Stripe Billing", "model": "Usage/volume-based commercial billing platform"},
                    {"name": "Lago", "model": "Open-source metering + Paid Cloud"},
                    {"name": "Togai", "model": "Usage-based event metering SaaS"},
                ],
                "pricing": ["Historical heuristic: volume-based fees or paid monthly usage tiers"],
                "demand_signals": ["Heuristic: usage-based pricing remains relevant to AI and infrastructure products"],
                "risks": ["High reliability, accounting, and compliance requirements; current market facts require validation"],
            },
            "Asynchronous Job & Workflow Automation": {
                "competitors": [
                    {"name": "Temporal", "model": "Open-source core + Managed Cloud"},
                    {"name": "Inngest", "model": "Event-driven workflow execution SaaS"},
                    {"name": "Trigger.dev", "model": "Developer-first background jobs"},
                ],
                "pricing": ["Historical heuristic: free developer tiers plus usage-based paid plans"],
                "demand_signals": ["Heuristic: durable execution and code-first workflows are established product patterns"],
                "risks": ["Infrastructure complexity and state persistence management"],
            },
        }

        default_data = {
            "competitors": [
                {"name": "Standard Open Source Libraries", "model": "Free / Self-supported"},
                {"name": "Vertical SaaS Tools", "model": "Subscription"},
            ],
            "pricing": ["Historical heuristic: freemium tooling with paid individual or team tiers"],
            "demand_signals": ["Heuristic: developers often prefer lightweight, non-intrusive tooling"],
            "risks": ["Willingness to pay is unknown until the specific workflow and buyer are validated"],
        }

        entry = benchmarks.get(category, default_data)
        return MarketContext(
            status="offline_heuristic",
            target_category=category,
            active_competitors=entry["competitors"],
            pricing_benchmarks=entry["pricing"],
            demand_signals=entry["demand_signals"],
            market_risks=entry["risks"],
            sources=["Bundled static benchmark heuristics; not live market research"],
            epistemic_rating="external_market_speculation",
        )
