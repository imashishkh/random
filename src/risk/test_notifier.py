"""
Tests for the RiskNotifier class.

This module contains unit tests for the RiskNotifier implementation.
"""

import unittest
import json
import time
from unittest.mock import patch, MagicMock
from datetime import datetime

from .notifier import RiskNotifier, NotificationConfig, NotificationLevel, NotificationTemplate


class TestRiskNotifier(unittest.TestCase):
    """Test cases for the RiskNotifier class."""
    
    def setUp(self):
        """Set up test environment."""
        self.webhook_url = "https://hooks.slack.com/services/FAKE/WEBHOOK/URL"
        self.config = NotificationConfig(
            slack_webhook_url=self.webhook_url,
            rate_limit_period=60,
            rate_limit_count={
                NotificationLevel.INFO.value: 5,
                NotificationLevel.WARNING.value: 3,
                NotificationLevel.CRITICAL.value: 1,
            }
        )
        self.notifier = RiskNotifier(self.config)
    
    @patch('requests.post')
    def test_notify_simple(self, mock_post):
        """Test simple notification."""
        # Set up the mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test notification
        result = self.notifier.notify_simple(
            NotificationLevel.INFO,
            "Test Title",
            "Test Message"
        )
        
        # Assert request was made with expected data
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], self.webhook_url)
        
        # Verify payload
        payload = json.loads(kwargs['data'])
        self.assertIn('attachments', payload)
        self.assertEqual(len(payload['attachments']), 1)
        self.assertEqual(payload['attachments'][0]['color'], '#36a64f')  # Info color
        
        # Verify blocks
        blocks = payload['attachments'][0]['blocks']
        self.assertTrue(any(block['type'] == 'header' and block['text']['text'] == 'Test Title' for block in blocks))
        self.assertTrue(any(block['type'] == 'section' and block['text']['text'] == 'Test Message' for block in blocks))
        
        # Verify result
        self.assertTrue(result)
    
    @patch('requests.post')
    def test_notify_with_template(self, mock_post):
        """Test notification with template."""
        # Set up the mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Add test template
        self.notifier.add_template("test_template", NotificationTemplate(
            title="Test Template: {item}",
            message="This is a test for {item} with value {value}",
            fields={
                "Item": "{item}",
                "Value": "{value}"
            }
        ))
        
        # Test notification
        result = self.notifier.notify(
            NotificationLevel.WARNING,
            "test_template",
            {
                "item": "Widget",
                "value": "42"
            }
        )
        
        # Assert request was made
        mock_post.assert_called_once()
        
        # Verify payload
        args, kwargs = mock_post.call_args
        payload = json.loads(kwargs['data'])
        self.assertIn('attachments', payload)
        self.assertEqual(payload['attachments'][0]['color'], '#ffcc00')  # Warning color
        
        # Verify blocks
        blocks = payload['attachments'][0]['blocks']
        self.assertTrue(any(block['type'] == 'header' and block['text']['text'] == 'Test Template: Widget' for block in blocks))
        self.assertTrue(any(block['type'] == 'section' and block['text']['text'] == 'This is a test for Widget with value 42' for block in blocks))
        
        # Verify fields
        fields_block = next((block for block in blocks if block['type'] == 'section' and 'fields' in block), None)
        self.assertIsNotNone(fields_block)
        self.assertEqual(len(fields_block['fields']), 2)
        
        # Verify result
        self.assertTrue(result)
    
    @patch('requests.post')
    def test_rate_limiting(self, mock_post):
        """Test rate limiting functionality."""
        # Set up the mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Configure a strict rate limit for testing
        self.notifier.config.rate_limit_count = {
            NotificationLevel.INFO.value: 2,
            NotificationLevel.WARNING.value: 1,
            NotificationLevel.CRITICAL.value: 1,
        }
        
        # Should allow 2 INFO notifications
        self.assertTrue(self.notifier.notify_simple(NotificationLevel.INFO, "Info 1", "Message 1"))
        self.assertTrue(self.notifier.notify_simple(NotificationLevel.INFO, "Info 2", "Message 2"))
        
        # Third INFO should be rate limited
        self.assertFalse(self.notifier.notify_simple(NotificationLevel.INFO, "Info 3", "Message 3"))
        
        # Should allow 1 WARNING notification
        self.assertTrue(self.notifier.notify_simple(NotificationLevel.WARNING, "Warning 1", "Message 1"))
        
        # Second WARNING should be rate limited
        self.assertFalse(self.notifier.notify_simple(NotificationLevel.WARNING, "Warning 2", "Message 2"))
        
        # Verify correct number of calls
        self.assertEqual(mock_post.call_count, 3)  # 2 info + 1 warning
    
    def test_rate_limit_expiry(self):
        """Test that rate limits expire after the configured period."""
        # Override time.time to control the clock
        original_time = time.time
        
        try:
            # Start with a fixed time
            current_time = 1000.0
            time.time = lambda: current_time
            
            # Configure a strict rate limit for testing
            self.notifier.config.rate_limit_period = 10  # 10 second expiry
            self.notifier.config.rate_limit_count = {
                NotificationLevel.INFO.value: 1
            }
            
            # Mock _send_to_slack to avoid actual API calls
            with patch.object(self.notifier, '_send_to_slack', return_value=True):
                # Send one notification
                self.assertTrue(self.notifier.notify_simple(NotificationLevel.INFO, "Test", "Message"))
                
                # Second notification should be rate limited
                self.assertFalse(self.notifier.notify_simple(NotificationLevel.INFO, "Test", "Message"))
                
                # Advance time past rate limit period
                current_time += 11
                
                # Now should allow another notification
                self.assertTrue(self.notifier.notify_simple(NotificationLevel.INFO, "Test", "Message"))
        finally:
            # Restore original time.time
            time.time = original_time
    
    def test_fallback_to_logging(self):
        """Test fallback to logging when webhook URL is not configured."""
        # Create notifier without webhook URL
        notifier = RiskNotifier(NotificationConfig(
            slack_webhook_url=None,
            fallback_to_logging=True
        ))
        
        # Notification should succeed due to fallback
        with self.assertLogs(level='INFO') as log:
            result = notifier.notify_simple(NotificationLevel.INFO, "Test", "Message")
            self.assertTrue(result)
            self.assertTrue(any("RISK ALERT" in msg for msg in log.output))
        
        # Create notifier without webhook URL and disable fallback
        notifier = RiskNotifier(NotificationConfig(
            slack_webhook_url=None,
            fallback_to_logging=False
        ))
        
        # Notification should fail due to no webhook and no fallback
        with self.assertLogs(level='INFO') as log:
            result = notifier.notify_simple(NotificationLevel.INFO, "Test", "Message")
            self.assertFalse(result)
    
    @patch('requests.post')
    def test_slack_error_handling(self, mock_post):
        """Test handling of Slack API errors."""
        # Set up the mock to return an error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_payload"
        mock_post.return_value = mock_response
        
        # Test notification should capture the error
        with self.assertLogs(level='WARNING') as log:
            result = self.notifier.notify_simple(NotificationLevel.INFO, "Test", "Message")
            self.assertFalse(result)
            self.assertTrue(any("Failed to send Slack notification" in msg for msg in log.output))
    
    @patch('requests.post')
    def test_template_not_found(self, mock_post):
        """Test behavior when template is not found."""
        # Template doesn't exist
        with self.assertLogs(level='ERROR') as log:
            result = self.notifier.notify(
                NotificationLevel.INFO,
                "nonexistent_template",
                {"key": "value"}
            )
            self.assertFalse(result)
            self.assertTrue(any("Template not found" in msg for msg in log.output))
        
        # Mock should not be called
        mock_post.assert_not_called()
    
    @patch('requests.post')
    def test_template_missing_data(self, mock_post):
        """Test behavior when template data is missing."""
        # Add template
        self.notifier.add_template("test_template", NotificationTemplate(
            title="Test: {item}",
            message="Value: {value}",
            fields={}
        ))
        
        # Missing data
        with self.assertLogs(level='ERROR') as log:
            result = self.notifier.notify(
                NotificationLevel.INFO,
                "test_template",
                {"item": "Widget"}  # Missing 'value'
            )
            self.assertFalse(result)
            self.assertTrue(any("Missing data for template" in msg for msg in log.output))
        
        # Mock should not be called
        mock_post.assert_not_called()
    
    @patch('requests.post')
    def test_actions_rendering(self, mock_post):
        """Test that action buttons are properly rendered."""
        # Set up the mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Add template with actions
        self.notifier.add_template("template_with_actions", NotificationTemplate(
            title="Action Test",
            message="Test message",
            fields={},
            actions=[
                {"text": "Button 1", "url": "{url_1}"},
                {"text": "Button 2", "url": "{url_2}"}
            ]
        ))
        
        # Test notification
        self.notifier.notify(
            NotificationLevel.INFO,
            "template_with_actions",
            {
                "url_1": "https://example.com/1",
                "url_2": "https://example.com/2"
            }
        )
        
        # Assert request was made
        mock_post.assert_called_once()
        
        # Verify actions block in payload
        args, kwargs = mock_post.call_args
        payload = json.loads(kwargs['data'])
        blocks = payload['attachments'][0]['blocks']
        
        # Find actions block
        actions_block = next((block for block in blocks if block['type'] == 'actions'), None)
        self.assertIsNotNone(actions_block)
        
        # Verify buttons
        self.assertEqual(len(actions_block['elements']), 2)
        self.assertEqual(actions_block['elements'][0]['text']['text'], "Button 1")
        self.assertEqual(actions_block['elements'][0]['url'], "https://example.com/1")
        self.assertEqual(actions_block['elements'][1]['text']['text'], "Button 2")
        self.assertEqual(actions_block['elements'][1]['url'], "https://example.com/2")


if __name__ == '__main__':
    unittest.main() 