"""
Experiment management service for CuratorKIT, SafeTune, and AuditKIT.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from backend.models.experiment import Experiment
from backend.schemas.experiment import ExperimentCreate


class ExperimentService:
    @staticmethod
    def create_experiment(
        payload: ExperimentCreate,
        db: Session,
    ) -> Experiment:
        """Creates a new experiment record in the database."""
        params_json = json.dumps(payload.parameters or {})

        exp = Experiment(
            name=payload.name,
            description=payload.description,
            tool_type=payload.tool_type,
            status="created",
            parameters=params_json,
            results=None,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp

    @staticmethod
    def list_experiments(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        tool_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[Experiment], int]:
        """Queries experiments with optional tool_type and status filtering."""
        query = db.query(Experiment)
        if tool_type:
            query = query.filter(Experiment.tool_type == tool_type.lower())
        if status:
            query = query.filter(Experiment.status == status.lower())

        total = query.count()
        experiments = query.order_by(Experiment.created_at.desc()).offset(skip).limit(limit).all()
        return experiments, total

    @staticmethod
    def get_by_id(db: Session, exp_id: int) -> Optional[Experiment]:
        """Retrieves a single experiment by ID."""
        return db.query(Experiment).filter(Experiment.id == exp_id).first()

    @staticmethod
    def update_status(
        db: Session,
        exp_id: int,
        status: str,
        results: Optional[Dict[str, Any]] = None,
    ) -> Optional[Experiment]:
        """Updates the status and optional results of an experiment."""
        exp = db.query(Experiment).filter(Experiment.id == exp_id).first()
        if not exp:
            return None

        exp.status = status
        if results is not None:
            exp.results = json.dumps(results)

        db.commit()
        db.refresh(exp)
        return exp
