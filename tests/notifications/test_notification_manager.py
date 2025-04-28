import unittest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock

# Import the notification manager
from src.notifications.notification_manager import NotificationManager


class TestNotificationManager(unittest.TestCase):
    def setUp(self):
        """Create a temporary configuration file for testing"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "test_notification_config.json")
        
        # Sample test configuration
        self.test_config = {
            "email": {
                "enabled": True,
                "smtp_server": "smtp.test.com",
                "smtp_port": 587,
                "username": "test@example.com",
                "password": "test_password",
                "from_email": "test-bot@example.com",
                "recipients": ["admin@example.com", "analyst@example.com"],
                "use_tls": True
            },
            "slack": {
                "enabled": True,
                "webhook_url": "https://hooks.slack.com/services/TEST/WEBHOOK/URL",
                "channel": "#test-alerts",
                "username": "TestBot"
            },
            "general": {
                "environment": "test",
                "log_notifications": True,
                "notification_level": "info"
            }
        }
        
        # Write the test configuration to the temporary file
        with open(self.config_path, 'w') as f:
            json.dump(self.test_config, f)

    def tearDown(self):
        """Clean up temporary files"""
        self.temp_dir.cleanup()

    def test_load_config(self):
        """Test that the configuration is loaded correctly"""
        notification_manager = NotificationManager(config_path=self.config_path)
        
        # Verify configuration was loaded correctly
        self.assertEqual(notification_manager.config["email"]["smtp_server"], "smtp.test.com")
        self.assertEqual(notification_manager.config["slack"]["channel"], "#test-alerts")
        self.assertEqual(notification_manager.config["general"]["environment"], "test")

    def test_invalid_config_path(self):
        """Test handling of invalid configuration file path"""
        with self.assertRaises(FileNotFoundError):
            NotificationManager(config_path="/path/does/not/exist.json")

    @patch('src.notifications.email_sender.EmailSender')
    def test_email_notification(self, mock_email_sender):
        """Test sending an email notification"""
        # Set up the mock
        mock_instance = MagicMock()
        mock_email_sender.return_value = mock_instance
        
        # Create NotificationManager with our test config
        notification_manager = NotificationManager(config_path=self.config_path)
        
        # Send a test notification
        notification_manager.send_info("Test Subject", "Test Message")
        
        # Verify the email sender was called correctly
        mock_instance.send_email.assert_called_once()
        args, kwargs = mock_instance.send_email.call_args
        self.assertEqual(kwargs["subject"], "Test Subject")
        self.assertEqual(kwargs["message"], "Test Message")

    @patch('src.notifications.slack_sender.SlackSender')
    def test_slack_notification(self, mock_slack_sender):
        """Test sending a Slack notification"""
        # Set up the mock
        mock_instance = MagicMock()
        mock_slack_sender.return_value = mock_instance
        
        # Create NotificationManager with our test config
        notification_manager = NotificationManager(config_path=self.config_path)
        
        # Send a test notification
        notification_manager.send_warning("Test Warning", "This is a test warning")
        
        # Verify the slack sender was called correctly
        mock_instance.send_message.assert_called_once()
        args, kwargs = mock_instance.send_message.call_args
        self.assertEqual(kwargs["subject"], "Test Warning")
        self.assertEqual(kwargs["message"], "This is a test warning")
        self.assertEqual(kwargs["level"], "warning")

    def test_notification_level_filtering(self):
        """Test that notifications are filtered based on level"""
        # Create config with error-only level
        error_only_config = self.test_config.copy()
        error_only_config["general"]["notification_level"] = "error"
        
        error_config_path = os.path.join(self.temp_dir.name, "error_only_config.json")
        with open(error_config_path, 'w') as f:
            json.dump(error_only_config, f)
        
        # Create manager with patched senders
        with patch('src.notifications.email_sender.EmailSender') as mock_email:
            with patch('src.notifications.slack_sender.SlackSender') as mock_slack:
                # Set up the mocks
                mock_email_instance = MagicMock()
                mock_email.return_value = mock_email_instance
                mock_slack_instance = MagicMock()
                mock_slack.return_value = mock_slack_instance
                
                # Create manager with error-only config
                notification_manager = NotificationManager(config_path=error_config_path)
                
                # Info should not be sent
                notification_manager.send_info("Info Subject", "Info Message")
                mock_email_instance.send_email.assert_not_called()
                mock_slack_instance.send_message.assert_not_called()
                
                # Warning should not be sent
                notification_manager.send_warning("Warning Subject", "Warning Message")
                mock_email_instance.send_email.assert_not_called()
                mock_slack_instance.send_message.assert_not_called()
                
                # Error should be sent
                notification_manager.send_error("Error Subject", "Error Message")
                mock_email_instance.send_email.assert_called_once()
                mock_slack_instance.send_message.assert_called_once()

    def test_format_model_validation_message(self):
        """Test formatting of model validation messages"""
        notification_manager = NotificationManager(config_path=self.config_path)
        
        # Test data
        validation_result = {
            "model_name": "Test Model",
            "accuracy": 0.90,
            "precision": 0.85,
            "recall": 0.88,
            "f1_score": 0.86
        }
        
        message = notification_manager.format_model_validation_message(validation_result)
        
        # Verify message contains all key metrics
        self.assertIn("Test Model", message)
        self.assertIn("90.0%", message)  # Accuracy as percentage
        self.assertIn("85.0%", message)  # Precision as percentage
        self.assertIn("88.0%", message)  # Recall as percentage
        self.assertIn("86.0%", message)  # F1 as percentage

    def test_format_deployment_message(self):
        """Test formatting of deployment messages"""
        notification_manager = NotificationManager(config_path=self.config_path)
        
        # Test data
        deployment_info = {
            "model_name": "Test Deployment Model",
            "environment": "staging",
            "version": "1.2.3",
            "timestamp": "2023-06-15T10:30:00Z",
            "status": "success"
        }
        
        message = notification_manager.format_deployment_message(deployment_info)
        
        # Verify message contains all key information
        self.assertIn("Test Deployment Model", message)
        self.assertIn("staging", message)
        self.assertIn("1.2.3", message)
        self.assertIn("success", message)

    def test_notification_history(self):
        """Test that notification history is correctly maintained"""
        notification_manager = NotificationManager(config_path=self.config_path)
        
        # Send multiple notifications
        notification_manager.send_info("Info 1", "Info Message 1")
        notification_manager.send_warning("Warning 1", "Warning Message 1")
        notification_manager.send_error("Error 1", "Error Message 1")
        
        # Get history
        history = notification_manager.get_notification_history()
        
        # Verify history
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["level"], "info")
        self.assertEqual(history[0]["subject"], "Info 1")
        self.assertEqual(history[1]["level"], "warning")
        self.assertEqual(history[1]["subject"], "Warning 1")
        self.assertEqual(history[2]["level"], "error")
        self.assertEqual(history[2]["subject"], "Error 1")
        
        # Test limit parameter
        limited_history = notification_manager.get_notification_history(limit=2)
        self.assertEqual(len(limited_history), 2)
        self.assertEqual(limited_history[0]["subject"], "Warning 1")
        self.assertEqual(limited_history[1]["subject"], "Error 1")


if __name__ == "__main__":
    unittest.main() 