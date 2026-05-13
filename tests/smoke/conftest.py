import pydantic_ai.models as _pai_models

# Re-enable real model requests for smoke tests
_pai_models.ALLOW_MODEL_REQUESTS = True
