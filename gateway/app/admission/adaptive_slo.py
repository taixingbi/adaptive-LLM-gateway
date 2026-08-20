from app.admission.base import Decision, RequestContext
from app.admission.slo_aware import SloAwarePolicy


class AdaptiveSloAwarePolicy:
    """Same band logic as slo-aware, but pressure uses adaptive C_hat.

    The adaptive budget is injected into RequestContext.platform_tpm_budget by
    the gateway before decide(). This policy only tags reasons distinctly.
    """

    name = "adaptive-slo"

    def __init__(self) -> None:
        self._inner = SloAwarePolicy()

    def decide(self, ctx: RequestContext) -> Decision:
        decision = self._inner.decide(ctx)
        if decision.reason.startswith("slo-"):
            return Decision(action=decision.action, reason="adaptive-" + decision.reason[len("slo-") :])
        return Decision(action=decision.action, reason="adaptive-" + decision.reason)
