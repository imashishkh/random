"""
Tests for Multi-Factor Authentication Module

This module contains unit tests for the MFA functionality.
"""

import unittest
import time
from unittest.mock import patch, MagicMock
import pyotp

from ..account.mfa import (
    generate_totp_secret, get_totp_uri, verify_totp_code,
    generate_backup_codes, MFAType
)

class MFATests(unittest.TestCase):
    """Test cases for MFA functionality."""
    
    def test_generate_totp_secret(self):
        """Test generating a TOTP secret."""
        secret = generate_totp_secret()
        # Should be a base32-encoded string
        self.assertTrue(all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567' for c in secret))
        # Should be at least 32 characters
        self.assertGreaterEqual(len(secret), 32)
    
    def test_get_totp_uri(self):
        """Test generating a TOTP URI."""
        secret = "JBSWY3DPEHPK3PXP"  # Example secret
        email = "test@example.com"
        issuer = "TestApp"
        
        uri = get_totp_uri(email, secret, issuer)
        
        # URI should contain all the necessary components
        self.assertIn(f"issuer={issuer}", uri)
        self.assertIn(f"secret={secret}", uri)
        self.assertIn(email, uri)
        self.assertTrue(uri.startswith("otpauth://totp/"))
    
    def test_verify_totp_code(self):
        """Test TOTP code verification."""
        # Generate a fixed secret for testing
        secret = "JBSWY3DPEHPK3PXP"
        
        # Generate a valid code
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()
        
        # Test valid code
        self.assertTrue(verify_totp_code(secret, valid_code))
        
        # Test invalid code
        self.assertFalse(verify_totp_code(secret, "000000"))
        
        # Generate a code that's just expired
        # This is a bit tricky since we need to generate a code right before it expires
        current_time = int(time.time())
        step = 30  # Default TOTP time step is 30 seconds
        previous_window = int((current_time - step) / step) * step
        previous_code = totp.at(previous_window)
        
        # Sleep to ensure we're in a new time window
        time.sleep(1)
        
        # Previous code should no longer be valid
        # Note: This test might be flaky depending on timing
        if int(time.time() / step) > int(previous_window / step):
            self.assertFalse(verify_totp_code(secret, previous_code))
    
    def test_generate_backup_codes(self):
        """Test backup code generation."""
        codes = generate_backup_codes()
        
        # Should generate the correct number of codes
        self.assertEqual(len(codes), 10)  # Default NUM_BACKUP_CODES
        
        # Each code should be the correct format (e.g., ABCD-EFGH-IJ)
        for code in codes:
            # Should have hyphens
            self.assertIn('-', code)
            
            # Should not have similar-looking characters (O, 0, I, 1)
            self.assertNotIn('O', code)
            self.assertNotIn('0', code)
            self.assertNotIn('I', code)
            self.assertNotIn('1', code)
    
    @patch('src.account.mfa.get_db_connection')
    def test_setup_mfa_for_user(self, mock_get_db):
        """Test setting up MFA for a user."""
        from src.account.mfa import setup_mfa_for_user
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock user lookup
        mock_cursor.fetchone.return_value = {'email': 'test@example.com'}
        
        # Call the function
        result = setup_mfa_for_user('test-user-id', MFAType.TOTP)
        
        # Check that the function updated the user in the database
        mock_cursor.execute.assert_any_call("""
                UPDATE users 
                SET mfa_enabled = TRUE, mfa_type = %s, mfa_secret = %s
                WHERE id = %s
            """, (MFAType.TOTP, result['secret'], 'test-user-id'))
        
        # Check that backup codes were inserted
        for code in result['backup_codes']:
            mock_cursor.execute.assert_any_call("""
                    INSERT INTO mfa_backup_codes (user_id, code)
                    VALUES (%s, %s)
                """, ('test-user-id', code))
        
        # Check result contains expected keys
        self.assertIn('secret', result)
        self.assertIn('uri', result)
        self.assertIn('backup_codes', result)
        
        # Check URI is valid
        self.assertIn('test@example.com', result['uri'])
    
    @patch('src.account.mfa.get_db_connection')
    def test_verify_mfa_code_with_totp(self, mock_get_db):
        """Test verifying a TOTP code."""
        from src.account.mfa import verify_mfa_code
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Set up a test secret
        test_secret = "JBSWY3DPEHPK3PXP"
        totp = pyotp.TOTP(test_secret)
        valid_code = totp.now()
        
        # Mock user lookup
        mock_cursor.fetchone.side_effect = [
            # First call - get user
            {'mfa_enabled': True, 'mfa_type': MFAType.TOTP, 'mfa_secret': test_secret},
            # Second call - check for backup code (not found)
            None
        ]
        
        # Call the function with valid code
        result = verify_mfa_code('test-user-id', valid_code)
        self.assertTrue(result)
        
        # Call with invalid code
        mock_cursor.fetchone.side_effect = [
            # First call - get user
            {'mfa_enabled': True, 'mfa_type': MFAType.TOTP, 'mfa_secret': test_secret},
            # Second call - check for backup code (not found)
            None
        ]
        result = verify_mfa_code('test-user-id', '000000')
        self.assertFalse(result)
    
    @patch('src.account.mfa.get_db_connection')
    def test_verify_mfa_code_with_backup(self, mock_get_db):
        """Test verifying a backup code."""
        from src.account.mfa import verify_mfa_code
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock user lookup
        mock_cursor.fetchone.side_effect = [
            # First call - get user
            {'mfa_enabled': True, 'mfa_type': MFAType.TOTP, 'mfa_secret': 'some-secret'},
            # Second call - check for backup code (found)
            {'id': 123}
        ]
        
        # Call the function with backup code
        result = verify_mfa_code('test-user-id', 'ABCD-EFGH-IJKL')
        self.assertTrue(result)
        
        # Check that the backup code was marked as used
        mock_cursor.execute.assert_any_call("""
                UPDATE mfa_backup_codes 
                SET is_used = TRUE, used_at = NOW() 
                WHERE id = %s
            """, (123,))

if __name__ == '__main__':
    unittest.main() 