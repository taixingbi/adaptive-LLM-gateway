from app.admission.base import Decision, RequestContext


class TpmPolicy:
    """Fixed calendar-minute TPM window (YYYY-MM-DDTHH:MM).

    Kept as a weak-but-common baseline. Prefer token-bucket as the
    production-like rate limiter.
    """

    name = "tpm"

    def decide(self, ctx: RequestContext) -> Decision:
        platform_next = ctx.platform_tpm_used + ctx.estimated_tokens
        if ctx.tenant_tpm_exceeded():
            return Decision(action="QUEUE", reason="tenant-tpm-exceeded")
        if platform_next > ctx.platform_tpm_budget:
            return Decision(action="QUEUE", reason="platform-tpm-exceeded")
        return Decision(action="ADMIT", reason="tpm-ok")
