from app.admission.base import Decision, RequestContext


class PriorityPolicy:
    name = "priority"

    def decide(self, ctx: RequestContext) -> Decision:
        if ctx.tenant_tpm_exceeded():
            return Decision(action="QUEUE", reason="tenant-tpm-exceeded")
        pressure = ctx.platform_pressure
        if pressure < 0.95:
            return Decision(action="ADMIT", reason="priority-low-pressure")
        if ctx.tier == "P1":
            return Decision(action="ADMIT", reason="priority-p1")
        if ctx.tier == "P2":
            return Decision(action="QUEUE", reason="priority-p2-throttled")
        return Decision(action="REJECT", reason="priority-p3-throttled")
