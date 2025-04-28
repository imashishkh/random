"""
Unit tests for the core pipeline module.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from ..core.pipeline import (
    PipelineStage,
    DataPipeline,
    CollectionStage,
    TransformationStage,
    FilterStage,
    StorageStage
)


class TestStage(PipelineStage):
    """Test implementation of PipelineStage."""
    
    def __init__(self, name, process_func=None):
        super().__init__(name)
        self.process_func = process_func or AsyncMock(return_value="default_result")
    
    async def process(self, data):
        """Process the input data using the provided mock function."""
        return await self.process_func(data)


@pytest.fixture
def pipeline():
    """Fixture for a test pipeline."""
    return DataPipeline("test-pipeline")


@pytest.mark.asyncio
async def test_pipeline_empty():
    """Test an empty pipeline returns the input data unchanged."""
    pipeline = DataPipeline("empty-pipeline")
    input_data = {"test": "data"}
    
    result = await pipeline.run(input_data)
    
    assert result == input_data


@pytest.mark.asyncio
async def test_pipeline_single_stage(pipeline):
    """Test a pipeline with a single stage."""
    process_mock = AsyncMock(return_value={"processed": "data"})
    stage = TestStage("test-stage", process_mock)
    
    pipeline.add_stage(stage)
    
    input_data = {"test": "data"}
    result = await pipeline.run(input_data)
    
    process_mock.assert_called_once_with(input_data)
    assert result == {"processed": "data"}


@pytest.mark.asyncio
async def test_pipeline_multiple_stages(pipeline):
    """Test a pipeline with multiple stages."""
    # Setup
    stage1_mock = AsyncMock(return_value={"stage1": "result"})
    stage2_mock = AsyncMock(return_value={"stage2": "result"})
    stage3_mock = AsyncMock(return_value={"stage3": "result"})
    
    pipeline.add_stage(TestStage("stage1", stage1_mock))
    pipeline.add_stage(TestStage("stage2", stage2_mock))
    pipeline.add_stage(TestStage("stage3", stage3_mock))
    
    # Execute
    input_data = {"input": "data"}
    result = await pipeline.run(input_data)
    
    # Verify
    stage1_mock.assert_called_once_with(input_data)
    stage2_mock.assert_called_once_with({"stage1": "result"})
    stage3_mock.assert_called_once_with({"stage2": "result"})
    assert result == {"stage3": "result"}


@pytest.mark.asyncio
async def test_pipeline_stage_error(pipeline):
    """Test error handling in pipeline."""
    # Setup
    stage1_mock = AsyncMock(return_value={"stage1": "result"})
    stage2_mock = AsyncMock(side_effect=ValueError("Test error"))
    stage3_mock = AsyncMock(return_value={"stage3": "result"})
    
    pipeline.add_stage(TestStage("stage1", stage1_mock))
    pipeline.add_stage(TestStage("stage2", stage2_mock))
    pipeline.add_stage(TestStage("stage3", stage3_mock))
    
    # Execute and verify
    input_data = {"input": "data"}
    with pytest.raises(ValueError) as excinfo:
        await pipeline.run(input_data)
    
    # Verify
    assert "Test error" in str(excinfo.value)
    stage1_mock.assert_called_once_with(input_data)
    stage2_mock.assert_called_once_with({"stage1": "result"})
    stage3_mock.assert_not_called()


@pytest.mark.asyncio
async def test_collection_stage():
    """Test the CollectionStage."""
    # Setup
    collector_func = AsyncMock(return_value={"collected": "data"})
    stage = CollectionStage("collector", collector_func)
    
    # Execute
    result = await stage.process(None)
    
    # Verify
    collector_func.assert_called_once()
    assert result == {"collected": "data"}


@pytest.mark.asyncio
async def test_transformation_stage():
    """Test the TransformationStage."""
    # Setup
    transform_func = AsyncMock(return_value={"transformed": "data"})
    stage = TransformationStage("transformer", transform_func)
    
    input_data = {"input": "data"}
    
    # Execute
    result = await stage.process(input_data)
    
    # Verify
    transform_func.assert_called_once_with(input_data)
    assert result == {"transformed": "data"}


@pytest.mark.asyncio
async def test_filter_stage():
    """Test the FilterStage."""
    # Setup
    filter_func = AsyncMock()
    filter_func.side_effect = [True, False, True]
    
    stage = FilterStage("filter", filter_func)
    
    input_data = [
        {"id": 1, "keep": True},
        {"id": 2, "keep": False},
        {"id": 3, "keep": True}
    ]
    
    # Execute
    result = await stage.process(input_data)
    
    # Verify
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 3
    assert filter_func.call_count == 3


@pytest.mark.asyncio
async def test_storage_stage():
    """Test the StorageStage."""
    # Setup
    storage_func = AsyncMock()
    stage = StorageStage("storage", storage_func)
    
    input_data = {"input": "data"}
    
    # Execute
    result = await stage.process(input_data)
    
    # Verify
    storage_func.assert_called_once_with(input_data)
    assert result == input_data  # Storage stage should pass through the data


@pytest.mark.asyncio
async def test_pipeline_integration():
    """Test a complete pipeline with various stage types."""
    # Setup
    collector_func = AsyncMock(return_value=[
        {"id": 1, "data": "item1", "keep": True},
        {"id": 2, "data": "item2", "keep": False},
        {"id": 3, "data": "item3", "keep": True}
    ])
    
    transform_func = AsyncMock(
        side_effect=lambda items: [{"transformed_id": item["id"], "value": item["data"]} for item in items]
    )
    
    filter_func = AsyncMock(side_effect=lambda item: item["transformed_id"] % 2 == 1)
    
    storage_func = AsyncMock()
    
    pipeline = DataPipeline("test-integration")
    pipeline.add_stage(CollectionStage("collector", collector_func))
    pipeline.add_stage(TransformationStage("transformer", transform_func))
    pipeline.add_stage(FilterStage("filter", filter_func))
    pipeline.add_stage(StorageStage("storage", storage_func))
    
    # Execute
    result = await pipeline.run(None)
    
    # Verify
    collector_func.assert_called_once()
    transform_func.assert_called_once()
    assert filter_func.call_count == 3
    
    # Only odd IDs should remain after filtering
    assert len(result) == 2
    assert result[0]["transformed_id"] == 1
    assert result[1]["transformed_id"] == 3
    
    storage_func.assert_called_once_with(result) 