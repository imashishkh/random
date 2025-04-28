"""
Tests for the cryptographic utilities used in the secret management system.

These tests verify the correct behavior of the encryption/decryption
utilities and key management functions.
"""

import unittest
import json
import base64
from cryptography.exceptions import InvalidTag

from src.security.secrets.crypto import (
    generate_key,
    derive_key_from_password,
    encrypt_data,
    decrypt_data,
    encrypt_json,
    decrypt_json,
    secure_compare,
    encrypt_key,
    decrypt_key
)


class TestCryptoUtils(unittest.TestCase):
    """Test suite for cryptographic utilities."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Generate test keys
        self.test_key = generate_key()
        self.test_data = "This is some secret test data."
        self.test_json = {
            "api_key": "test_api_key_12345",
            "api_secret": "test_api_secret_67890",
            "permissions": ["read", "trade"]
        }
    
    def test_generate_key(self):
        """Test that generate_key produces keys of the expected length."""
        key = generate_key()
        self.assertEqual(len(key), 32)  # AES-256 key length
        
        # Generate another key to ensure they're different
        key2 = generate_key()
        self.assertNotEqual(key, key2)
    
    def test_derive_key_from_password(self):
        """Test deriving encryption keys from passwords."""
        password = "secure-password-123"
        
        # Test with auto-generated salt
        key1, salt1 = derive_key_from_password(password)
        self.assertEqual(len(key1), 32)
        self.assertEqual(len(salt1), 16)
        
        # Test with provided salt
        key2, salt2 = derive_key_from_password(password, salt1)
        self.assertEqual(salt1, salt2)
        self.assertEqual(key1, key2)
        
        # Test with different password
        key3, _ = derive_key_from_password("different-password", salt1)
        self.assertNotEqual(key1, key3)
    
    def test_encrypt_decrypt_data_string(self):
        """Test encrypting and decrypting string data."""
        # Encrypt
        ciphertext, nonce, tag = encrypt_data(self.test_key, self.test_data)
        
        # Verify ciphertext is not the same as plaintext
        self.assertNotEqual(ciphertext, self.test_data.encode('utf-8'))
        
        # Decrypt
        plaintext = decrypt_data(self.test_key, ciphertext, nonce, tag)
        
        # Verify decryption worked
        self.assertEqual(plaintext.decode('utf-8'), self.test_data)
    
    def test_encrypt_decrypt_data_bytes(self):
        """Test encrypting and decrypting bytes."""
        test_bytes = b'\x01\x02\x03\x04\x05'
        
        # Encrypt
        ciphertext, nonce, tag = encrypt_data(self.test_key, test_bytes)
        
        # Verify ciphertext is not the same as plaintext
        self.assertNotEqual(ciphertext, test_bytes)
        
        # Decrypt
        plaintext = decrypt_data(self.test_key, ciphertext, nonce, tag)
        
        # Verify decryption worked
        self.assertEqual(plaintext, test_bytes)
    
    def test_encrypt_decrypt_json(self):
        """Test encrypting and decrypting JSON data."""
        # Encrypt
        ciphertext, nonce, tag = encrypt_json(self.test_key, self.test_json)
        
        # Decrypt
        decrypted_json = decrypt_json(self.test_key, ciphertext, nonce, tag)
        
        # Verify decryption worked
        self.assertEqual(decrypted_json, self.test_json)
    
    def test_tampered_data_detection(self):
        """Test that tampered ciphertext is detected."""
        # Encrypt
        ciphertext, nonce, tag = encrypt_data(self.test_key, self.test_data)
        
        # Tamper with the ciphertext
        if len(ciphertext) > 0:
            tampered_ciphertext = bytearray(ciphertext)
            tampered_ciphertext[0] ^= 0xFF  # Flip all bits in the first byte
            tampered_ciphertext = bytes(tampered_ciphertext)
        else:
            tampered_ciphertext = b'\x01'
        
        # Decryption should fail
        with self.assertRaises(InvalidTag):
            decrypt_data(self.test_key, tampered_ciphertext, nonce, tag)
    
    def test_incorrect_key_detection(self):
        """Test that using the wrong key is detected."""
        # Encrypt with the original key
        ciphertext, nonce, tag = encrypt_data(self.test_key, self.test_data)
        
        # Create a different key
        wrong_key = generate_key()
        
        # Decryption with wrong key should fail
        with self.assertRaises(InvalidTag):
            decrypt_data(wrong_key, ciphertext, nonce, tag)
    
    def test_secure_compare(self):
        """Test secure comparison of byte strings."""
        # Same strings should compare equal
        a = b'test string'
        b = b'test string'
        self.assertTrue(secure_compare(a, b))
        
        # Different strings should compare not equal
        c = b'different'
        self.assertFalse(secure_compare(a, c))
    
    def test_envelope_encryption(self):
        """Test the envelope encryption pattern with master and data keys."""
        # Create a master key (KEK) and data key (DEK)
        master_key = generate_key()
        data_key = generate_key()
        
        # Encrypt the DEK with the KEK
        encrypted_key, key_nonce, key_tag = encrypt_key(master_key, data_key)
        
        # Decrypt the DEK with the KEK
        decrypted_key = decrypt_key(master_key, encrypted_key, key_nonce, key_tag)
        
        # Verify the decrypted key matches the original
        self.assertEqual(data_key, decrypted_key)
        
        # Now use the data key for actual data encryption
        ciphertext, nonce, tag = encrypt_data(data_key, self.test_data)
        
        # Verify decryption works with the recovered DEK
        plaintext = decrypt_data(decrypted_key, ciphertext, nonce, tag)
        self.assertEqual(plaintext.decode('utf-8'), self.test_data)


if __name__ == "__main__":
    unittest.main() 