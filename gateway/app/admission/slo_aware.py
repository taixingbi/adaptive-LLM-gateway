from app.admission.base import Decision, RequestContext


class SloAwarePolicy:
    """Paper policy: slack-aware admission under a platform TPM budget.

    First version matches the staged algorithm in the experiment plan:
    over-quota tenants wait; low pressure admits; P1 and tight-SLO waiters
    go first; everyone else queues.
    """

    name = "slo-aware"

    def decide(self, ctx: RequestContext) -> Decision:
        tenant_next = ctx.tenant_tpm_used + ctx.estimated_tokens
        if tenant_next > ctx.tenant_tpm_limit:
            return Decision(action="QUEUE", reason="tenant-over-quota")
        if ctx.tenant_concurrency >= ctx.tenant_max_concurrency:
            return Decision(action="QUEUE", reason="tenant-concurrency")

        pressure = ctx.platform_pressure
        if pressure < 0.8:
            return Decision(action="ADMIT", reason="slo-low-pressure")
        if ctx.tier == "P1":
            return Decision(action="ADMIT", reason="slo-p1")
        if ctx.remaining_slack_ms < 200:
            return Decision(action="ADMIT", reason="slo-tight-slack")
        if pressure >= 1.0 and ctx.tier == "P3":
            return Decision(action="REJECT", reason="slo-shed-batch")
        return Decision(action="QUEUE", reason="slo-queue")
