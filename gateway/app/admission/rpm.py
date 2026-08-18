from app.admission.base import Decision, RequestContext


class RpmPolicy:
    name = "rpm"

    def decide(self, ctx: RequestContext) -> Decision:
        if ctx.tenant_rpm_used >= ctx.tenant_rpm_limit:
            return Decision(action="REJECT", reason="tenant-rpm-exceeded")
        return Decision(action="ADMIT", reason="rpm-ok")
