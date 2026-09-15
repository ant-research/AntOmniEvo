def __getattr__(name):
    if name == "System":
        from antomnievo.interface.system import System
        return System
    if name == "SystemResult":
        from antomnievo.model.system_result import SystemResult
        return SystemResult
    if name == "Evaluator":
        from antomnievo.interface.evaluator import Evaluator
        return Evaluator
    if name == "EvaluationResult":
        from antomnievo.interface.evaluator import EvaluationResult
        return EvaluationResult
    if name == "Proposer":
        from antomnievo.interface.proposer import Proposer
        return Proposer
    if name == "ProposalResult":
        from antomnievo.interface.proposer import ProposalResult
        return ProposalResult
    if name == "EvolutionAlgorithm":
        from antomnievo.interface.evolution_algorithm import EvolutionAlgorithm
        return EvolutionAlgorithm
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EvaluationResult",
    "Evaluator",
    "EvolutionAlgorithm",
    "ProposalResult",
    "Proposer",
    "System",
    "SystemResult",
]
