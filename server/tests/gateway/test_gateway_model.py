import pytest
from app.model.gateway import BulkUpdateGatewayParams
from pydantic import ValidationError


def test_bulk_update_gateway_params_reject_invalid_targets() -> None:
    with pytest.raises(ValidationError, match='at least 1 item'):
        BulkUpdateGatewayParams(enabled=True, gateways=[])

    duplicate = {'id': 'gateway-1', 'expected_version': 1}
    with pytest.raises(ValidationError, match='cannot contain duplicates'):
        BulkUpdateGatewayParams.model_validate({'enabled': False, 'gateways': [duplicate, duplicate]})

    gateways = [{'id': f'gateway-{index}', 'expected_version': 1} for index in range(51)]
    with pytest.raises(ValidationError, match='at most 50 items'):
        BulkUpdateGatewayParams.model_validate({'enabled': True, 'gateways': gateways})
