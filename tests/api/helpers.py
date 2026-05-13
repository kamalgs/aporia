from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def make_fake_turn_model(utterance: str = "Good.", on_target: bool = True) -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "utterance": utterance,
            "on_target": on_target,
            "matched_markers": [],
            "affect": {},
            "notes": "",
        })])
    return FunctionModel(_fn)


def make_fake_session_model(goal: str = "warm_up", skill_id: str = "add-1digit") -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "goal": goal,
            "skill_id": skill_id,
            "difficulty_hint": "same",
            "rationale": "test",
            "tone_note": None,
        })])
    return FunctionModel(_fn)


def make_fake_identity_model(portrait: str = "Portrait.") -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "portrait_md": portrait,
        })])
    return FunctionModel(_fn)
