from app.admission.base import Decision, RequestContext


class NonePolicy:
    name = "none"

    def decide(self, ctx: RequestContext) -> Decision:
        return Decision(action="ADMIT", reason="no-control")
