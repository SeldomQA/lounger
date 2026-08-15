from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from lounger.log import log


@dataclass
class BaseModel:
    """Base model for all test cases"""
    name: str = ""
    step: Optional[str] = None
    prescript: Optional[str] = None
    extract: Optional[Dict[str, Any]] = None
    validate: Optional[Dict[str, Any]] = None
    sleep: Optional[int] = None

    def __post_init__(self):
        if not self.name and not self.step:
            raise ValueError("Either 'name' or 'step' is required.")


@dataclass
class RequestModel(BaseModel):
    """Data model for HTTP-like test cases"""
    request: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        if not self.request:
            raise ValueError("RequestModel.request is required.")


@dataclass
class CentrifugeModel(BaseModel):
    """Data model for websocket test cases"""
    centrifuge: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        if not self.centrifuge:
            raise ValueError("CentrifugeModel.centrifuge is required.")


def verify_model(case_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that case information matches the Model structure

    :param case_info: Case information to verify
    :return: Verified case information
    :raises Exception: If case information doesn't match the Model structure
    """
    try:
        if case_info.get("centrifuge"):
            CentrifugeModel(**case_info)
        elif case_info.get("request"):
            RequestModel(**case_info)
        else:
            raise TypeError("Currently, only Centrifuge and HTTP (request) protocols are supported.")
        return case_info
    except Exception as e:
        log.error(f"Data model verification failed: {e}")
        raise
