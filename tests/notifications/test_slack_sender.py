import unittest
from unittest.mock import patch, MagicMock
import json

# Import the slack sender
from src.notifications.slack_sender import SlackSender


class TestSlackSender(unittest.TestCase):
    def setUp(self):
        """Set up test configuration"""
        self.slack_config = {
            "enabled": True,
            "webhook_url": "https://hooks.slack.com/services/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",
            "channel": "#trading-alerts",
            "username": "Forex-Bot"
        }

    @patch('requests.post')
    def test_send_message(self, mock_post):
        """Test sending a message to Slack via webhook"""
        # Set up mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_post.return_value = mock_response
        
        # Create slack sender
        slack_sender = SlackSender(self.slack_config)
        
        # Send test message
        slack_sender.send_message(
            message="This is a test message.",
            level="info"
        )
        
        # Verify post was called with correct data
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Check URL
        self.assertEqual(args[0], self.slack_config["webhook_url"])
        
        # Check payload
        payload = json.loads(kwargs["data"])
        self.assertEqual(payload["channel"], "#trading-alerts")
        self.assertEqual(payload["username"], "Forex-Bot")
        self.assertIn("This is a test message.", payload["text"])
        
        # Check headers
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")

    @patch('requests.post')
    def test_message_formatting_by_level(self, mock_post):
        """Test that messages are formatted according to notification level"""
        # Set up mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_post.return_value = mock_response
        
        # Create slack sender
        slack_sender = SlackSender(self.slack_config)
        
        # Test different notification levels
        levels = ["info", "warning", "error", "success"]
        expected_icons = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":x:",
            "success": ":white_check_mark:"
        }
        
        for level in levels:
            # Reset mock
            mock_post.reset_mock()
            
            # Send test message with current level
            slack_sender.send_message(
                message=f"This is a test {level} message.",
                level=level
            )
            
            # Verify post was called
            mock_post.assert_called_once()
            
            # Get payload
            args, kwargs = mock_post.call_args
            payload = json.loads(kwargs["data"])
            
            # Verify level-specific formatting
            self.assertIn(expected_icons[level], payload["text"])
            self.assertIn(f"This is a test {level} message.", payload["text"])

    def test_disabled_slack_sender(self):
        """Test that slack sender doesn't send when disabled"""
        # Create disabled config
        disabled_config = self.slack_config.copy()
        disabled_config["enabled"] = False
        
        # Create slack sender with disabled config
        slack_sender = SlackSender(disabled_config)
        
        # Test that send_message doesn't attempt to send
        with patch('requests.post') as mock_post:
            slack_sender.send_message(
                message="This message should not be sent.",
                level="info"
            )
            
            # Verify post was never called
            mock_post.assert_not_called()

    @patch('requests.post')
    def test_error_handling(self, mock_post):
        """Test handling of HTTP errors when sending to Slack"""
        # Set up mock to return an error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_payload"
        mock_post.return_value = mock_response
        
        # Create slack sender
        slack_sender = SlackSender(self.slack_config)
        
        # Send message and verify it raises an exception
        with self.assertRaises(Exception) as context:
            slack_sender.send_message(
                message="This message should trigger an error.",
                level="error"
            )
        
        # Verify exception message includes status code and response text
        self.assertIn("400", str(context.exception))
        self.assertIn("invalid_payload", str(context.exception))

    @patch('requests.post')
    def test_connection_error_handling(self, mock_post):
        """Test handling of connection errors when sending to Slack"""
        # Set up mock to raise a connection error
        mock_post.side_effect = Exception("Connection error")
        
        # Create slack sender
        slack_sender = SlackSender(self.slack_config)
        
        # Send message and verify it raises an exception
        try:
            slack_sender.send_message(
                message="This message should trigger a connection error.",
                level="warning"
            )
            # If we get here, test should fail
            self.fail("Exception not raised")
        except Exception as e:
            # Verify exception was caught and reraised with additional info
            self.assertIn("Connection error", str(e))

    @patch('requests.post')
    def test_custom_message_formatting(self, mock_post):
        """Test custom message formatting with attachments"""
        # Set up mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_post.return_value = mock_response
        
        # Create slack sender
        slack_sender = SlackSender(self.slack_config)
        
        # Send message with custom formatting
        slack_sender.send_message(
            message="Trade executed",
            level="success",
            attachments=[
                {
                    "fallback": "Trade details",
                    "color": "#36a64f",
                    "title": "Trade Details",
                    "fields": [
                        {
                            "title": "Currency Pair",
                            "value": "EUR/USD",
                            "short": True
                        },
                        {
                            "title": "Position",
                            "value": "BUY",
                            "short": True
                        },
                        {
                            "title": "Amount",
                            "value": "10,000",
                            "short": True
                        },
                        {
                            "title": "Price",
                            "value": "1.1234",
                            "short": True
                        }
                    ]
                }
            ]
        )
        
        # Verify post was called
        mock_post.assert_called_once()
        
        # Get payload
        args, kwargs = mock_post.call_args
        payload = json.loads(kwargs["data"])
        
        # Verify message text
        self.assertIn("Trade executed", payload["text"])
        
        # Verify attachments
        self.assertIn("attachments", payload)
        self.assertEqual(len(payload["attachments"]), 1)
        
        attachment = payload["attachments"][0]
        self.assertEqual(attachment["color"], "#36a64f")
        self.assertEqual(attachment["title"], "Trade Details")
        self.assertEqual(len(attachment["fields"]), 4)
        
        # Check specific field values
        fields = attachment["fields"]
        self.assertEqual(fields[0]["value"], "EUR/USD")
        self.assertEqual(fields[1]["value"], "BUY")


if __name__ == "__main__":
    unittest.main() 