"""
Forex Trading Bot CLI Wizard Command

This module implements the 'botctl wizard' command for interactive KYC, 
Binance sub-account creation, and API key generation.
"""

import os
import json
import time
import click
import re
import random
import string
from typing import Dict, Any, Optional, List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.theme import Theme
from rich.table import Table
from rich.markdown import Markdown

# Import the Secret Manager from the security module
from ..security.secrets import create_secret_manager, ManagerType
from ..utils.config_manager import ConfigManager
# Import the KYC module
from .kyc_module import KYCCollector

# Initialize custom theme for consistent styling
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red",
    "success": "bold green",
    "header": "bold blue",
    "step": "bold cyan",
})

# Initialize Rich console with custom theme
console = Console(theme=custom_theme)

# Get config manager instance
config_manager = ConfigManager.get_instance()

# Create a wizard state object to track the progress
class WizardState:
    """Stores the state of the wizard and handles persistence."""
    
    def __init__(self):
        self.data = {}
        self.current_step = 0
        self.total_steps = 5
        self.session_id = int(time.time())
        self.sensitive_keys = set()
    
    def update(self, key: str, value: Any, sensitive: bool = False) -> None:
        """Update the wizard state with a new key/value pair."""
        self.data[key] = value
        if sensitive:
            self.sensitive_keys.add(key)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the wizard state."""
        return self.data.get(key, default)
    
    def advance_step(self) -> None:
        """Advance to the next step."""
        self.current_step += 1
    
    def go_back(self) -> None:
        """Go back to the previous step."""
        if self.current_step > 0:
            self.current_step -= 1
    
    def get_progress(self) -> Tuple[int, int]:
        """Get current progress as (current_step, total_steps)."""
        return (self.current_step, self.total_steps)
    
    def get_safe_data(self) -> Dict[str, Any]:
        """Get a copy of the data with sensitive fields masked."""
        safe_data = {}
        for key, value in self.data.items():
            if key in self.sensitive_keys and value:
                # Mask sensitive data
                if isinstance(value, str):
                    if len(value) > 4:
                        # Show only last 4 chars of secrets
                        safe_data[key] = f"{'*' * (len(value) - 4)}{value[-4:]}"
                    else:
                        safe_data[key] = "****"
                else:
                    safe_data[key] = "****"
            else:
                safe_data[key] = value
        return safe_data


# Define helper functions for the UI
def display_header(state: WizardState) -> None:
    """Display a consistent header showing the current progress."""
    current, total = state.get_progress()
    header_text = f"Trading Bot Setup Wizard - Step {current+1}/{total}"
    console.print(Panel(header_text, style="header"))


def create_spinner(description: str = "Processing"):
    """Create a consistent spinner for async operations."""
    return Progress(
        SpinnerColumn(), 
        TextColumn(f"[info]{description}[/info]"),
        transient=True
    )


def display_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[error]Error: {message}[/error]")


def display_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[success]{message}[/success]")


def prompt_with_validation(
    prompt_text: str, 
    validator_func: callable, 
    password: bool = False
) -> str:
    """Prompt user with validation and error handling."""
    while True:
        try:
            value = Prompt.ask(prompt_text, password=password)
            validated_value = validator_func(value)
            return validated_value
        except ValueError as e:
            display_error(str(e))


# Validation functions for KYC information
def validate_name(name: str) -> str:
    """Validate a name field."""
    if not name or len(name.strip()) < 2:
        raise ValueError("Name must be at least 2 characters long")
    return name.strip()

def validate_email(email: str) -> str:
    """Validate an email address."""
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise ValueError("Invalid email format")
    return email.strip()

def validate_date(date: str) -> str:
    """Validate a date in YYYY-MM-DD format."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError("Date must be in YYYY-MM-DD format")
    try:
        year, month, day = date.split('-')
        year, month, day = int(year), int(month), int(day)
        if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
            raise ValueError("Invalid date values")
    except Exception:
        raise ValueError("Invalid date format or values")
    return date

def validate_country(country: str) -> str:
    """Validate a country name."""
    if not country or len(country.strip()) < 2:
        raise ValueError("Country name must be at least 2 characters long")
    return country.strip()

def validate_phone(phone: str) -> str:
    """Validate a phone number."""
    # Remove common phone number formatting characters
    clean_phone = re.sub(r'[\s\-\(\)\+]', '', phone)
    
    # Check if remaining characters are digits
    if not clean_phone.isdigit():
        raise ValueError("Phone number must contain only digits, spaces, +, -, and ()")
    
    # Check length
    if len(clean_phone) < 8 or len(clean_phone) > 15:
        raise ValueError("Phone number must be between 8 and 15 digits")
    
    return clean_phone


# Binance API integration

class BinanceAPIClient:
    """Simple client for Binance API interactions."""
    
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.api_client = None
        
        if not test_mode:
            # Import here to avoid circular imports
            from src.exchange.binance_api_client import BinanceApiClient
            
            # Get API credentials from environment or config
            api_key = os.environ.get('BINANCE_API_KEY')
            api_secret = os.environ.get('BINANCE_API_SECRET')
            
            # Check if we have the required credentials
            if not api_key or not api_secret:
                raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET environment variables are required")
            
            # Initialize the main API client
            self.api_client = BinanceApiClient(
                api_key=api_key,
                api_secret=api_secret,
                testnet=False,  # Always use production for account creation
                enable_rate_limit=True,
                max_retries=3
            )
    
    def create_subaccount(self, 
                         email: str, 
                         name: str,
                         country: str,
                         phone: str,
                         dob: str
                         ) -> Dict[str, Any]:
        """
        Create a Binance sub-account using the API.
        
        Args:
            email: Sub-account email address
            name: Name for the sub-account
            country: Country code
            phone: Phone number
            dob: Date of birth
            
        Returns:
            Dictionary containing the API response
        """
        if self.test_mode:
            # Simulate API response in test mode
            time.sleep(2)  # Simulate API latency
            sub_account_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            return {
                "success": True,
                "subAccountId": f"sa-{sub_account_id}",
                "email": email,
                "status": "ACTIVE",
                "activated": True,
                "createTime": int(time.time() * 1000)
            }
        else:
            # Format the name to ensure it meets Binance requirements
            # Typically, this should be alphanumeric and may have max length restrictions
            formatted_name = f"{name.replace(' ', '_')}_{int(time.time())}"
            
            try:
                # Use the API client we initialized to call the Binance API
                result = self.api_client.create_virtual_subaccount(
                    subaccount_name=formatted_name,
                    email=email
                )
                
                # Process the result to match our expected format
                # Note: Actual Binance response format may differ and require mapping
                return {
                    "success": True,
                    "subAccountId": result.get("subAccountId", ""),
                    "email": email,
                    "status": result.get("status", "ACTIVE"),
                    "activated": True,
                    "createTime": result.get("createTime", int(time.time() * 1000))
                }
            except Exception as e:
                # Log the error details
                console.print(f"[error]Error details: {str(e)}[/error]")
                # Re-raise with a user-friendly message
                raise Exception(f"Failed to create Binance sub-account: {str(e)}")

    def generate_api_key(self, 
                        sub_account_id: str, 
                        label: str,
                        permissions: List[str],
                        ip_restrict: bool = False,
                        restrict_ips: List[str] = None,
                        key_type: str = "Ed25519"
                        ) -> Dict[str, Any]:
        """
        Generate API keys for a Binance sub-account.
        
        Args:
            sub_account_id: The sub-account ID
            label: Label for the API key
            permissions: List of permissions to enable
            ip_restrict: Whether to restrict IPs
            restrict_ips: List of IPs to allow if ip_restrict is True
            key_type: Type of API key to generate (Ed25519, HMAC, or RSA)
            
        Returns:
            Dictionary containing the API response with key and secret
        """
        if self.test_mode:
            # Simulate API response in test mode
            time.sleep(1.5)  # Simulate API latency
            api_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
            api_secret = ''.join(random.choices(string.ascii_lowercase + string.digits + string.ascii_uppercase, k=32))
            return {
                "success": True,
                "apiKey": api_key,
                "secretKey": api_secret,
                "permissions": permissions,
                "restrictIPs": ip_restrict,
                "allowedIPs": restrict_ips if ip_restrict else [],
                "keyType": key_type,
                "created": int(time.time() * 1000)
            }
        else:
            try:
                # Use our API client to generate keys
                ip_restrictions = None
                if ip_restrict and restrict_ips:
                    ip_restrictions = ",".join(restrict_ips)
                
                result = self.api_client.create_subaccount_api_key(
                    subaccount_id=sub_account_id,
                    label=label,
                    permissions=permissions,
                    ip_restrict=ip_restrict,
                    ip_list=ip_restrictions,
                    key_type=key_type
                )
                
                # Process the result to match our expected format
                return {
                    "success": True,
                    "apiKey": result.get("apiKey", ""),
                    "secretKey": result.get("secretKey", ""),
                    "permissions": permissions,
                    "restrictIPs": result.get("isRestricted", ip_restrict),
                    "allowedIPs": result.get("allowedIPs", restrict_ips if ip_restrict else []),
                    "keyType": result.get("keyType", key_type),
                    "created": result.get("createTime", int(time.time() * 1000))
                }
            except Exception as e:
                # Log the error details
                console.print(f"[error]Error details: {str(e)}[/error]")
                # Re-raise with a user-friendly message
                raise Exception(f"Failed to generate API keys: {str(e)}")


# Secret storage utilities

def store_credentials(state: WizardState) -> Dict[str, Any]:
    """
    Store credentials in the secret manager.
    
    Args:
        state: The wizard state containing credentials
        
    Returns:
        Dictionary with status and message
    """
    try:
        # Create an instance of the secret manager
        # Use keyring for desktop or KMS for cloud
        test_mode = state.get("test_mode", False)
        if test_mode:
            # In test mode, use a mock secret manager
            return {
                "success": True,
                "message": "Credentials stored successfully (test mode)"
            }
        
        # Initialize the secret manager
        secret_manager = create_secret_manager(ManagerType.KEYRING)
        
        # Store API credentials
        if state.get("api_key") and state.get("api_secret"):
            secret_manager.store("binance_api_key", state.get("api_key"))
            secret_manager.store("binance_api_secret", state.get("api_secret"))
        
        # Store sub-account information
        if state.get("binance_subaccount_id"):
            secret_manager.store("binance_subaccount_id", state.get("binance_subaccount_id"))
        
        # Store additional metadata as non-sensitive information in config
        config = {
            "trading": {
                "binance": {
                    "account_email": state.get("email"),
                    "account_created": int(time.time()),
                    "api_permissions": state.get("api_permissions", []),
                    "setup_completed": True
                }
            }
        }
        
        # Update the config
        for section, values in config.items():
            for key, value in values.items():
                config_manager.set(f"{section}.{key}", value)
        
        config_manager.save()
        
        return {
            "success": True,
            "message": "Credentials stored successfully in secure storage"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error storing credentials: {str(e)}"
        }


# Define the wizard steps

def welcome_step(state: WizardState) -> Dict[str, Any]:
    """First step: Welcome and introduction."""
    display_header(state)
    
    console.print(Panel(
        "[bold]Welcome to the Forex Trading Bot Setup Wizard![/bold]\n\n"
        "This wizard will guide you through:\n"
        "- KYC information collection\n"
        "- Binance sub-account creation\n"
        "- API key generation\n"
        "- Secure credential storage\n\n"
        "You'll need:\n"
        "- Personal identification information\n"
        "- Access to your email\n"
        "- Binance account (if you already have one)\n",
        title="Welcome",
        expand=False
    ))
    
    # Ask if the user wants to continue
    if not Confirm.ask("[bold]Do you want to continue with the setup?[/bold]"):
        return {"exit": True}
    
    return {"next": True}


def kyc_information_step(state: WizardState) -> Dict[str, Any]:
    """
    Second step: Collect KYC information with enhanced validation and editing capabilities.
    
    This step collects detailed KYC information required for Binance sub-account creation,
    with robust validation and the ability to edit previous inputs.
    """
    display_header(state)
    
    # Create a KYC collector instance
    kyc_collector = KYCCollector(console, state)
    
    # Collect KYC information
    success = kyc_collector.collect_kyc_information()
    
    if not success:
        # User cancelled or had too many failed attempts
        console.print("[warning]KYC information collection was not completed.[/warning]")
        
        # Ask if they want to try again or exit
        if Confirm.ask("[bold]Would you like to try again?[/bold]"):
            return {"back": True}  # Go back to this same step
        else:
            console.print("[info]You can complete the KYC information later.[/info]")
            return {"exit": True}  # Exit the wizard
    
    # KYC information was successfully collected
    display_success("KYC information collected successfully!")
    return {"next": True}


def binance_account_step(state: WizardState) -> Dict[str, Any]:
    """Third step: Create Binance sub-account."""
    display_header(state)
    
    console.print(Panel(
        "[bold]Binance Sub-Account Creation[/bold]\n\n"
        "We'll now create a Binance sub-account for trading. "
        "This account will be linked to your KYC information and "
        "will be used by the trading bot.\n\n"
        "You'll receive an email from Binance to verify the account.",
        title="Binance Account",
        expand=False
    ))
    
    # Get test mode setting
    test_mode = state.get("test_mode", False)
    
    # Check if credentials are available in non-test mode
    if not test_mode:
        has_api_key = os.environ.get('BINANCE_API_KEY') is not None
        has_api_secret = os.environ.get('BINANCE_API_SECRET') is not None
        
        if not (has_api_key and has_api_secret):
            console.print("[warning]Binance API credentials not found in environment.[/warning]")
            console.print("Before creating sub-accounts, you need to configure your Binance master account API keys.")
            console.print("These keys should have permission to create sub-accounts.\n")
            
            if Confirm.ask("[bold]Do you want to skip this step and configure API keys manually later?[/bold]"):
                console.print("[info]You can create the sub-account later manually.[/info]")
                state.update("binance_account_created", False)
                return {"next": True}
            else:
                return {"back": True}
    
    # Initialize Binance client
    try:
        binance_client = BinanceAPIClient(test_mode=test_mode)
    except Exception as e:
        display_error(f"Failed to initialize Binance API client: {str(e)}")
        if Confirm.ask("[bold]Do you want to skip this step and configure Binance integration later?[/bold]"):
            state.update("binance_account_created", False)
            return {"next": True}
        else:
            return {"back": True}
    
    # Check if the user wants to proceed
    if not Confirm.ask("[bold]Do you want to create a Binance sub-account now?[/bold]"):
        console.print("[info]You can create the sub-account later manually.[/info]")
        # Skip this step but mark it as completed
        state.update("binance_account_created", False)
        return {"next": True}
    
    # Verify we have the necessary KYC information
    required_fields = ["email", "full_name", "country", "phone", "date_of_birth"]
    missing_fields = [field for field in required_fields if not state.get(field)]
    
    if missing_fields:
        display_error("Missing required KYC information for sub-account creation.")
        console.print(f"Missing fields: {', '.join(missing_fields)}")
        if Confirm.ask("[bold]Do you want to go back to the KYC step?[/bold]"):
            return {"back": True}
        else:
            console.print("[info]Skipping Binance sub-account creation.[/info]")
            state.update("binance_account_created", False)
            return {"next": True}
    
    # Display spinner while creating the account
    with create_spinner("Creating Binance sub-account...") as progress:
        task = progress.add_task("Creating...", total=None)
        
        # Get KYC information from state
        email = state.get("email")
        name = state.get("full_name")
        country = state.get("country")
        phone = state.get("phone")
        dob = state.get("date_of_birth")
        
        # Set up retry logic
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                # Call Binance API to create sub-account
                response = binance_client.create_subaccount(
                    email=email,
                    name=name,
                    country=country,
                    phone=phone,
                    dob=dob
                )
                
                # Store the sub-account information in state
                state.update("binance_subaccount_id", response["subAccountId"])
                state.update("binance_account_created", True)
                state.update("binance_account_created_time", response["createTime"])
                state.update("binance_account_status", response.get("status", "ACTIVE"))
                
                success = True
                
            except Exception as e:
                retry_count += 1
                error_message = str(e)
                
                # If we're out of retries, display the error and ask what to do
                if retry_count >= max_retries:
                    display_error(f"Failed to create Binance sub-account after {max_retries} attempts.")
                    console.print(f"Last error: {error_message}")
                    
                    # Ask if they want to retry or skip
                    if Confirm.ask("[bold]Do you want to try again?[/bold]"):
                        retry_count = 0  # Reset retry counter for another round
                    else:
                        console.print("[info]Skipping Binance sub-account creation.[/info]")
                        state.update("binance_account_created", False)
                        return {"next": True}
                else:
                    # Wait a bit before retrying (exponential backoff)
                    wait_time = 2 ** retry_count
                    console.print(f"[warning]API call failed. Retrying in {wait_time} seconds...[/warning]")
                    time.sleep(wait_time)
    
    # Display success message
    if success:
        display_success(f"Binance sub-account created successfully!")
        console.print(f"Sub-account ID: [bold]{state.get('binance_subaccount_id')}[/bold]")
        console.print(f"Status: [bold]{state.get('binance_account_status')}[/bold]")
        console.print("\nA verification email has been sent to your address. "
                     "Please verify the account before proceeding to the next step.")
        
        # Ask for verification
        if not Confirm.ask("[bold]Have you verified the account?[/bold]"):
            console.print("[warning]Please verify the account before proceeding.[/warning]")
            if Confirm.ask("[bold]Do you want to proceed anyway?[/bold]"):
                return {"next": True}
            else:
                return {"back": True}
    else:
        # This should rarely happen due to our retry logic, but just in case
        display_error("Failed to create Binance sub-account due to persistent errors.")
        console.print("[info]You can try again later manually.[/info]")
        state.update("binance_account_created", False)
    
    return {"next": True}


def api_key_step(state: WizardState) -> Dict[str, Any]:
    """Fourth step: Generate API keys."""
    display_header(state)
    
    console.print(Panel(
        "[bold]API Key Generation[/bold]\n\n"
        "We'll now generate API keys for the Binance sub-account. "
        "These keys will allow the trading bot to interact with your account.\n\n"
        "We'll set appropriate permissions and security restrictions to ensure "
        "your account remains secure while allowing necessary trading functions.",
        title="API Keys",
        expand=False
    ))
    
    # Check if we have a valid Binance sub-account ID
    subaccount_id = state.get("binance_subaccount_id")
    account_created = state.get("binance_account_created", False)
    test_mode = state.get("test_mode", False)
    
    if not subaccount_id and not test_mode:
        console.print("[warning]No Binance sub-account ID found.[/warning]")
        console.print("You need to create a Binance sub-account first.")
        
        if Confirm.ask("[bold]Do you want to go back to the Binance account step?[/bold]"):
            return {"back": True}
        else:
            console.print("[info]Proceeding without Binance sub-account.[/info]")
            # Create a test account ID for demonstration
            subaccount_id = "demo-account-id"
            state.update("binance_subaccount_id", subaccount_id)
    elif not subaccount_id and test_mode:
        # Generate a test sub-account ID
        subaccount_id = f"sa-{int(time.time())}"
        state.update("binance_subaccount_id", subaccount_id)
    
    # Notify if we're running in test mode
    if test_mode:
        console.print("\n[info]Running in test mode. API keys will be simulated.[/info]")
    
    # Check if credentials are available in non-test mode
    if not test_mode:
        has_api_key = os.environ.get('BINANCE_API_KEY') is not None
        has_api_secret = os.environ.get('BINANCE_API_SECRET') is not None
        
        if not (has_api_key and has_api_secret):
            console.print("[warning]Binance API credentials not found in environment.[/warning]")
            console.print("You need to configure your Binance master account API keys.")
            
            if Confirm.ask("[bold]Do you want to skip API key generation and configure manually later?[/bold]"):
                console.print("[info]Skipping API key generation.[/info]")
                return {"next": True}
            else:
                return {"back": True}
    
    # Display API key type selection
    console.print("\n[bold]Step 1: Select API Key Type[/bold]")
    
    key_types_table = Table(show_header=True, header_style="bold")
    key_types_table.add_column("Key Type")
    key_types_table.add_column("Description")
    key_types_table.add_column("Recommended")
    
    key_types = [
        ("Ed25519", "Modern asymmetric key with improved security and performance", "Yes"),
        ("RSA", "Traditional asymmetric key with strong security", "No"),
        ("HMAC", "Legacy symmetric key type (deprecated)", "No")
    ]
    
    for key_type, desc, recommended in key_types:
        key_types_table.add_row(
            key_type,
            desc,
            f"[{'success' if recommended == 'Yes' else 'info'}]{recommended}[/{'success' if recommended == 'Yes' else 'info'}]"
        )
    
    console.print(key_types_table)
    
    # Create a radio button effect with prompt
    console.print("\n[info]Select an API key type (Ed25519 recommended):[/info]")
    key_type_options = ["Ed25519", "RSA", "HMAC"]
    selected_key_type = Prompt.ask(
        "[step]API Key Type[/step]",
        choices=key_type_options,
        default="Ed25519"
    )
    
    # Set a label for the API key
    console.print("\n[bold]Step 2: Set API Key Label[/bold]")
    console.print("[info]Choose a descriptive label to easily identify this API key.[/info]")
    
    label = "Trading Bot"
    if not test_mode:
        label = Prompt.ask(
            "[step]API Key Label[/step]", 
            default="Trading Bot"
        )
    
    # Validate the label
    if len(label.strip()) < 3:
        display_error("Label must be at least 3 characters long")
        label = Prompt.ask(
            "[step]API Key Label[/step] (minimum 3 characters)", 
            default="Trading Bot"
        )
    
    # Display information about API key permissions
    console.print("\n[bold]Step 3: Set API Key Permissions[/bold]")
    console.print("[info]Select which operations this API key will be allowed to perform.[/info]")
    
    permissions_table = Table(show_header=True, header_style="bold")
    permissions_table.add_column("Permission")
    permissions_table.add_column("Description")
    permissions_table.add_column("Security Risk")
    permissions_table.add_column("Required")
    
    permissions = [
        ("Enable Reading", "Read account information and balances", "Low", "Yes"),
        ("Enable Spot & Margin Trading", "Create and manage spot/margin orders", "Medium", "Yes"),
        ("Enable Futures", "Access futures trading functions", "Medium", "No"),
        ("Enable Withdrawals", "Withdraw funds from your account", "High", "No"),
        ("Enable Internal Transfer", "Transfer between main/sub accounts", "High", "No"),
        ("Portfolio Margin", "Use portfolio margin mode", "Medium", "No"),
    ]
    
    for perm, desc, risk, req in permissions:
        risk_color = "info"
        if risk == "Medium":
            risk_color = "warning"
        elif risk == "High":
            risk_color = "error"
            
        permissions_table.add_row(
            perm,
            desc,
            f"[{risk_color}]{risk}[/{risk_color}]",
            f"[{'success' if req == 'Yes' else 'info'}]{req}[/{'success' if req == 'Yes' else 'info'}]"
        )
    
    console.print(permissions_table)
    
    # List of permission mapping from display name to API permission code
    permission_mapping = {
        "Enable Reading": "READ_INFO",
        "Enable Spot & Margin Trading": "SPOT_TRADING",
        "Enable Futures": "FUTURES_TRADING",
        "Enable Withdrawals": "WITHDRAWALS",
        "Enable Internal Transfer": "INTERNAL_TRANSFER",
        "Portfolio Margin": "PORTFOLIO_MARGIN"
    }
    
    # Default required permissions
    selected_permissions = ["READ_INFO", "SPOT_TRADING"]
    enabled_permissions = ["Enable Reading", "Enable Spot & Margin Trading"]
    
    # Ask for each optional permission
    optional_display_permissions = [
        "Enable Futures", 
        "Portfolio Margin"
    ]
    
    high_risk_permissions = [
        "Enable Withdrawals", 
        "Enable Internal Transfer"
    ]
    
    for perm in optional_display_permissions:
        if Confirm.ask(f"Enable [bold]{perm}[/bold] permission?", default=False):
            api_perm = permission_mapping.get(perm)
            if api_perm:
                selected_permissions.append(api_perm)
                enabled_permissions.append(perm)
    
    # Special handling for high-risk permissions with extra warnings
    for perm in high_risk_permissions:
        if Confirm.ask(f"Enable [bold]{perm}[/bold] permission? [error](HIGH SECURITY RISK)[/error]", default=False):
            console.print(Panel(
                f"[error]SECURITY WARNING[/error]\n\n"
                f"Enabling {perm} gives this API key the ability to move funds out of your account. "
                f"This is a significant security risk and is not recommended unless absolutely necessary.\n\n"
                f"If enabled, you MUST restrict access to specific IP addresses.",
                title="High Risk Permission",
                expand=False
            ))
            
            if Confirm.ask("[bold]Are you absolutely sure you want to enable this high-risk permission?[/bold]", default=False):
                api_perm = permission_mapping.get(perm)
                if api_perm:
                    selected_permissions.append(api_perm)
                    enabled_permissions.append(perm)
    
    # IP restrictions
    console.print("\n[bold]Step 4: Set IP Restrictions[/bold]")
    
    # Determine if IP restrictions should be enforced
    high_risk_enabled = any(perm in enabled_permissions for perm in high_risk_permissions)
    trading_enabled = "Enable Spot & Margin Trading" in enabled_permissions or "Enable Futures" in enabled_permissions
    
    ip_restrict = False
    restrict_ips = []
    
    if high_risk_enabled:
        console.print("[error]IP restriction is REQUIRED for high-risk permissions.[/error]")
        ip_restrict = True
    elif trading_enabled:
        console.print("[warning]IP restriction is RECOMMENDED for trading permissions.[/warning]")
        ip_restrict = Confirm.ask("[bold]Restrict API key to specific IP addresses?[/bold] (Recommended)", default=True)
    else:
        console.print("[info]IP restriction is optional for read-only permissions.[/info]")
        ip_restrict = Confirm.ask("[bold]Restrict API key to specific IP addresses?[/bold]", default=False)
    
    # If IP restriction is enabled, collect IP addresses
    if ip_restrict:
        console.print("\n[info]Enter the IP addresses that should be allowed to use this API key.[/info]")
        console.print("[info]Enter one IP address per line. Press Enter twice when done.[/info]")
        
        # Add current IP by default if we can detect it
        default_ip = ""
        try:
            import requests
            response = requests.get("https://api.ipify.org", timeout=5)
            if response.status_code == 200:
                default_ip = response.text.strip()
                console.print(f"[info]Your current IP address appears to be: {default_ip}[/info]")
        except:
            pass
        
        if default_ip:
            restrict_ips.append(default_ip)
            console.print(f"[info]Added your current IP address: {default_ip}[/info]")
            
        # Allow adding more IPs
        while True:
            ip = Prompt.ask("[step]Enter IP address[/step] (or press Enter to finish)")
            if not ip:
                break
                
            # Basic IP validation
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                if ip not in restrict_ips:
                    restrict_ips.append(ip)
                    console.print(f"[success]Added IP: {ip}[/success]")
                else:
                    console.print(f"[warning]IP {ip} already added[/warning]")
            else:
                console.print(f"[error]Invalid IP format: {ip}[/error]")
        
        # Ensure we have at least one IP if restriction is enabled
        if not restrict_ips:
            console.print("[error]At least one IP address is required when IP restriction is enabled.[/error]")
            default_ip = "127.0.0.1"  # Localhost as fallback
            restrict_ips.append(default_ip)
            console.print(f"[warning]Added localhost ({default_ip}) as fallback. Replace this with your actual IP.[/warning]")
    
    # 2FA Verification
    console.print("\n[bold]Step 5: API Key Creation & Verification[/bold]")
    console.print("[info]Binance requires 2FA and email verification to create API keys.[/info]")
    
    if not test_mode:
        has_2fa_ready = Confirm.ask("[bold]Do you have your 2FA device (authenticator app or phone) ready?[/bold]")
        if not has_2fa_ready:
            console.print("[warning]Please prepare your 2FA device before continuing.[/warning]")
            if not Confirm.ask("[bold]Continue anyway?[/bold]"):
                return {"back": True}
    
    # Confirmation before creating
    console.print("\n[bold]API Key Configuration Summary:[/bold]")
    
    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Setting")
    summary_table.add_column("Value")
    
    summary_table.add_row("Key Type", selected_key_type)
    summary_table.add_row("Label", label)
    summary_table.add_row("Permissions", ", ".join(enabled_permissions))
    summary_table.add_row(
        "IP Restricted", 
        f"[{'success' if ip_restrict else 'warning'}]{str(ip_restrict)}[/{'success' if ip_restrict else 'warning'}]"
    )
    
    if ip_restrict and restrict_ips:
        summary_table.add_row("Allowed IPs", ", ".join(restrict_ips))
    
    console.print(summary_table)
    
    # Final confirmation
    if not Confirm.ask("\n[bold]Create API key with these settings?[/bold]"):
        console.print("[info]API key creation cancelled.[/info]")
        if Confirm.ask("[bold]Do you want to start over?[/bold]"):
            return {"back": True}
        else:
            return {"next": True}
    
    # Create the API key
    try:
        binance_client = BinanceAPIClient(test_mode=test_mode)
    except Exception as e:
        display_error(f"Failed to initialize Binance API client: {str(e)}")
        if Confirm.ask("[bold]Do you want to skip this step and configure Binance integration later?[/bold]"):
            return {"next": True}
        else:
            return {"back": True}
    
    with create_spinner("Generating API keys...") as progress:
        task = progress.add_task("Generating...", total=None)
        
        # Set up retry logic
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                # If not in test mode, handle 2FA verification if needed
                if not test_mode:
                    # Ask for 2FA code here if needed
                    # For now, we'll assume the API handles this or raises appropriate errors
                    pass
                
                # Call Binance API to generate keys
                response = binance_client.generate_api_key(
                    sub_account_id=subaccount_id,
                    label=label,
                    permissions=selected_permissions,
                    ip_restrict=ip_restrict,
                    restrict_ips=restrict_ips,
                    key_type=selected_key_type
                )
                
                # Store the API keys in state
                state.update("api_key", response["apiKey"], sensitive=True)
                state.update("api_secret", response["secretKey"], sensitive=True)
                state.update("api_permissions", response["permissions"])
                state.update("api_key_type", response.get("keyType", selected_key_type))
                state.update("api_created_time", response["created"])
                state.update("api_ip_restricted", response.get("restrictIPs", ip_restrict))
                state.update("api_allowed_ips", response.get("allowedIPs", restrict_ips if ip_restrict else []))
                
                success = True
                
            except Exception as e:
                retry_count += 1
                error_message = str(e)
                
                # If we're out of retries, display the error and ask what to do
                if retry_count >= max_retries:
                    display_error(f"Failed to generate API keys after {max_retries} attempts.")
                    console.print(f"Last error: {error_message}")
                    
                    # Ask if they want to retry or skip
                    if Confirm.ask("[bold]Do you want to try again?[/bold]"):
                        retry_count = 0  # Reset retry counter for another round
                    else:
                        console.print("[info]Skipping API key generation.[/info]")
                        return {"next": True}
                else:
                    # Wait a bit before retrying (exponential backoff)
                    wait_time = 2 ** retry_count
                    console.print(f"[warning]API call failed. Retrying in {wait_time} seconds...[/warning]")
                    time.sleep(wait_time)
    
    # Display the generated keys (if successful)
    if success:
        console.print("\n[bold]API Keys Generated Successfully:[/bold]")
        
        keys_table = Table(show_header=True, header_style="bold")
        keys_table.add_column("Key Type")
        keys_table.add_column("Value")
        keys_table.add_column("Security")
        
        # Get the API key and secret from state
        api_key = state.get("api_key", "")
        api_secret = state.get("api_secret", "")
        
        # Mask the API key partially
        masked_key = api_key
        if len(api_key) > 8:
            masked_key = f"{api_key[:4]}...{api_key[-4:]}"
        
        # Mask the API secret completely by default
        masked_secret = "••••••••••••••••" 
        if api_secret and len(api_secret) > 4:
            masked_secret = f"••••••••{api_secret[-4:]}"
        
        keys_table.add_row(
            "API Key",
            masked_key,
            "[warning]Store securely[/warning]"
        )
        
        keys_table.add_row(
            "API Secret",
            masked_secret,
            "[error]Never share with anyone[/error]"
        )
        
        keys_table.add_row(
            "Key Type",
            selected_key_type,
            "[info]Generated as requested[/info]"
        )
        
        console.print(keys_table)
        
        # Option to reveal full API secret with confirmation
        if Confirm.ask("\n[bold]Do you need to view the full API secret?[/bold] (This is your ONLY chance)", default=False):
            console.print("\n[error]IMPORTANT: This is the ONLY time you will see the full API secret.[/error]")
            console.print("[error]Copy it to a secure location immediately.[/error]\n")
            
            console.print(f"[bold]API Secret:[/bold] {api_secret}")
            
            # Pause for the user to copy the secret
            input("\nPress Enter after you have securely copied the API Secret...")
        
        # Security warning
        console.print("\n[warning]Important Security Warning:[/warning]")
        console.print("These API keys provide access to your Binance account. Please ensure:")
        console.print("1. Never share them with anyone")
        console.print("2. Store them in a secure password manager")
        console.print("3. Enable IP restrictions for maximum security")
        console.print("4. Never commit API keys to code repositories")
        console.print("5. Rotate your keys regularly (every 30-90 days)")
        
        # Confirm they've noted down the keys
        if Confirm.ask("\n[bold]Have you securely stored these keys?[/bold]"):
            display_success("API keys generated and stored successfully.")
        else:
            console.print("[warning]Please store your keys securely before continuing.[/warning]")
    else:
        # This should rarely happen due to our retry logic, but just in case
        display_error("Failed to generate API keys due to persistent errors.")
        console.print("[info]You can generate API keys manually later.[/info]")
    
    return {"next": True}


def credential_storage_step(state: WizardState) -> Dict[str, Any]:
    """Fifth step: Store credentials securely and finalize setup."""
    display_header(state)
    
    console.print(Panel(
        "[bold]Secure Credential Storage[/bold]\n\n"
        "We'll now securely store your API credentials using the "
        "Secret Manager. The credentials will be encrypted at rest "
        "using AES-GCM encryption.\n\n"
        "In addition, we'll update your configuration files with "
        "the necessary non-sensitive settings for the trading bot.",
        title="Final Setup",
        expand=False
    ))
    
    # Check for the presence of credentials
    has_api_credentials = state.get("api_key") and state.get("api_secret")
    has_account_info = state.get("binance_subaccount_id")
    
    if not has_api_credentials and not has_account_info:
        console.print("[warning]No API credentials or account information found.[/warning]")
        console.print("You need to generate API keys before storing credentials.")
        
        if Confirm.ask("[bold]Do you want to go back to the API key step?[/bold]"):
            return {"back": True}
        else:
            console.print("[info]Proceeding without storing credentials.[/info]")
            # Skip credential storage
            return {"next": True}
    
    # Show summary of what will be stored
    console.print("\n[bold]The following credentials will be stored securely:[/bold]")
    
    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Credential")
    summary_table.add_column("Status")
    
    summary_table.add_row(
        "Binance API Key", 
        "[success]Available[/success]" if state.get("api_key") else "[warning]Missing[/warning]"
    )
    summary_table.add_row(
        "Binance API Secret", 
        "[success]Available[/success]" if state.get("api_secret") else "[warning]Missing[/warning]"
    )
    summary_table.add_row(
        "Binance Sub-Account ID", 
        "[success]Available[/success]" if state.get("binance_subaccount_id") else "[warning]Missing[/warning]"
    )
    
    console.print(summary_table)
    
    # Ask for confirmation
    if not Confirm.ask("[bold]Do you want to store these credentials securely?[/bold]"):
        console.print("[info]Skipping credential storage.[/info]")
        return {"next": True}
    
    # Store the credentials
    with create_spinner("Storing credentials securely...") as progress:
        task = progress.add_task("Storing...", total=None)
        
        # Call the store_credentials function
        result = store_credentials(state)
    
    # Display the result
    if result["success"]:
        display_success(result["message"])
    else:
        display_error(result["message"])
        
        # Ask if they want to retry
        if Confirm.ask("[bold]Do you want to retry?[/bold]"):
            return {"back": True}
        
    # Setup complete
    console.print(Panel(
        "[bold]Setup Complete![/bold]\n\n"
        "Your Forex Trading Bot has been successfully configured with the necessary "
        "credentials and settings.\n\n"
        "You can now use the following commands:\n"
        "- `botctl start` - Start the trading bot\n"
        "- `botctl status` - Check the bot status\n"
        "- `botctl stop` - Stop the trading bot\n"
        "- `botctl help` - View all available commands\n\n"
        "For more information, refer to the documentation at:\n"
        "https://forextrading.example.com/docs",
        title="Congratulations!",
        border_style="green"
    ))
    
    return {"next": True}


# Main wizard command
@click.command(name="wizard")
@click.option("--test", is_flag=True, help="Run in test mode with simulated API responses")
def wizard_command(test: bool):
    """
    Interactive wizard for KYC, Binance sub-account creation, and API key generation.
    
    This wizard will guide you through the setup process for the Forex Trading Bot,
    including collecting KYC information, creating a Binance sub-account, generating
    API keys with appropriate permissions, and securely storing your credentials.
    """
    try:
        # Initialize the wizard state
        state = WizardState()
        
        # Set test mode if specified
        state.update("test_mode", test)
        
        # Initialize state machine for wizard flow
        steps = [
            welcome_step,
            kyc_information_step,
            binance_account_step,
            api_key_step,
            credential_storage_step
        ]
        
        # Execute steps in sequence
        current_step = 0
        while current_step < len(steps):
            # Execute the current step
            result = steps[current_step](state)
            
            # Handle step result
            if result.get("exit"):
                console.print("[info]Wizard exited.[/info]")
                break
            elif result.get("back") and current_step > 0:
                current_step -= 1
                state.go_back()
            else:
                current_step += 1
                state.advance_step()
        
        if current_step == len(steps):
            console.print("\n[info]Thank you for using the Forex Trading Bot Setup Wizard![/info]")
    
    except KeyboardInterrupt:
        console.print("\n[info]Wizard cancelled by user.[/info]")
    except Exception as e:
        console.print(f"[error]An unexpected error occurred: {str(e)}[/error]")


# Function to register the command with the CLI
def register_commands(cli):
    """Register wizard command with the CLI."""
    cli.add_command(wizard_command) 