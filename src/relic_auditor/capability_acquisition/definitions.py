from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Signal:
    name: str
    pattern: re.Pattern[str]
    weight: float


@dataclass(frozen=True)
class CapabilityRule:
    key: str
    title: str
    description: str
    signals: tuple[Signal, ...]


def _signal(name: str, pattern: str, weight: float) -> Signal:
    return Signal(name, re.compile(pattern, re.IGNORECASE), weight)


CAPABILITY_RULES: tuple[CapabilityRule, ...] = (
    CapabilityRule(
        "orchestrator",
        "Orchestrator",
        "Coordinates bounded tasks, agents, workflows, or dependency graphs.",
        (
            _signal("named orchestrator", r"\b(?:class|def|function)\s+\w*orchestrat\w*", 0.48),
            _signal("task dispatch", r"\b(?:dispatch|route|schedule)_(?:task|job|agent)\b", 0.30),
            _signal("agent registry", r"\bagent[_ ]registry\b", 0.26),
            _signal("workflow graph", r"\b(?:workflow|task)[_ ](?:graph|dag)\b", 0.24),
            _signal("dependency ordering", r"\btopological(?:ly)?\b|\bdependency[_ ]order\b", 0.18),
        ),
    ),
    CapabilityRule(
        "goal_registry",
        "Goal Registry",
        "Stores explicit goals, objectives, desired state, and goal lifecycle metadata.",
        (
            _signal("named goal registry", r"\bgoal[_ ]registry\b|\bGoalRegistry\b", 0.52),
            _signal("goal lifecycle", r"\b(?:create|register|update|complete|cancel)_goal\b", 0.30),
            _signal("desired state", r"\bdesired[_ ]state\b", 0.20),
            _signal("objective store", r"\b(?:objective|goal)[_ ](?:store|repository)\b", 0.26),
            _signal("goal status", r"\bgoal[_ ]status\b", 0.17),
        ),
    ),
    CapabilityRule(
        "autonomy_loop",
        "Autonomy Loop",
        "Runs a bounded observe-plan-act-evaluate cycle with explicit stop conditions.",
        (
            _signal("named autonomy loop", r"\bautonom(?:y|ous)[_ ]loop\b", 0.50),
            _signal("observe plan act", r"\bobserve\b.{0,80}\bplan\b.{0,80}\bact\b", 0.40),
            _signal("iteration budget", r"\b(?:max[_ ]iterations?|iteration[_ ]budget|step[_ ]limit)\b", 0.27),
            _signal("stop condition", r"\b(?:stop|termination)[_ ]condition\b", 0.25),
            _signal("evaluation cycle", r"\b(?:evaluate|reflect)[_ ](?:result|outcome|step)\b", 0.20),
        ),
    ),
    CapabilityRule(
        "governance_boundary",
        "Governance Boundary",
        "Constrains permissions, scope, policy, and authority before actions occur.",
        (
            _signal("policy engine", r"\bpolicy[_ ]engine\b|\bPolicyEngine\b", 0.42),
            _signal("authority boundary", r"\b(?:authority|governance|permission)[_ ]boundary\b", 0.46),
            _signal("allow deny list", r"\b(?:allow|deny)[_-]?list\b", 0.25),
            _signal("scope check", r"\b(?:check|validate|enforce)_(?:scope|permission|authority)\b", 0.31),
            _signal("least privilege", r"\bleast[_ -]privilege\b", 0.23),
        ),
    ),
    CapabilityRule(
        "approval_queue",
        "Approval Queue",
        "Holds proposed actions until a human or policy authority approves or rejects them.",
        (
            _signal("approval queue", r"\bapproval[_ ]queue\b|\bApprovalQueue\b", 0.52),
            _signal("pending approval", r"\bpending[_ ]approval\b|\brequires[_ ]approval\b", 0.33),
            _signal("approve reject", r"\bapprove\b.{0,80}\breject\b|\breject\b.{0,80}\bapprove\b", 0.28),
            _signal("approval status", r"\bapproval[_ ]status\b", 0.20),
            _signal("human gate", r"\bhuman[_ -](?:gate|approval|review)\b", 0.28),
        ),
    ),
    CapabilityRule(
        "audit_log",
        "Audit Log",
        "Records attributable, tamper-evident or append-only decision and action history.",
        (
            _signal("audit log", r"\baudit[_ ]log\b|\bAuditLog\b", 0.45),
            _signal("append only", r"\bappend[_ -]only\b", 0.28),
            _signal("event ledger", r"\b(?:event|decision|action)[_ ]ledger\b", 0.32),
            _signal("provenance", r"\bprovenance\b|\btrace[_ ]id\b", 0.20),
            _signal("actor action record", r"\bactor\b.{0,80}\baction\b.{0,80}\btimestamp\b", 0.30),
        ),
    ),
    CapabilityRule(
        "self_improvement_proposal",
        "Self-Improvement Proposal",
        "Produces reviewable improvement proposals without directly changing the running system.",
        (
            _signal("improvement proposal", r"\b(?:self[_ -])?improvement[_ ]proposal\b", 0.52),
            _signal("patch proposal", r"\b(?:patch|change|mutation)[_ ]proposal\b", 0.34),
            _signal("champion challenger", r"\bchampion\b.{0,80}\bchallenger\b", 0.30),
            _signal("proposal evaluator", r"\b(?:evaluate|score|review)_(?:proposal|candidate|patch)\b", 0.27),
            _signal("rollback plan", r"\brollback[_ ]plan\b", 0.20),
        ),
    ),
    CapabilityRule(
        "resource_request",
        "Resource Request",
        "Creates bounded requests for budget, quota, compute, storage, or tools; it does not self-provision.",
        (
            _signal("resource request", r"\bresource[_ ]request\b|\bResourceRequest\b", 0.52),
            _signal("request resource", r"\brequest_(?:resource|budget|quota|capacity|compute)\b", 0.34),
            _signal("budget approval", r"\bbudget[_ ]approval\b", 0.27),
            _signal("quota request", r"\b(?:quota|capacity|compute)[_ ]request\b", 0.30),
            _signal("resource limit", r"\b(?:resource|budget|quota)[_ ]limit\b", 0.18),
        ),
    ),
)


CAPABILITY_ORDER = tuple(rule.key for rule in CAPABILITY_RULES)

