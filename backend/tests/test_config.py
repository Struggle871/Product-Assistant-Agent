import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("dimensions", ["1024", "1536", 1024, 1536])
def test_dimensions_accept_environment_strings(dimensions: str | int) -> None:
    settings = Settings.model_validate({"embedding_dimensions": dimensions})
    assert settings.embedding_dimensions == int(dimensions)


def test_unsupported_dimensions_fail_before_database_use() -> None:
    with pytest.raises(ValidationError, match="1024 or 1536"):
        Settings.model_validate({"embedding_dimensions": "768"})
