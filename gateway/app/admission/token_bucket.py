from app.admission.base import Decision, RequestContext


class TokenBucketPolicy:
    """Stronger TPM baseline: refill at tenant/platform quota per minute.

    Unlike the fixed YYYY-MM-DDTHH:MM window, this does not reset to zero
    at the minute boundary. Tokens accrue continuously up to capacity.
    """

    name = "token-bucket"

    def decide(self, ctx: RequestContext) -> Decision:
        if ctx.tenant_bucket_tokens < ctx.estimated_tokens:
            return Decision(action="QUEUE", reason="tenant-bucket-empty")
        if ctx.platform_bucket_tokens < ctx.estimated_tokens:
            return Decision(action="QUEUE", reason="platform-bucket-empty")
        return Decision(action="ADMIT", reason="token-bucket-ok")
