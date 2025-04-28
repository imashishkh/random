"""
Perplexity Collection Scheduler

This module provides functionality for scheduling and managing
collection jobs that use the Perplexity API.
"""
import logging
import time
import asyncio
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job

from .perplexity.client import get_perplexity_client
from .perplexity.query_generator import QueryGenerator
from .perplexity.parser import get_response_parser
from .perplexity.categorizer import get_content_categorizer
from .perplexity.storage import get_research_storage

# Set up logging
logger = logging.getLogger(__name__)

class CollectionScheduler:
    """
    Scheduler for Perplexity API collection jobs.
    Manages periodic collection of different types of financial data.
    """
    
    def __init__(self):
        """Initialize the scheduler with necessary components."""
        self.scheduler = AsyncIOScheduler()
        self.client = get_perplexity_client()
        self.query_generator = QueryGenerator()
        self.parser = get_response_parser()
        self.categorizer = get_content_categorizer()
        self.storage = get_research_storage()
        self.jobs = {}
        self.running = False
        
        # Collection metrics
        self.metrics = {
            "total_collections": 0,
            "successful_collections": 0,
            "failed_collections": 0,
            "last_collection_time": None,
            "items_collected": 0,
            "api_errors": 0
        }
        
        logger.info("Collection scheduler initialized")
    
    def start(self):
        """Start the scheduler."""
        if not self.running:
            self.scheduler.start()
            self.running = True
            logger.info("Collection scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        if self.running:
            self.scheduler.shutdown()
            self.running = False
            logger.info("Collection scheduler stopped")
    
    def schedule_market_news_collection(
        self,
        interval_minutes: int = 30,
        market: str = "forex",
        specific_pairs: Optional[List[str]] = None
    ) -> str:
        """
        Schedule periodic market news collection.
        
        Args:
            interval_minutes: Collection interval in minutes
            market: Market type (forex, equities, etc.)
            specific_pairs: List of specific currency pairs or instruments
            
        Returns:
            Job ID
        """
        job_id = f"market_news_{market}_{interval_minutes}min"
        
        # Create job function
        async def collect_market_news():
            await self._collect_market_news(market, specific_pairs)
        
        # Schedule job
        job = self.scheduler.add_job(
            collect_market_news,
            IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True
        )
        
        self.jobs[job_id] = job
        logger.info(f"Scheduled market news collection for {market} every {interval_minutes} minutes")
        return job_id
    
    def schedule_economic_calendar_collection(
        self,
        time_of_day: str = "07:00",
        indicators: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
        days_ahead: int = 7
    ) -> str:
        """
        Schedule daily economic calendar collection.
        
        Args:
            time_of_day: Time to run collection (HH:MM format)
            indicators: List of indicators to focus on
            countries: List of countries to focus on
            days_ahead: Number of days ahead to look for upcoming releases
            
        Returns:
            Job ID
        """
        job_id = "economic_calendar_daily"
        
        # Default indicators if not provided
        if not indicators:
            indicators = ["GDP", "CPI", "NFP", "PMI", "Retail Sales", "Interest Rate"]
        
        # Parse time
        hour, minute = map(int, time_of_day.split(":"))
        
        # Create job function
        async def collect_economic_calendar():
            await self._collect_economic_indicators(indicators, countries, days_ahead)
        
        # Schedule job
        job = self.scheduler.add_job(
            collect_economic_calendar,
            CronTrigger(hour=hour, minute=minute),
            id=job_id,
            replace_existing=True
        )
        
        self.jobs[job_id] = job
        logger.info(f"Scheduled economic calendar collection daily at {time_of_day}")
        return job_id
    
    def schedule_central_bank_collection(
        self,
        day_of_week: int = 1,  # Monday=0, Sunday=6
        time_of_day: str = "09:00",
        banks: Optional[List[str]] = None
    ) -> str:
        """
        Schedule weekly central bank information collection.
        
        Args:
            day_of_week: Day of week to run collection (0-6, Monday=0)
            time_of_day: Time to run collection (HH:MM format)
            banks: List of central banks to focus on
            
        Returns:
            Job ID
        """
        job_id = "central_bank_weekly"
        
        # Default banks if not provided
        if not banks:
            banks = ["Federal Reserve", "ECB", "Bank of Japan", "Bank of England"]
        
        # Parse time
        hour, minute = map(int, time_of_day.split(":"))
        
        # Create job function
        async def collect_central_bank_info():
            await self._collect_central_bank_info(banks)
        
        # Schedule job
        job = self.scheduler.add_job(
            collect_central_bank_info,
            CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute),
            id=job_id,
            replace_existing=True
        )
        
        self.jobs[job_id] = job
        logger.info(f"Scheduled central bank collection weekly on day {day_of_week} at {time_of_day}")
        return job_id
    
    def schedule_market_sentiment_collection(
        self,
        interval_hours: int = 12,
        markets: Optional[List[str]] = None,
        specific_instruments: Optional[List[str]] = None
    ) -> str:
        """
        Schedule periodic market sentiment collection.
        
        Args:
            interval_hours: Collection interval in hours
            markets: List of markets to analyze
            specific_instruments: List of specific instruments to focus on
            
        Returns:
            Job ID
        """
        # Default markets if not provided
        if not markets:
            markets = ["forex", "equities"]
        
        job_ids = []
        
        for market in markets:
            job_id = f"sentiment_{market}_{interval_hours}h"
            
            # Create job function
            async def collect_sentiment(mkt=market, instr=specific_instruments):
                await self._collect_market_sentiment(mkt, instr)
            
            # Schedule job
            job = self.scheduler.add_job(
                collect_sentiment,
                IntervalTrigger(hours=interval_hours),
                id=job_id,
                replace_existing=True
            )
            
            self.jobs[job_id] = job
            job_ids.append(job_id)
            logger.info(f"Scheduled market sentiment collection for {market} every {interval_hours} hours")
        
        return ",".join(job_ids)
    
    def schedule_one_time_collection(
        self,
        collection_type: str,
        params: Dict[str, Any],
        run_time: Optional[datetime] = None
    ) -> str:
        """
        Schedule a one-time collection job.
        
        Args:
            collection_type: Type of collection (market_news, economic, central_bank, sentiment)
            params: Parameters for the collection
            run_time: Time to run the collection (None for immediate)
            
        Returns:
            Job ID
        """
        # Generate unique job ID
        timestamp = int(time.time())
        job_id = f"onetime_{collection_type}_{timestamp}"
        
        # Create job function based on collection type
        if collection_type == "market_news":
            async def job_func():
                await self._collect_market_news(
                    params.get("market", "forex"),
                    params.get("specific_pairs")
                )
        elif collection_type == "economic":
            async def job_func():
                await self._collect_economic_indicators(
                    params.get("indicators"),
                    params.get("countries"),
                    params.get("days_ahead", 7)
                )
        elif collection_type == "central_bank":
            async def job_func():
                await self._collect_central_bank_info(
                    params.get("banks")
                )
        elif collection_type == "sentiment":
            async def job_func():
                await self._collect_market_sentiment(
                    params.get("market", "forex"),
                    params.get("specific_instruments")
                )
        else:
            raise ValueError(f"Unknown collection type: {collection_type}")
        
        # Set up trigger
        if run_time is None:
            # Run immediately
            trigger = DateTrigger(run_date=datetime.now() + timedelta(seconds=1))
        else:
            trigger = DateTrigger(run_date=run_time)
        
        # Schedule job
        job = self.scheduler.add_job(
            job_func,
            trigger,
            id=job_id
        )
        
        self.jobs[job_id] = job
        logger.info(f"Scheduled one-time {collection_type} collection with ID {job_id}")
        return job_id
    
    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.
        
        Args:
            job_id: ID of the job to remove
            
        Returns:
            Success status
        """
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self.jobs:
                del self.jobs[job_id]
            logger.info(f"Removed job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Error removing job {job_id}: {e}")
            return False
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all scheduled jobs.
        
        Returns:
            List of job information dictionaries
        """
        jobs_info = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "None"
            job_info = {
                "id": job.id,
                "next_run_time": next_run,
                "trigger": str(job.trigger),
            }
            jobs_info.append(job_info)
        return jobs_info
    
    async def run_now(self, job_id: str) -> bool:
        """
        Run a scheduled job immediately.
        
        Args:
            job_id: ID of the job to run
            
        Returns:
            Success status
        """
        job = self.scheduler.get_job(job_id)
        if job:
            await job.func()
            logger.info(f"Manually ran job {job_id}")
            return True
        else:
            logger.error(f"Job {job_id} not found")
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get collection metrics.
        
        Returns:
            Metrics dictionary
        """
        return self.metrics
    
    async def _collect_market_news(
        self,
        market: str,
        specific_pairs: Optional[List[str]] = None
    ):
        """Collect market news using Perplexity API."""
        logger.info(f"Collecting market news for {market}")
        self.metrics["total_collections"] += 1
        self.metrics["last_collection_time"] = datetime.now().isoformat()
        
        try:
            # Generate query
            query = self.query_generator.create_market_news_query(
                market=market,
                timeframe="today",
                specific_pairs=specific_pairs
            )
            
            # Send API request
            response = self.client.query(query)
            content = self.client.get_response_content(response)
            
            # Parse response
            news_items = self.parser.parse_market_news(content)
            logger.info(f"Extracted {len(news_items)} market news items")
            
            # Categorize and store
            stored_count = 0
            for item in news_items:
                # Add metadata
                item["collection_time"] = datetime.now().isoformat()
                item["collection_type"] = "market_news"
                item["market"] = market
                if specific_pairs:
                    item["specific_pairs"] = specific_pairs
                
                # Categorize
                categorized_item = self.categorizer.categorize(item)
                
                # Store
                success = await self.storage.store_item(categorized_item)
                if success:
                    stored_count += 1
            
            logger.info(f"Stored {stored_count} market news items")
            self.metrics["successful_collections"] += 1
            self.metrics["items_collected"] += stored_count
            
        except Exception as e:
            logger.error(f"Error collecting market news: {e}")
            self.metrics["failed_collections"] += 1
            self.metrics["api_errors"] += 1
    
    async def _collect_economic_indicators(
        self,
        indicators: Optional[List[str]],
        countries: Optional[List[str]],
        days_ahead: int
    ):
        """Collect economic indicators using Perplexity API."""
        logger.info(f"Collecting economic indicators for next {days_ahead} days")
        self.metrics["total_collections"] += 1
        self.metrics["last_collection_time"] = datetime.now().isoformat()
        
        try:
            # Generate query
            query = self.query_generator.create_economic_indicator_query(
                indicators=indicators or ["GDP", "CPI", "NFP", "PMI", "Interest Rate"],
                countries=countries,
                timeframe="upcoming",
                days_ahead=days_ahead
            )
            
            # Send API request
            response = self.client.query(query)
            content = self.client.get_response_content(response)
            
            # Parse response
            indicators = self.parser.parse_economic_indicators(content)
            logger.info(f"Extracted {len(indicators)} economic indicators")
            
            # Categorize and store
            stored_count = 0
            for item in indicators:
                # Add metadata
                item["collection_time"] = datetime.now().isoformat()
                item["collection_type"] = "economic_indicator"
                if countries:
                    item["countries"] = countries
                
                # Categorize
                categorized_item = self.categorizer.categorize(item)
                
                # Store
                success = await self.storage.store_item(categorized_item)
                if success:
                    stored_count += 1
            
            logger.info(f"Stored {stored_count} economic indicators")
            self.metrics["successful_collections"] += 1
            self.metrics["items_collected"] += stored_count
            
        except Exception as e:
            logger.error(f"Error collecting economic indicators: {e}")
            self.metrics["failed_collections"] += 1
            self.metrics["api_errors"] += 1
    
    async def _collect_central_bank_info(
        self,
        banks: Optional[List[str]]
    ):
        """Collect central bank information using Perplexity API."""
        logger.info(f"Collecting central bank information")
        self.metrics["total_collections"] += 1
        self.metrics["last_collection_time"] = datetime.now().isoformat()
        
        try:
            # Generate query
            query = self.query_generator.create_central_bank_query(
                banks=banks,
                focus="monetary policy",
                timeframe="recent"
            )
            
            # Send API request
            response = self.client.query(query)
            content = self.client.get_response_content(response)
            
            # Parse response
            bank_info = self.parser.parse_central_bank_info(content)
            logger.info(f"Extracted information for {len(bank_info)} central banks")
            
            # Categorize and store
            stored_count = 0
            for item in bank_info:
                # Add metadata
                item["collection_time"] = datetime.now().isoformat()
                item["collection_type"] = "central_bank"
                
                # Categorize
                categorized_item = self.categorizer.categorize(item)
                
                # Store
                success = await self.storage.store_item(categorized_item)
                if success:
                    stored_count += 1
            
            logger.info(f"Stored information for {stored_count} central banks")
            self.metrics["successful_collections"] += 1
            self.metrics["items_collected"] += stored_count
            
        except Exception as e:
            logger.error(f"Error collecting central bank information: {e}")
            self.metrics["failed_collections"] += 1
            self.metrics["api_errors"] += 1
    
    async def _collect_market_sentiment(
        self,
        market: str,
        specific_instruments: Optional[List[str]] = None
    ):
        """Collect market sentiment using Perplexity API."""
        logger.info(f"Collecting market sentiment for {market}")
        self.metrics["total_collections"] += 1
        self.metrics["last_collection_time"] = datetime.now().isoformat()
        
        try:
            # Generate query
            query = self.query_generator.create_market_sentiment_query(
                market=market,
                specific_instruments=specific_instruments
            )
            
            # Send API request
            response = self.client.query(query)
            content = self.client.get_response_content(response)
            
            # Parse response
            sentiment = self.parser.parse_market_sentiment(content)
            
            # Add metadata
            sentiment["collection_time"] = datetime.now().isoformat()
            sentiment["collection_type"] = "market_sentiment"
            sentiment["market"] = market
            if specific_instruments:
                sentiment["specific_instruments"] = specific_instruments
            
            # Categorize
            categorized_sentiment = self.categorizer.categorize(sentiment)
            
            # Store
            success = await self.storage.store_item(categorized_sentiment)
            
            if success:
                logger.info(f"Stored market sentiment for {market}")
                self.metrics["successful_collections"] += 1
                self.metrics["items_collected"] += 1
            else:
                logger.error(f"Failed to store market sentiment for {market}")
                self.metrics["failed_collections"] += 1
            
        except Exception as e:
            logger.error(f"Error collecting market sentiment: {e}")
            self.metrics["failed_collections"] += 1
            self.metrics["api_errors"] += 1


# Singleton instance
collection_scheduler = CollectionScheduler()


def get_collection_scheduler() -> CollectionScheduler:
    """
    Get the CollectionScheduler instance.
    
    Returns:
        The CollectionScheduler singleton
    """
    return collection_scheduler 