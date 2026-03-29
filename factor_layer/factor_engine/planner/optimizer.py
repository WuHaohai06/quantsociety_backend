from .logical_plan import PlanNode


class Optimizer:
    def optimize(self, plan: PlanNode) -> PlanNode:
        return plan
