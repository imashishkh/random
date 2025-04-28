"""
Secure Withdrawal Processing System for BEP20 tokens

This module implements a secure withdrawal system with multi-signature support,
verification mechanisms, and transaction monitoring for the Binance Smart Chain.
It provides functionality to create withdrawal requests, approve/reject requests,
and process transactions with proper security measures.
"""
import os
import json
import logging
import uuid
from typing import Dict, List, Optional, Union, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal

from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
import time

from .models import Wallet, WalletType
from .wallet import (
    get_web3, decrypt_private_key, get_wallet_by_id, get_wallet_balances,
    is_valid_bep20_address, get_token_balance, get_bnb_balance,
    BSC_MAINNET_CHAIN_ID, BSC_TESTNET_CHAIN_ID, BEP20_ABI
)
from ..db import connection as db

# Setup logging
logger = logging.getLogger(__name__)

# Withdrawal status constants
class WithdrawalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


# Global withdrawal configuration
# These should be loaded from environment variables in production
DEFAULT_GAS_LIMIT = 21000  # Default gas limit for BNB transfers
TOKEN_GAS_LIMIT = 65000    # Default gas limit for token transfers
MAX_WITHDRAWAL_AMOUNT = Decimal(os.getenv("MAX_WITHDRAWAL_AMOUNT", "100"))  # Maximum amount per withdrawal
MIN_CONFIRMATIONS = int(os.getenv("MIN_WITHDRAWAL_CONFIRMATIONS", "12"))    # Minimum block confirmations
WITHDRAWAL_COOLDOWN = int(os.getenv("WITHDRAWAL_COOLDOWN_MINUTES", "30"))   # Cooldown between withdrawals in minutes
REQUIRED_APPROVALS = int(os.getenv("REQUIRED_WITHDRAWAL_APPROVALS", "2"))   # Number of approvals required


def create_withdrawal_request(
    user_id: str,
    wallet_id: int,
    to_address: str,
    amount: Union[Decimal, float, str],
    token_address: Optional[str] = None,
    chain_id: int = BSC_MAINNET_CHAIN_ID
) -> int:
    """
    Create a new withdrawal request.
    
    Args:
        user_id: ID of the user creating the request
        wallet_id: ID of the wallet to withdraw from
        to_address: Destination address
        amount: Amount to withdraw
        token_address: Token contract address (None for BNB)
        chain_id: Chain ID
    
    Returns:
        ID of the created withdrawal request
    
    Raises:
        ValueError: If the request couldn't be created
    """
    # Convert amount to Decimal
    if isinstance(amount, float) or isinstance(amount, str):
        amount = Decimal(str(amount))
    
    # Validate wallet
    wallet = get_wallet_by_id(wallet_id)
    if not wallet:
        raise ValueError(f"Wallet with ID {wallet_id} not found")
    
    # Validate owner
    if wallet.user_id != user_id:
        raise ValueError("Not authorized to withdraw from this wallet")
    
    # Validate destination address
    if not is_valid_bep20_address(to_address):
        raise ValueError(f"Invalid destination address: {to_address}")
    
    # Check chain ID
    if wallet.chain_id != chain_id:
        raise ValueError(f"Chain ID mismatch: wallet is on chain {wallet.chain_id}")
    
    # Check for withdrawal cooldown
    cooldown_check_query = """
    SELECT id FROM withdrawal_requests
    WHERE wallet_id = %s AND created_at > NOW() - INTERVAL %s MINUTE
    AND status NOT IN ('rejected', 'failed')
    LIMIT 1
    """
    
    cooldown_requests = db.execute_query(
        cooldown_check_query, 
        (wallet_id, WITHDRAWAL_COOLDOWN)
    )
    
    if cooldown_requests:
        raise ValueError(
            f"Withdrawal cooldown period active. Please wait {WITHDRAWAL_COOLDOWN} minutes between withdrawals."
        )
    
    # Determine token symbol for record keeping
    token_symbol = "BNB"
    if token_address:
        try:
            web3 = get_web3(chain_id)
            token_contract = web3.eth.contract(address=token_address, abi=BEP20_ABI)
            token_symbol = token_contract.functions.symbol().call()
        except Exception as e:
            logger.error(f"Error getting token symbol: {e}")
            token_symbol = "UNKNOWN"
    
    # Check available balance
    balances = get_wallet_balances(wallet_id)
    available_balance = Decimal(str(balances.get(token_symbol, 0)))
    
    if amount > available_balance:
        raise ValueError(
            f"Insufficient balance. Available: {available_balance} {token_symbol}, Requested: {amount} {token_symbol}"
        )
    
    # Check maximum withdrawal limit
    if amount > MAX_WITHDRAWAL_AMOUNT:
        raise ValueError(
            f"Amount exceeds maximum withdrawal limit of {MAX_WITHDRAWAL_AMOUNT} {token_symbol}"
        )
    
    # Create withdrawal request
    request_data = {
        "wallet_id": wallet_id,
        "to_address": to_address,
        "token_address": token_address,
        "amount": str(amount),  # Store as string to preserve decimal precision
        "status": WithdrawalStatus.PENDING,
        "created_by": user_id
    }
    
    query = """
    INSERT INTO withdrawal_requests
    (wallet_id, to_address, token_address, amount, status, created_by)
    VALUES (%(wallet_id)s, %(to_address)s, %(token_address)s, %(amount)s, %(status)s, %(created_by)s)
    RETURNING id
    """
    
    try:
        with db.get_db_cursor() as cursor:
            cursor.execute(query, request_data)
            request_id = cursor.fetchone()[0]
            
        logger.info(
            f"Created withdrawal request {request_id} for {amount} {token_symbol} "
            f"from wallet {wallet_id} to {to_address}"
        )
        return request_id
    except Exception as e:
        logger.error(f"Error creating withdrawal request: {e}")
        raise ValueError(f"Failed to create withdrawal request: {str(e)}")


def get_withdrawal_request(request_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a withdrawal request by ID.
    
    Args:
        request_id: The withdrawal request ID
    
    Returns:
        Withdrawal request data or None if not found
    """
    query = """
    SELECT wr.*, w.address as wallet_address, w.wallet_type, w.user_id
    FROM withdrawal_requests wr
    JOIN wallets w ON wr.wallet_id = w.id
    WHERE wr.id = %s
    """
    
    results = db.execute_query(query, (request_id,))
    if not results:
        return None
    
    return results[0]


def get_user_withdrawal_requests(user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Get withdrawal requests for a user.
    
    Args:
        user_id: The user ID
        limit: Maximum number of requests to return
        offset: Offset for pagination
    
    Returns:
        List of withdrawal requests
    """
    query = """
    SELECT wr.*, w.address as wallet_address, w.wallet_type
    FROM withdrawal_requests wr
    JOIN wallets w ON wr.wallet_id = w.id
    WHERE w.user_id = %s
    ORDER BY wr.created_at DESC
    LIMIT %s OFFSET %s
    """
    
    results = db.execute_query(query, (user_id, limit, offset))
    return results


def get_pending_withdrawal_requests(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get pending withdrawal requests that need approval.
    
    Args:
        limit: Maximum number of requests to return
    
    Returns:
        List of pending withdrawal requests
    """
    query = """
    SELECT wr.*, w.address as wallet_address, w.wallet_type, w.user_id
    FROM withdrawal_requests wr
    JOIN wallets w ON wr.wallet_id = w.id
    WHERE wr.status = %s
    ORDER BY wr.created_at ASC
    LIMIT %s
    """
    
    results = db.execute_query(query, (WithdrawalStatus.PENDING, limit))
    return results


def approve_withdrawal_request(
    request_id: int, 
    approver_address: str, 
    private_key: Optional[str] = None
) -> bool:
    """
    Approve a withdrawal request.
    
    Args:
        request_id: The withdrawal request ID
        approver_address: The address of the approver
        private_key: Private key for signing (required for automated processes)
    
    Returns:
        True if successfully approved
    
    Raises:
        ValueError: If the request couldn't be approved
    """
    # Get withdrawal request
    request = get_withdrawal_request(request_id)
    if not request:
        raise ValueError(f"Withdrawal request {request_id} not found")
    
    # Check status
    if request['status'] != WithdrawalStatus.PENDING:
        raise ValueError(f"Cannot approve request with status {request['status']}")
    
    # Check for duplicate approval
    check_query = """
    SELECT id FROM withdrawal_approvals
    WHERE request_id = %s AND approver_address = %s
    """
    
    existing_approval = db.execute_query(check_query, (request_id, approver_address))
    if existing_approval:
        raise ValueError("You have already approved or rejected this request")
    
    # Get wallet to check if it's a multisig
    wallet_id = request['wallet_id']
    wallet_type = request['wallet_type']
    
    # For multisig wallets, verify that approver is a valid signer
    if wallet_type == WalletType.MULTISIG:
        # Check if approver is a valid signer for this multisig
        check_signer_query = """
        SELECT ms.id
        FROM multisig_wallets mw
        JOIN multisig_signers ms ON mw.id = ms.multisig_id
        WHERE mw.wallet_id = %s AND ms.signer_address = %s
        """
        
        signer_check = db.execute_query(check_signer_query, (wallet_id, approver_address))
        if not signer_check:
            raise ValueError(f"Address {approver_address} is not a valid signer for this multisig wallet")
    
    # Create signature if private key provided
    signature = None
    if private_key:
        try:
            # Create message hash from request details
            # This would normally use proper EIP-712 typed data signing
            message = (
                f"withdrawal:{request_id}:{request['wallet_id']}:{request['to_address']}:"
                f"{request['amount']}:{request['token_address'] or 'BNB'}"
            )
            web3 = get_web3(request['chain_id'])
            message_hash = web3.keccak(text=message)
            
            # Sign message
            account = Account.from_key(private_key)
            signed = web3.eth.account.sign_message(
                message_hash,
                private_key=private_key
            )
            signature = web3.to_hex(signed.signature)
            
            # Verify signature matches approver address
            if account.address.lower() != approver_address.lower():
                raise ValueError("Private key does not match approver address")
            
        except Exception as e:
            logger.error(f"Error signing withdrawal request: {e}")
            raise ValueError(f"Failed to sign withdrawal request: {str(e)}")
    
    # Record approval
    approval_data = {
        "request_id": request_id,
        "approver_address": approver_address,
        "approved": True,
        "signature": signature
    }
    
    query = """
    INSERT INTO withdrawal_approvals
    (request_id, approver_address, approved, signature)
    VALUES (%(request_id)s, %(approver_address)s, %(approved)s, %(signature)s)
    RETURNING id
    """
    
    try:
        with db.get_db_cursor() as cursor:
            cursor.execute(query, approval_data)
            approval_id = cursor.fetchone()[0]
        
        logger.info(f"Recorded approval {approval_id} for withdrawal request {request_id}")
        
        # Check if we have enough approvals to execute the withdrawal
        check_approvals_query = """
        SELECT COUNT(*) as approval_count
        FROM withdrawal_approvals
        WHERE request_id = %s AND approved = TRUE
        """
        
        approval_count_result = db.execute_query(check_approvals_query, (request_id,))
        approval_count = approval_count_result[0]['approval_count']
        
        # For multisig wallets, check threshold
        threshold = REQUIRED_APPROVALS
        if wallet_type == WalletType.MULTISIG:
            threshold_query = """
            SELECT threshold
            FROM multisig_wallets
            WHERE wallet_id = %s
            """
            
            threshold_result = db.execute_query(threshold_query, (wallet_id,))
            if threshold_result:
                threshold = threshold_result[0]['threshold']
        
        # If we have enough approvals, update status to approved
        if approval_count >= threshold:
            update_query = """
            UPDATE withdrawal_requests
            SET status = %s, updated_at = NOW()
            WHERE id = %s
            """
            
            with db.get_db_cursor() as cursor:
                cursor.execute(update_query, (WithdrawalStatus.APPROVED, request_id))
            
            logger.info(f"Withdrawal request {request_id} approved with {approval_count} approvals")
        
        return True
    
    except Exception as e:
        logger.error(f"Error approving withdrawal request: {e}")
        raise ValueError(f"Failed to approve withdrawal request: {str(e)}")


def reject_withdrawal_request(request_id: int, approver_address: str, reason: str = "") -> bool:
    """
    Reject a withdrawal request.
    
    Args:
        request_id: The withdrawal request ID
        approver_address: The address of the rejector
        reason: Optional reason for rejection
    
    Returns:
        True if successfully rejected
    
    Raises:
        ValueError: If the request couldn't be rejected
    """
    # Get withdrawal request
    request = get_withdrawal_request(request_id)
    if not request:
        raise ValueError(f"Withdrawal request {request_id} not found")
    
    # Check status
    if request['status'] != WithdrawalStatus.PENDING:
        raise ValueError(f"Cannot reject request with status {request['status']}")
    
    # Check for duplicate action
    check_query = """
    SELECT id FROM withdrawal_approvals
    WHERE request_id = %s AND approver_address = %s
    """
    
    existing_approval = db.execute_query(check_query, (request_id, approver_address))
    if existing_approval:
        raise ValueError("You have already approved or rejected this request")
    
    # Get wallet to check if it's a multisig
    wallet_id = request['wallet_id']
    wallet_type = request['wallet_type']
    
    # For multisig wallets, verify that rejector is a valid signer
    if wallet_type == WalletType.MULTISIG:
        # Check if rejector is a valid signer for this multisig
        check_signer_query = """
        SELECT ms.id
        FROM multisig_wallets mw
        JOIN multisig_signers ms ON mw.id = ms.multisig_id
        WHERE mw.wallet_id = %s AND ms.signer_address = %s
        """
        
        signer_check = db.execute_query(check_signer_query, (wallet_id, approver_address))
        if not signer_check:
            raise ValueError(f"Address {approver_address} is not a valid signer for this multisig wallet")
    
    # Record rejection
    rejection_data = {
        "request_id": request_id,
        "approver_address": approver_address,
        "approved": False,
        "signature": reason  # Store reason in signature field
    }
    
    query = """
    INSERT INTO withdrawal_approvals
    (request_id, approver_address, approved, signature)
    VALUES (%(request_id)s, %(approver_address)s, %(approved)s, %(signature)s)
    RETURNING id
    """
    
    try:
        with db.get_db_cursor() as cursor:
            cursor.execute(query, rejection_data)
            rejection_id = cursor.fetchone()[0]
        
        # Update withdrawal request status to rejected
        update_query = """
        UPDATE withdrawal_requests
        SET status = %s, updated_at = NOW()
        WHERE id = %s
        """
        
        with db.get_db_cursor() as cursor:
            cursor.execute(update_query, (WithdrawalStatus.REJECTED, request_id))
        
        logger.info(f"Withdrawal request {request_id} rejected by {approver_address}: {reason}")
        return True
    
    except Exception as e:
        logger.error(f"Error rejecting withdrawal request: {e}")
        raise ValueError(f"Failed to reject withdrawal request: {str(e)}")


def process_approved_withdrawals(password: str, batch_size: int = 5) -> List[Dict[str, Any]]:
    """
    Process approved withdrawal requests.
    
    Args:
        password: Password to decrypt wallet private keys
        batch_size: Maximum number of withdrawals to process in one batch
    
    Returns:
        List of processed withdrawal results
    
    Raises:
        ValueError: If processing fails
    """
    # Get approved withdrawal requests
    query = """
    SELECT wr.*, w.address as wallet_address, w.encrypted_private_key, w.chain_id
    FROM withdrawal_requests wr
    JOIN wallets w ON wr.wallet_id = w.id
    WHERE wr.status = %s AND w.wallet_type = %s
    ORDER BY wr.created_at ASC
    LIMIT %s
    """
    
    withdrawals = db.execute_query(
        query, 
        (WithdrawalStatus.APPROVED, WalletType.HOT, batch_size)
    )
    
    results = []
    
    for withdrawal in withdrawals:
        result = {
            "request_id": withdrawal["id"],
            "status": "pending",
            "tx_hash": None,
            "error": None
        }
        
        try:
            # Process this withdrawal
            tx_hash = _execute_withdrawal(withdrawal, password)
            
            # Update status in database
            update_query = """
            UPDATE withdrawal_requests
            SET status = %s, updated_at = NOW()
            WHERE id = %s
            """
            
            with db.get_db_cursor() as cursor:
                cursor.execute(update_query, (WithdrawalStatus.COMPLETED, withdrawal["id"]))
            
            result["status"] = "completed"
            result["tx_hash"] = tx_hash
            logger.info(f"Successfully processed withdrawal {withdrawal['id']}, tx hash: {tx_hash}")
            
        except Exception as e:
            logger.error(f"Error processing withdrawal {withdrawal['id']}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            
            # Update status to failed
            update_query = """
            UPDATE withdrawal_requests
            SET status = %s, updated_at = NOW()
            WHERE id = %s
            """
            
            with db.get_db_cursor() as cursor:
                cursor.execute(update_query, (WithdrawalStatus.FAILED, withdrawal["id"]))
        
        results.append(result)
    
    return results


def _execute_withdrawal(withdrawal: Dict[str, Any], password: str) -> str:
    """
    Execute a single withdrawal transaction.
    
    Args:
        withdrawal: Withdrawal request data
        password: Password to decrypt the private key
    
    Returns:
        Transaction hash
    
    Raises:
        ValueError: If the withdrawal couldn't be executed
    """
    wallet_address = withdrawal["wallet_address"]
    to_address = withdrawal["to_address"]
    amount = Decimal(withdrawal["amount"])
    token_address = withdrawal["token_address"]
    chain_id = withdrawal["chain_id"]
    encrypted_private_key = withdrawal["encrypted_private_key"]
    
    if not encrypted_private_key:
        raise ValueError("No private key available for this wallet")
    
    try:
        # Decrypt private key
        private_key = decrypt_private_key(encrypted_private_key, password)
        
        # Get web3 instance
        web3 = get_web3(chain_id)
        
        # Create account from private key
        account = Account.from_key(private_key)
        
        # Verify the account address matches the wallet address
        if account.address.lower() != wallet_address.lower():
            raise ValueError("Decrypted private key does not match wallet address")
        
        # Check balance one more time before sending
        if token_address:
            # Token transfer
            current_balance = get_token_balance(wallet_address, token_address, chain_id)
            if Decimal(str(current_balance)) < amount:
                raise ValueError(f"Insufficient token balance: {current_balance} < {amount}")
            
            # Get gas price and nonce
            gas_price = web3.eth.gas_price
            nonce = web3.eth.get_transaction_count(wallet_address)
            
            # Create token contract instance
            token_contract = web3.eth.contract(address=token_address, abi=BEP20_ABI)
            
            # Get token decimals
            decimals = token_contract.functions.decimals().call()
            
            # Convert amount to token units
            token_amount = int(amount * (10 ** decimals))
            
            # Build transaction
            tx = token_contract.functions.transfer(
                to_address,
                token_amount
            ).build_transaction({
                'chainId': chain_id,
                'gas': TOKEN_GAS_LIMIT,
                'gasPrice': gas_price,
                'nonce': nonce,
            })
            
        else:
            # BNB transfer
            current_balance = get_bnb_balance(wallet_address, chain_id)
            if Decimal(str(current_balance)) < amount:
                raise ValueError(f"Insufficient BNB balance: {current_balance} < {amount}")
            
            # Get gas price and nonce
            gas_price = web3.eth.gas_price
            nonce = web3.eth.get_transaction_count(wallet_address)
            
            # Calculate gas cost
            gas_cost = web3.from_wei(gas_price * DEFAULT_GAS_LIMIT, 'ether')
            
            # Ensure we have enough for gas
            if Decimal(str(current_balance)) < (amount + Decimal(str(gas_cost))):
                raise ValueError(
                    f"Insufficient BNB balance for amount + gas: {current_balance} < {amount + Decimal(str(gas_cost))}"
                )
            
            # Convert amount to wei
            amount_wei = web3.to_wei(amount, 'ether')
            
            # Build transaction
            tx = {
                'to': to_address,
                'value': amount_wei,
                'gas': DEFAULT_GAS_LIMIT,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': chain_id
            }
        
        # Sign transaction
        signed_tx = web3.eth.account.sign_transaction(tx, private_key=private_key)
        
        # Send transaction
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for transaction receipt with timeout
        tx_receipt = None
        timeout = 60  # seconds
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                tx_receipt = web3.eth.get_transaction_receipt(tx_hash)
                if tx_receipt is not None:
                    break
            except Exception:
                pass
            time.sleep(2)
        
        if tx_receipt is None:
            logger.warning(f"Transaction sent but receipt not available within timeout: {tx_hash.hex()}")
            return tx_hash.hex()
        
        # Check status
        if tx_receipt.status != 1:
            raise ValueError(f"Transaction failed: {tx_hash.hex()}")
        
        # Record transaction in wallet_transactions table
        transaction_data = {
            "wallet_id": withdrawal["wallet_id"],
            "transaction_hash": tx_hash.hex(),
            "from_address": wallet_address,
            "to_address": to_address,
            "token_address": token_address,
            "amount": str(amount),
            "gas_used": tx_receipt.gasUsed,
            "gas_price": str(web3.from_wei(gas_price, 'gwei')),
            "block_number": tx_receipt.blockNumber,
            "status": True,
            "nonce": nonce
        }
        
        query = """
        INSERT INTO wallet_transactions
        (wallet_id, transaction_hash, from_address, to_address, token_address, 
         amount, gas_used, gas_price, block_number, status, nonce)
        VALUES (%(wallet_id)s, %(transaction_hash)s, %(from_address)s, %(to_address)s, 
                %(token_address)s, %(amount)s, %(gas_used)s, %(gas_price)s, 
                %(block_number)s, %(status)s, %(nonce)s)
        """
        
        with db.get_db_cursor() as cursor:
            cursor.execute(query, transaction_data)
        
        # Update wallet balance
        if token_address:
            balance = get_token_balance(wallet_address, token_address, chain_id)
            token_contract = web3.eth.contract(address=token_address, abi=BEP20_ABI)
            token_symbol = token_contract.functions.symbol().call()
            
            balance_query = """
            UPDATE wallet_balances
            SET balance = %s, last_updated = NOW()
            WHERE wallet_id = %s AND token_address = %s
            """
            
            with db.get_db_cursor() as cursor:
                cursor.execute(balance_query, (balance, withdrawal["wallet_id"], token_address))
        else:
            balance = get_bnb_balance(wallet_address, chain_id)
            
            balance_query = """
            UPDATE wallet_balances
            SET balance = %s, last_updated = NOW()
            WHERE wallet_id = %s AND token_address IS NULL
            """
            
            with db.get_db_cursor() as cursor:
                cursor.execute(balance_query, (balance, withdrawal["wallet_id"]))
        
        return tx_hash.hex()
    
    except Exception as e:
        logger.error(f"Error executing withdrawal: {e}")
        raise ValueError(f"Failed to execute withdrawal: {str(e)}") 