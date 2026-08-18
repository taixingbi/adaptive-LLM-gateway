from app.admission.base import Decision, RequestContext


class TpmPolicy:
    name = "tpm"

    def decide(self, ctx: RequestContext) -> Decision:
        tenant_next = ctx.tenant_tpm_used + ctx.estimated_tokens
        platform_next = ctx.platform_tpm_used + ctx.estimated_tokens
        if tenant_next > ctx.tenant_tpm_limit:
            return Decision(action="QUEUE", reason="tenant-tpm-exceeded")
        if platform_next > ctx.platform_tpm_budget:
            return Decision(action="QUEUE", reason="platform-tpm-exceeded")
        return Decision(action="ADMIT", reason="tpm-ok")
