"""
Reporting services for analytics data.

This module provides the core reporting infrastructure for generating,
storing, and managing analytics reports in various formats.
"""
from abc import ABC, abstractmethod
import io
import os
import uuid
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, BinaryIO, Union, BytesIO

import pandas as pd
import numpy as np
from fastapi import BackgroundTasks
import aiofiles
import aiofiles.os
import boto3
from botocore.exceptions import ClientError

from .models import ReportType, ReportFormat, ReportResponse
from ..config import settings
from ..cache.redis_cache import cache_result, invalidate_cache

# Configure logging
logger = logging.getLogger(__name__)

# Constants
REPORTS_DIR = Path(settings.REPORTS_DIR)
REPORT_EXPIRY_DAYS = settings.REPORT_EXPIRY_DAYS


class ReportGenerator(ABC):
    """Abstract base class for report generators."""
    
    @abstractmethod
    async def generate(self, data: Dict[str, Any], format: ReportFormat) -> BytesIO:
        """
        Generate a report in the specified format.
        
        Args:
            data: The data to include in the report
            format: The output format for the report
            
        Returns:
            A file-like object containing the report
        """
        pass


class PerformanceReportGenerator(ReportGenerator):
    """Generator for performance reports."""
    
    async def generate(self, data: Dict[str, Any], format: ReportFormat) -> BytesIO:
        """Generate a performance report."""
        if format == ReportFormat.JSON:
            return await self._generate_json(data)
        elif format == ReportFormat.CSV:
            return await self._generate_csv(data)
        elif format == ReportFormat.EXCEL:
            return await self._generate_excel(data)
        elif format == ReportFormat.PDF:
            return await self._generate_pdf(data)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    async def _generate_json(self, data: Dict[str, Any]) -> BytesIO:
        """Generate a JSON performance report."""
        buffer = BytesIO()
        json_data = json.dumps(data, indent=2, default=str).encode('utf-8')
        buffer.write(json_data)
        buffer.seek(0)
        return buffer
    
    async def _generate_csv(self, data: Dict[str, Any]) -> BytesIO:
        """Generate a CSV performance report."""
        buffer = BytesIO()
        
        # Convert metrics to DataFrame for easy CSV export
        if "metrics" in data and isinstance(data["metrics"], list):
            df = pd.DataFrame(data["metrics"])
            csv_data = df.to_csv(index=False).encode('utf-8')
            buffer.write(csv_data)
        else:
            # Fallback for data that isn't in the expected format
            csv_data = "No metrics data available".encode('utf-8')
            buffer.write(csv_data)
        
        buffer.seek(0)
        return buffer
    
    async def _generate_excel(self, data: Dict[str, Any]) -> BytesIO:
        """Generate an Excel performance report."""
        buffer = BytesIO()
        
        # Create Excel writer with pandas
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Add summary sheet
            summary_data = {
                "Report ID": data.get("report_id", ""),
                "Generated At": data.get("generated_at", datetime.now().isoformat()),
                "Start Date": data.get("start_date", ""),
                "End Date": data.get("end_date", ""),
                "Account ID": data.get("account_id", ""),
                "Report Type": data.get("report_type", "")
            }
            summary_df = pd.DataFrame([summary_data])
            summary_df.to_excel(writer, sheet_name="Summary", index=False)
            
            # Add metrics sheet
            if "metrics" in data and isinstance(data["metrics"], list):
                metrics_df = pd.DataFrame(data["metrics"])
                metrics_df.to_excel(writer, sheet_name="Metrics", index=False)
        
        buffer.seek(0)
        return buffer
    
    async def _generate_pdf(self, data: Dict[str, Any]) -> BytesIO:
        """Generate a PDF performance report."""
        buffer = BytesIO()
        
        # Implement PDF generation using ReportLab
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        
        # Create document
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Create story (content)
        story = []
        
        # Add title
        title_style = styles["Heading1"]
        title = Paragraph("Performance Report", title_style)
        story.append(title)
        story.append(Spacer(1, 12))
        
        # Add summary information
        summary_style = styles["Normal"]
        summary = [
            Paragraph(f"Report ID: {data.get('report_id', '')}", summary_style),
            Paragraph(f"Generated: {data.get('generated_at', datetime.now().isoformat())}", summary_style),
            Paragraph(f"Period: {data.get('start_date', '')} to {data.get('end_date', '')}", summary_style),
            Paragraph(f"Account: {data.get('account_id', '')}", summary_style)
        ]
        for item in summary:
            story.append(item)
        story.append(Spacer(1, 12))
        
        # Add metrics table
        if "metrics" in data and isinstance(data["metrics"], list):
            metrics_heading = Paragraph("Performance Metrics", styles["Heading2"])
            story.append(metrics_heading)
            story.append(Spacer(1, 8))
            
            # Extract metrics
            metrics = data["metrics"]
            if metrics:
                # Get column names for table
                cols = list(metrics[0].keys())
                
                # Create table data with header row
                table_data = [cols]
                
                # Add data rows
                for metric in metrics:
                    row = [str(metric.get(col, "")) for col in cols]
                    table_data.append(row)
                
                # Create table
                table = Table(table_data)
                
                # Style the table
                style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ])
                table.setStyle(style)
                
                story.append(table)
        
        # Build the PDF
        doc.build(story)
        buffer.seek(0)
        return buffer


class TradeHistoryReportGenerator(ReportGenerator):
    """Generator for trade history reports."""
    
    async def generate(self, data: Dict[str, Any], format: ReportFormat) -> BytesIO:
        """Generate a trade history report."""
        # Similar implementation to PerformanceReportGenerator
        # but with specific logic for trade history reports
        # For brevity, we'll implement this later
        buffer = BytesIO()
        json_data = json.dumps({"message": "Trade history report generation not yet implemented"}).encode('utf-8')
        buffer.write(json_data)
        buffer.seek(0)
        return buffer


class ReportStorage(ABC):
    """Abstract base class for report storage systems."""
    
    @abstractmethod
    async def save(self, report_id: str, data: BytesIO, metadata: Dict[str, Any]) -> str:
        """
        Save a report and return its URL.
        
        Args:
            report_id: The unique identifier for the report
            data: The report data as a file-like object
            metadata: Additional metadata about the report
            
        Returns:
            The URL where the report can be accessed
        """
        pass
    
    @abstractmethod
    async def get(self, report_id: str) -> Tuple[BytesIO, Dict[str, Any]]:
        """
        Retrieve a report and its metadata.
        
        Args:
            report_id: The unique identifier for the report
            
        Returns:
            A tuple containing the report data and its metadata
        """
        pass
    
    @abstractmethod
    async def delete(self, report_id: str) -> bool:
        """
        Delete a report.
        
        Args:
            report_id: The unique identifier for the report
            
        Returns:
            True if the report was successfully deleted, False otherwise
        """
        pass
    
    @abstractmethod
    async def generate_url(self, report_id: str, expire_in: int = 3600) -> str:
        """
        Generate a URL for accessing the report.
        
        Args:
            report_id: The unique identifier for the report
            expire_in: The number of seconds until the URL expires
            
        Returns:
            A signed URL for accessing the report
        """
        pass


class LocalFileStorage(ReportStorage):
    """Storage system that saves reports to the local filesystem."""
    
    def __init__(self, base_dir: Path = REPORTS_DIR):
        """
        Initialize the local file storage.
        
        Args:
            base_dir: The base directory for storing reports
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def save(self, report_id: str, data: BytesIO, metadata: Dict[str, Any]) -> str:
        """Save a report to the local filesystem."""
        # Determine file extension based on format
        format = metadata.get("format", "json").lower()
        file_extension = format
        
        # Create report directory if it doesn't exist
        report_dir = self.base_dir / metadata.get("account_id", "default")
        await self._ensure_dir_exists(report_dir)
        
        # Create the report file path
        file_path = report_dir / f"{report_id}.{file_extension}"
        
        # Save the report data
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data.read())
        
        # Save metadata
        metadata_path = report_dir / f"{report_id}.metadata.json"
        metadata_copy = metadata.copy()
        metadata_copy["file_path"] = str(file_path)
        metadata_copy["created_at"] = datetime.now().isoformat()
        metadata_copy["expires_at"] = (datetime.now() + timedelta(days=REPORT_EXPIRY_DAYS)).isoformat()
        
        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(json.dumps(metadata_copy, default=str))
        
        # Return the URL (file path in this case)
        return str(file_path)
    
    async def get(self, report_id: str) -> Tuple[BytesIO, Dict[str, Any]]:
        """Retrieve a report from the local filesystem."""
        # Find the report metadata
        metadata = await self._get_metadata(report_id)
        
        if not metadata:
            raise FileNotFoundError(f"Report {report_id} not found")
        
        # Check if the report has expired
        expires_at = datetime.fromisoformat(metadata.get("expires_at", "2099-12-31T00:00:00"))
        if expires_at < datetime.now():
            raise FileNotFoundError(f"Report {report_id} has expired")
        
        # Get the report file path
        file_path = metadata.get("file_path")
        if not file_path:
            raise FileNotFoundError(f"File path not found in metadata for report {report_id}")
        
        # Read the report data
        buffer = BytesIO()
        async with aiofiles.open(file_path, "rb") as f:
            buffer.write(await f.read())
        buffer.seek(0)
        
        return buffer, metadata
    
    async def delete(self, report_id: str) -> bool:
        """Delete a report from the local filesystem."""
        try:
            # Find the report metadata
            metadata = await self._get_metadata(report_id)
            
            if not metadata:
                return False
            
            # Get the report file path
            file_path = metadata.get("file_path")
            if not file_path:
                return False
            
            # Delete the report file
            await aiofiles.os.remove(file_path)
            
            # Delete the metadata file
            account_id = metadata.get("account_id", "default")
            metadata_path = self.base_dir / account_id / f"{report_id}.metadata.json"
            await aiofiles.os.remove(metadata_path)
            
            return True
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Error deleting report {report_id}: {e}")
            return False
    
    async def generate_url(self, report_id: str, expire_in: int = 3600) -> str:
        """Generate a URL for accessing the report (local path in this case)."""
        # For local storage, we just return the file path
        # In a real API, this would be an actual URL
        metadata = await self._get_metadata(report_id)
        
        if not metadata:
            raise FileNotFoundError(f"Report {report_id} not found")
        
        # In a real application, you would generate a signed URL here
        # For now, we'll just return the path with an additional query parameter
        return f"/api/v1/analytics/reports/{report_id}"
    
    async def _get_metadata(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Get the metadata for a report."""
        # Metadata is stored by account ID, so we need to search all account directories
        try:
            # Loop through account directories
            for account_dir in await self._list_dirs(self.base_dir):
                metadata_path = account_dir / f"{report_id}.metadata.json"
                
                try:
                    async with aiofiles.open(metadata_path, "r") as f:
                        return json.loads(await f.read())
                except FileNotFoundError:
                    continue
            
            return None
        except Exception as e:
            logger.error(f"Error getting metadata for report {report_id}: {e}")
            return None
    
    async def _ensure_dir_exists(self, dir_path: Path) -> None:
        """Ensure a directory exists."""
        os.makedirs(dir_path, exist_ok=True)
    
    async def _list_dirs(self, parent_dir: Path) -> List[Path]:
        """List all directories in a parent directory."""
        return [path for path in parent_dir.iterdir() if path.is_dir()]


class S3Storage(ReportStorage):
    """Storage system that saves reports to an S3-compatible object store."""
    
    def __init__(self, bucket_name: str = settings.S3_BUCKET_NAME):
        """
        Initialize the S3 storage.
        
        Args:
            bucket_name: The name of the S3 bucket for storing reports
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_ENDPOINT_URL
        )
    
    async def save(self, report_id: str, data: BytesIO, metadata: Dict[str, Any]) -> str:
        """Save a report to S3."""
        # Implementation similar to LocalFileStorage but for S3
        # For brevity, we'll implement this later
        return f"s3://{self.bucket_name}/{report_id}"
    
    async def get(self, report_id: str) -> Tuple[BytesIO, Dict[str, Any]]:
        """Retrieve a report from S3."""
        # Implementation for S3
        # For brevity, we'll implement this later
        buffer = BytesIO()
        metadata = {}
        return buffer, metadata
    
    async def delete(self, report_id: str) -> bool:
        """Delete a report from S3."""
        # Implementation for S3
        # For brevity, we'll implement this later
        return True
    
    async def generate_url(self, report_id: str, expire_in: int = 3600) -> str:
        """Generate a signed URL for accessing the report in S3."""
        # Implementation for S3
        # For brevity, we'll implement this later
        return f"/api/v1/analytics/reports/{report_id}"


class ReportingService:
    """Service for generating and managing reports."""
    
    def __init__(self, storage: ReportStorage = None):
        """
        Initialize the reporting service.
        
        Args:
            storage: The storage system to use for reports
        """
        # Use the specified storage or create a default one based on configuration
        self.storage = storage or self._create_default_storage()
        
        # Initialize report generators
        self.generators = {
            ReportType.PERFORMANCE: PerformanceReportGenerator(),
            ReportType.TRADE_HISTORY: TradeHistoryReportGenerator(),
            # Add other generators as needed
        }
    
    def _create_default_storage(self) -> ReportStorage:
        """Create the default storage system based on configuration."""
        if settings.REPORT_STORAGE_TYPE == "s3":
            return S3Storage()
        else:
            return LocalFileStorage()
    
    async def generate_report(
        self,
        report_type: ReportType,
        format: ReportFormat,
        data: Dict[str, Any],
        background_tasks: Optional[BackgroundTasks] = None
    ) -> ReportResponse:
        """
        Generate a report.
        
        Args:
            report_type: The type of report to generate
            format: The output format for the report
            data: The data to include in the report
            background_tasks: Optional background tasks for async generation
            
        Returns:
            A report response with metadata and download URL
        """
        # Generate a unique report ID
        report_id = str(uuid.uuid4())
        
        # Add report ID to data
        data["report_id"] = report_id
        
        # Create metadata
        metadata = {
            "report_id": report_id,
            "report_type": report_type,
            "format": format,
            "account_id": data.get("account_id", "default"),
            "parameters": {
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "timeframe": data.get("timeframe"),
                "symbol": data.get("symbol")
            }
        }
        
        # Get the appropriate generator
        generator = self.generators.get(report_type)
        if not generator:
            raise ValueError(f"Unsupported report type: {report_type}")
        
        # Generate the report
        if background_tasks:
            # For background generation
            background_tasks.add_task(
                self._generate_and_save_report,
                generator=generator,
                report_id=report_id,
                data=data,
                format=format,
                metadata=metadata
            )
            
            # Return a response with the report ID and a status indicating it's being generated
            return ReportResponse(
                report_id=report_id,
                report_type=report_type,
                format=format,
                url=f"/api/v1/analytics/reports/{report_id}/status",  # Status endpoint
                created_at=datetime.now(),
                parameters=metadata["parameters"],
                status="generating"  # Add status field to the model
            )
        else:
            # For synchronous generation
            report_data = await generator.generate(data, format)
            
            # Save the report
            url = await self.storage.save(report_id, report_data, metadata)
            
            # Generate a URL for accessing the report
            access_url = await self.storage.generate_url(report_id)
            
            # Return the report response
            return ReportResponse(
                report_id=report_id,
                report_type=report_type,
                format=format,
                url=access_url,
                created_at=datetime.now(),
                parameters=metadata["parameters"]
            )
    
    async def _generate_and_save_report(
        self,
        generator: ReportGenerator,
        report_id: str,
        data: Dict[str, Any],
        format: ReportFormat,
        metadata: Dict[str, Any]
    ):
        """
        Generate and save a report in the background.
        
        Args:
            generator: The report generator to use
            report_id: The unique identifier for the report
            data: The data to include in the report
            format: The output format for the report
            metadata: Additional metadata about the report
        """
        try:
            # Generate the report
            report_data = await generator.generate(data, format)
            
            # Save the report
            await self.storage.save(report_id, report_data, metadata)
            
            # Update report status to completed
            # In a real application, you would update a database record here
            logger.info(f"Report {report_id} generated successfully")
        except Exception as e:
            # Log the error and update the report status
            logger.error(f"Error generating report {report_id}: {e}")
            # In a real application, you would update a database record here
    
    async def get_report(self, report_id: str) -> Tuple[BytesIO, Dict[str, Any]]:
        """
        Retrieve a generated report.
        
        Args:
            report_id: The unique identifier for the report
            
        Returns:
            A tuple containing the report data and its metadata
        """
        return await self.storage.get(report_id)
    
    async def delete_report(self, report_id: str) -> bool:
        """
        Delete a report.
        
        Args:
            report_id: The unique identifier for the report
            
        Returns:
            True if the report was successfully deleted, False otherwise
        """
        return await self.storage.delete(report_id)
    
    async def list_reports(self, account_id: str) -> List[Dict[str, Any]]:
        """
        List available reports for an account.
        
        Args:
            account_id: The account ID to list reports for
            
        Returns:
            A list of report metadata
        """
        # Implementation depends on the storage system
        # For brevity, we'll implement this later
        return []
    
    async def cleanup_expired_reports(self):
        """Clean up expired reports to free up storage space."""
        # Implementation depends on the storage system
        # For brevity, we'll implement this later
        pass 