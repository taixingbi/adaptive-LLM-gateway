from app.admission.base import Decision, RequestContext


class SloAwarePolicy:
    """Paper controller: slack-aware admission with a hard safety ceiling.

    Slack = TTFT_SLO - waiting_time - estimated_backend_TTFT

    Capacity bands (platform_tpm_used / platform_tpm_budget):
      < 0.8       freely admit (after tenant quota / concurrency checks)
      0.8–1.0     SLO / priority-aware
      1.0–1.1     only reserved share (weight / weight_sum * C)
      >= 1.1      hard shed
    """

    name = "slo-aware"
    soft_pressure = 0.8
    capacity_pressure = 1.0
    hard_shed_pressure = 1.1
    slack_threshold_ms = 200.0

    def decide(self, ctx: RequestContext) -> Decision:
        if ctx.tenant_tpm_exceeded():
            return Decision(action="QUEUE", reason="tenant-over-quota")
        if ctx.tenant_concurrency >= ctx.tenant_max_concurrency:
            return Decision(action="QUEUE", reason="tenant-concurrency")

        pressure = ctx.platform_pressure
        if pressure >= self.hard_shed_pressure:
            return Decision(action="REJECT", reason="slo-hard-shed")
        if pressure >= self.capacity_pressure:
            if ctx.tenant_tpm_used < ctx.reserved_tpm:
                return Decision(action="ADMIT", reason="slo-reserved")
            return Decision(action="QUEUE", reason="slo-over-capacity")
        if pressure < self.soft_pressure:
            return Decision(action="ADMIT", reason="slo-low-pressure")
        if ctx.tier == "P1":
            return Decision(action="ADMIT", reason="slo-p1")
        if ctx.remaining_slack_ms < self.slack_threshold_ms:
            return Decision(action="ADMIT", reason="slo-tight-slack")
        return Decision(action="QUEUE", reason="slo-queue")
