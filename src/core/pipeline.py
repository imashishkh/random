"""
Data pipeline framework module.

This module provides components for creating modular data pipelines,
including data ingestion, processing, and storage stages.
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, Generic, Awaitable

# Setup logger
logger = logging.getLogger(__name__)

# Type variables for generic pipeline stages
T_IN = TypeVar('T_IN')
T_OUT = TypeVar('T_OUT')


class PipelineStage(Generic[T_IN, T_OUT], ABC):
    """Abstract base class for a stage in a data pipeline."""
    
    def __init__(self, name: str):
        """Initialize the pipeline stage.
        
        Args:
            name: Unique identifier for this stage
        """
        self.name = name
        logger.info(f"Initialized pipeline stage: {name}")
    
    @abstractmethod
    async def process(self, data: T_IN) -> T_OUT:
        """Process the input data and produce output.
        
        Args:
            data: Input data for this stage
            
        Returns:
            Processed output data
        """
        pass
    
    async def __call__(self, data: T_IN) -> T_OUT:
        """Allow stages to be called directly."""
        logger.debug(f"Running pipeline stage: {self.name}")
        return await self.process(data)


class DataPipeline:
    """A pipeline that processes data through a series of stages."""
    
    def __init__(self, name: str, stages: Optional[List[PipelineStage]] = None):
        """Initialize the pipeline with optional stages.
        
        Args:
            name: Unique identifier for this pipeline
            stages: Initial stages to add to the pipeline
        """
        self.name = name
        self.stages: List[PipelineStage] = stages or []
        logger.info(f"Initialized data pipeline: {name} with {len(self.stages)} stages")
    
    def add_stage(self, stage: PipelineStage) -> 'DataPipeline':
        """Add a stage to the pipeline.
        
        Args:
            stage: Stage to add
            
        Returns:
            Self for chaining
        """
        self.stages.append(stage)
        logger.info(f"Added stage '{stage.name}' to pipeline '{self.name}'")
        return self
    
    async def run(self, initial_data: Any) -> Any:
        """Run the pipeline with the given initial data.
        
        Args:
            initial_data: Data to pass to the first stage
            
        Returns:
            Result from the final stage
        """
        logger.info(f"Starting pipeline: {self.name}")
        
        data = initial_data
        for i, stage in enumerate(self.stages):
            logger.debug(f"Running stage {i+1}/{len(self.stages)}: {stage.name}")
            try:
                start_time = asyncio.get_event_loop().time()
                data = await stage(data)
                end_time = asyncio.get_event_loop().time()
                
                logger.debug(f"Stage {stage.name} completed in {end_time - start_time:.2f}s")
            except Exception as e:
                logger.error(f"Error in pipeline '{self.name}' at stage '{stage.name}': {str(e)}")
                raise
        
        logger.info(f"Pipeline '{self.name}' completed successfully")
        return data


class CollectionStage(PipelineStage[None, Any]):
    """Pipeline stage for data collection from external sources."""
    
    def __init__(self, name: str, collector_func: Callable[[], Awaitable[Any]]):
        """Initialize the collection stage.
        
        Args:
            name: Stage name
            collector_func: Async function that collects data
        """
        super().__init__(name)
        self.collector_func = collector_func
    
    async def process(self, _: None) -> Any:
        """Run the collector function to gather data.
        
        Args:
            _: Ignored input
            
        Returns:
            Collected data
        """
        logger.info(f"Starting data collection: {self.name}")
        result = await self.collector_func()
        logger.info(f"Data collection completed: {self.name}")
        return result


class TransformationStage(PipelineStage[T_IN, T_OUT]):
    """Pipeline stage for transforming data."""
    
    def __init__(self, name: str, transform_func: Callable[[T_IN], Awaitable[T_OUT]]):
        """Initialize the transformation stage.
        
        Args:
            name: Stage name
            transform_func: Function to transform the data
        """
        super().__init__(name)
        self.transform_func = transform_func
    
    async def process(self, data: T_IN) -> T_OUT:
        """Transform the input data.
        
        Args:
            data: Input data
            
        Returns:
            Transformed data
        """
        logger.debug(f"Transforming data: {self.name}")
        result = await self.transform_func(data)
        return result


class FilterStage(PipelineStage[List[T_IN], List[T_IN]]):
    """Pipeline stage for filtering data items."""
    
    def __init__(self, name: str, filter_func: Callable[[T_IN], Awaitable[bool]]):
        """Initialize the filter stage.
        
        Args:
            name: Stage name
            filter_func: Function that returns True for items to keep
        """
        super().__init__(name)
        self.filter_func = filter_func
    
    async def process(self, data: List[T_IN]) -> List[T_IN]:
        """Filter the input data items.
        
        Args:
            data: List of input data items
            
        Returns:
            Filtered list with only items that passed the filter
        """
        logger.debug(f"Filtering data: {self.name}")
        result = []
        for item in data:
            if await self.filter_func(item):
                result.append(item)
        
        logger.debug(f"Filtered {len(data)} items to {len(result)} items")
        return result


class StorageStage(PipelineStage[T_IN, T_IN]):
    """Pipeline stage for storing data while passing it through."""
    
    def __init__(self, name: str, storage_func: Callable[[T_IN], Awaitable[None]]):
        """Initialize the storage stage.
        
        Args:
            name: Stage name
            storage_func: Function to store the data
        """
        super().__init__(name)
        self.storage_func = storage_func
    
    async def process(self, data: T_IN) -> T_IN:
        """Store the input data and pass it through.
        
        Args:
            data: Input data
            
        Returns:
            Same input data, unmodified
        """
        logger.info(f"Storing data: {self.name}")
        await self.storage_func(data)
        return data 