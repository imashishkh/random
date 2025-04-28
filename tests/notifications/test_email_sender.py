import unittest
from unittest.mock import patch, MagicMock
import os
import json
import tempfile

# Import the email sender
from src.notifications.email_sender import EmailSender


class TestEmailSender(unittest.TestCase):
    def setUp(self):
        """Set up test configuration"""
        self.email_config = {
            "enabled": True,
            "smtp_server": "smtp.test.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "test_password",
            "from_email": "test-bot@example.com",
            "recipients": ["admin@example.com", "analyst@example.com"],
            "use_tls": True
        }

    @patch('smtplib.SMTP')
    def test_send_email(self, mock_smtp):
        """Test sending an email via SMTP"""
        # Set up mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # Create email sender
        email_sender = EmailSender(self.email_config)
        
        # Send test email
        email_sender.send_email(
            subject="Test Subject",
            message="This is a test message.",
            level="info"
        )
        
        # Verify SMTP server was initialized correctly
        mock_smtp.assert_called_once_with("smtp.test.com", 587)
        
        # Verify TLS was started
        mock_server.starttls.assert_called_once()
        
        # Verify login was attempted with correct credentials
        mock_server.login.assert_called_once_with("test@example.com", "test_password")
        
        # Verify send_message was called
        self.assertEqual(mock_server.send_message.call_count, 1)
        
        # Get the email message that was sent
        args, kwargs = mock_server.send_message.call_args
        email_msg = args[0]
        
        # Verify email headers
        self.assertEqual(email_msg["From"], "test-bot@example.com")
        self.assertEqual(email_msg["To"], "admin@example.com, analyst@example.com")
        self.assertEqual(email_msg["Subject"], "Test Subject")
        
        # Verify email content
        self.assertIn("This is a test message.", email_msg.get_content().decode())
        
        # Verify SMTP connection was closed
        mock_server.quit.assert_called_once()

    @patch('smtplib.SMTP')
    def test_send_email_without_tls(self, mock_smtp):
        """Test sending an email without TLS"""
        # Modify config to disable TLS
        config_without_tls = self.email_config.copy()
        config_without_tls["use_tls"] = False
        
        # Set up mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # Create email sender with modified config
        email_sender = EmailSender(config_without_tls)
        
        # Send test email
        email_sender.send_email(
            subject="Test Subject",
            message="This is a test message without TLS.",
            level="warning"
        )
        
        # Verify SMTP server was initialized correctly
        mock_smtp.assert_called_once_with("smtp.test.com", 587)
        
        # Verify TLS was NOT started
        mock_server.starttls.assert_not_called()
        
        # Rest of assertions remain the same
        mock_server.login.assert_called_once()
        self.assertEqual(mock_server.send_message.call_count, 1)
        mock_server.quit.assert_called_once()

    @patch('smtplib.SMTP')
    def test_email_message_formatting(self, mock_smtp):
        """Test that email messages are formatted correctly with level-based styling"""
        # Set up mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # Create email sender
        email_sender = EmailSender(self.email_config)
        
        # Test different notification levels
        levels = ["info", "warning", "error", "success"]
        
        for level in levels:
            # Reset mock
            mock_server.reset_mock()
            
            # Send test email with current level
            email_sender.send_email(
                subject=f"Test {level.capitalize()} Subject",
                message=f"This is a test {level} message.",
                level=level
            )
            
            # Verify email was sent
            self.assertEqual(mock_server.send_message.call_count, 1)
            
            # Get the email message that was sent
            args, kwargs = mock_server.send_message.call_args
            email_msg = args[0]
            email_content = email_msg.get_content().decode()
            
            # Verify level-specific formatting
            if level == "info":
                self.assertIn("Info:", email_content)
            elif level == "warning":
                self.assertIn("Warning:", email_content)
            elif level == "error":
                self.assertIn("Error:", email_content)
            elif level == "success":
                self.assertIn("Success:", email_content)

    def test_disabled_email_sender(self):
        """Test that email sender doesn't send when disabled"""
        # Create disabled config
        disabled_config = self.email_config.copy()
        disabled_config["enabled"] = False
        
        # Create email sender with disabled config
        email_sender = EmailSender(disabled_config)
        
        # Test that send_email doesn't attempt to send
        with patch('smtplib.SMTP') as mock_smtp:
            email_sender.send_email(
                subject="Test Disabled Subject",
                message="This message should not be sent.",
                level="info"
            )
            
            # Verify SMTP was never created
            mock_smtp.assert_not_called()

    @patch('smtplib.SMTP')
    def test_smtp_error_handling(self, mock_smtp):
        """Test handling of SMTP errors"""
        # Set up mock to raise an exception
        mock_smtp.side_effect = Exception("SMTP connection error")
        
        # Create email sender
        email_sender = EmailSender(self.email_config)
        
        # Send email and verify it handles the exception
        try:
            email_sender.send_email(
                subject="Test Error Subject",
                message="This message should trigger an error.",
                level="error"
            )
            # If we get here, test should fail - exception should be caught but reraised
            self.fail("Exception not raised")
        except Exception as e:
            # Verify exception was caught and reraised with additional info
            self.assertIn("SMTP connection error", str(e))

    @patch('smtplib.SMTP')
    def test_custom_html_template(self, mock_smtp):
        """Test that custom HTML templates are applied correctly"""
        # Set up mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # Create config with custom template
        custom_template_config = self.email_config.copy()
        custom_template_config["html_template"] = """
        <!DOCTYPE html>
        <html>
        <body>
            <h1>{subject}</h1>
            <div style="border: 1px solid #ccc; padding: 10px;">
                {message}
            </div>
            <p>Custom Footer - {level}</p>
        </body>
        </html>
        """
        
        # Create email sender with custom template
        email_sender = EmailSender(custom_template_config)
        
        # Send test email
        email_sender.send_email(
            subject="Custom Template Test",
            message="Testing custom template.",
            level="info"
        )
        
        # Get the email message that was sent
        args, kwargs = mock_server.send_message.call_args
        email_msg = args[0]
        email_content = email_msg.get_content().decode()
        
        # Verify custom template was applied
        self.assertIn("<h1>Custom Template Test</h1>", email_content)
        self.assertIn("Testing custom template.", email_content)
        self.assertIn("Custom Footer - info", email_content)


if __name__ == "__main__":
    unittest.main() 