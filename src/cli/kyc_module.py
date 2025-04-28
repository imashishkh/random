"""
KYC information collection module for Forex Trading Bot CLI Wizard.

This module handles the collection and validation of KYC information
needed for Binance sub-account creation.
"""

import re
import datetime
from typing import Dict, Any, List, Tuple, Optional, Callable
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.text import Text

# ISO-3166 country codes (subset for common countries)
ISO_COUNTRIES = {
    "US": "United States",
    "CA": "Canada",
    "GB": "United Kingdom",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "JP": "Japan",
    "CN": "China",
    "IN": "India",
    "SG": "Singapore",
    "HK": "Hong Kong",
    "CH": "Switzerland",
    "NZ": "New Zealand",
    "RU": "Russia",
    "BR": "Brazil",
    "ZA": "South Africa",
    "AE": "United Arab Emirates",
    # More countries would be included in a full implementation
}


@dataclass
class KYCField:
    """Configuration for a KYC field with validation logic."""
    name: str
    display_name: str
    description: str
    prompt: str
    validator: Callable[[str], str]
    sensitive: bool = False
    examples: List[str] = field(default_factory=list)
    required: bool = True
    
    def get_prompt_text(self) -> str:
        """Generate the full prompt text with examples if available."""
        base_prompt = f"[step]{self.display_name}[/step] ({self.description})"
        if self.examples:
            examples_text = f" [dim]Example: {', '.join(self.examples)}[/dim]"
            return base_prompt + examples_text
        return base_prompt


class KYCCollector:
    """Handles the collection and validation of KYC information."""
    
    def __init__(self, console: Console, state: Any):
        self.console = console
        self.state = state
        self.fields = self._define_kyc_fields()
        self.completed_fields = set()
        
    def _define_kyc_fields(self) -> Dict[str, KYCField]:
        """Define all KYC fields with their validation logic."""
        return {
            "full_name": KYCField(
                name="full_name",
                display_name="Full Name",
                description="as it appears on your ID",
                prompt="Enter your full name",
                validator=self.validate_name,
                examples=["John A. Smith"]
            ),
            "email": KYCField(
                name="email",
                display_name="Email Address",
                description="you will receive verification at this address",
                prompt="Enter your email address",
                validator=self.validate_email,
                examples=["john.smith@example.com"]
            ),
            "date_of_birth": KYCField(
                name="date_of_birth",
                display_name="Date of Birth",
                description="YYYY-MM-DD format",
                prompt="Enter your date of birth",
                validator=self.validate_date,
                sensitive=True,
                examples=["1990-01-31"]
            ),
            "country_code": KYCField(
                name="country_code",
                display_name="Country Code",
                description="ISO 2-letter code",
                prompt="Enter your country code",
                validator=self.validate_country_code,
                examples=["US", "CA", "GB"]
            ),
            "address_line1": KYCField(
                name="address_line1",
                display_name="Address Line 1",
                description="street address",
                prompt="Enter your street address",
                validator=self.validate_address,
                examples=["123 Main St"]
            ),
            "city": KYCField(
                name="city",
                display_name="City",
                description="city/town name",
                prompt="Enter your city",
                validator=self.validate_city,
                examples=["New York"]
            ),
            "postal_code": KYCField(
                name="postal_code",
                display_name="Postal Code",
                description="ZIP/postal code",
                prompt="Enter your postal/ZIP code",
                validator=self.validate_postal_code,
                examples=["10001"]
            ),
            "phone": KYCField(
                name="phone",
                display_name="Phone Number",
                description="including country code",
                prompt="Enter your phone number",
                validator=self.validate_phone,
                examples=["+1 555-123-4567"]
            ),
        }
    
    # Validation methods
    def validate_name(self, name: str) -> str:
        """
        Validate a full name.
        
        Rules:
        - At least 2 characters
        - Contains at least one space (first and last name)
        - No numbers or special characters except hyphen, apostrophe, and period
        - No more than 100 characters
        """
        name = name.strip()
        
        if not name:
            raise ValueError("Name cannot be empty")
            
        if len(name) < 2:
            raise ValueError("Name must be at least 2 characters long")
            
        if len(name) > 100:
            raise ValueError("Name is too long (maximum 100 characters)")
            
        # Check for at least first and last name
        if ' ' not in name:
            raise ValueError("Please provide both first and last name")
            
        # Check for invalid characters
        if not re.match(r"^[A-Za-z\s\-\'\.]+$", name):
            raise ValueError("Name contains invalid characters. Only letters, spaces, hyphens (-), apostrophes ('), and periods (.) are allowed")
            
        # Capitalize each part of the name
        parts = name.split()
        return ' '.join(part.capitalize() for part in parts)
    
    def validate_email(self, email: str) -> str:
        """
        Validate an email address with comprehensive checks.
        
        Rules:
        - Standard email format
        - Checks for TLD validity
        - Prevents common typos
        """
        email = email.strip().lower()
        
        if not email:
            raise ValueError("Email cannot be empty")
            
        # Comprehensive email regex
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_regex, email):
            raise ValueError("Invalid email format")
            
        # Check for common typos in domain
        common_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
        domain = email.split('@')[-1]
        
        for common_domain in common_domains:
            # Check for close matches like 'gmial.com' instead of 'gmail.com'
            if domain != common_domain and self._levenshtein_distance(domain, common_domain) == 1:
                self.console.print(f"[warning]Warning: Did you mean '{email.split('@')[0]}@{common_domain}'?[/warning]")
                if Confirm.ask("Correct this typo?"):
                    email = f"{email.split('@')[0]}@{common_domain}"
        
        return email
    
    def validate_date(self, date_str: str) -> str:
        """
        Validate a date string with comprehensive checks.
        
        Rules:
        - YYYY-MM-DD format
        - Date must be valid
        - Person must be 18-100 years old
        """
        date_str = date_str.strip()
        
        if not date_str:
            raise ValueError("Date cannot be empty")
            
        # Check format
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            raise ValueError("Date must be in YYYY-MM-DD format (e.g., 1990-01-31)")
        
        try:
            # Parse the date
            year, month, day = map(int, date_str.split('-'))
            date_obj = datetime.date(year, month, day)
            
            # Check if date is valid
            today = datetime.date.today()
            
            # Calculate age
            age = today.year - date_obj.year - ((today.month, today.day) < (date_obj.month, date_obj.day))
            
            # Check if person is at least 18 years old
            if age < 18:
                raise ValueError("You must be at least 18 years old to use this service")
                
            # Check if person is less than 100 years old
            if age > 100:
                raise ValueError("Please double-check your birth date")
                
            return date_str
        
        except ValueError as e:
            # Check if this is our custom error
            if str(e) in ["You must be at least 18 years old to use this service", 
                          "Please double-check your birth date"]:
                raise
            else:
                raise ValueError(f"Invalid date: {date_str}. Please enter a valid date in YYYY-MM-DD format")
    
    def validate_country_code(self, country_code: str) -> str:
        """
        Validate an ISO-3166 country code.
        
        Rules:
        - Must be a valid 2-letter ISO country code
        - Case insensitive
        """
        country_code = country_code.strip().upper()
        
        if not country_code:
            raise ValueError("Country code cannot be empty")
            
        if len(country_code) != 2:
            raise ValueError("Country code must be a 2-letter code (e.g., US, CA, GB)")
            
        if country_code not in ISO_COUNTRIES:
            raise ValueError(f"Invalid country code: {country_code}. Please enter a valid ISO country code")
            
        # Show the full country name
        self.console.print(f"[info]Selected: {ISO_COUNTRIES[country_code]}[/info]")
        
        return country_code
    
    def validate_address(self, address: str) -> str:
        """
        Validate a street address.
        
        Rules:
        - At least 5 characters
        - No more than 100 characters
        - Basic sanity check for address format
        """
        address = address.strip()
        
        if not address:
            raise ValueError("Address cannot be empty")
            
        if len(address) < 5:
            raise ValueError("Address is too short (minimum 5 characters)")
            
        if len(address) > 100:
            raise ValueError("Address is too long (maximum 100 characters)")
            
        # Basic check for numeric component (most addresses have at least one number)
        if not any(char.isdigit() for char in address):
            self.console.print("[warning]Warning: Address doesn't appear to contain a number. Is this correct?[/warning]")
            if not Confirm.ask("Confirm this address?"):
                raise ValueError("Please enter a valid street address")
        
        return address
    
    def validate_city(self, city: str) -> str:
        """
        Validate a city name.
        
        Rules:
        - At least 2 characters
        - No more than 50 characters
        - Letters, spaces, hyphens only
        """
        city = city.strip()
        
        if not city:
            raise ValueError("City cannot be empty")
            
        if len(city) < 2:
            raise ValueError("City name is too short (minimum 2 characters)")
            
        if len(city) > 50:
            raise ValueError("City name is too long (maximum 50 characters)")
            
        # Check for invalid characters
        if not re.match(r"^[A-Za-z\s\-\'\.]+$", city):
            raise ValueError("City contains invalid characters. Only letters, spaces, hyphens (-), apostrophes ('), and periods (.) are allowed")
        
        # Title case the city name
        return city.title()
    
    def validate_postal_code(self, postal_code: str) -> str:
        """
        Validate a postal/ZIP code based on the country.
        
        Rules:
        - Format validation based on country
        - Default to basic sanity check if country format unknown
        """
        postal_code = postal_code.strip().upper()
        
        if not postal_code:
            raise ValueError("Postal code cannot be empty")
            
        # Get the country code from state
        country_code = self.state.get("country_code")
        
        # Country-specific validation
        if country_code == "US":
            # US ZIP code: 5 digits, or 5+4
            if not re.match(r"^\d{5}(-\d{4})?$", postal_code):
                raise ValueError("Invalid US ZIP code. Format should be 5 digits (e.g., 10001) or ZIP+4 (e.g., 10001-1234)")
        elif country_code == "CA":
            # Canadian postal code: A1A 1A1
            if not re.match(r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$", postal_code):
                raise ValueError("Invalid Canadian postal code. Format should be A1A 1A1")
            # Format with a space
            if len(postal_code) == 6:
                postal_code = f"{postal_code[:3]} {postal_code[3:]}"
        elif country_code == "GB":
            # UK postcode
            if not re.match(r"^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$", postal_code):
                raise ValueError("Invalid UK postcode")
        else:
            # Generic validation for other countries
            if len(postal_code) < 3:
                raise ValueError("Postal code is too short")
            if len(postal_code) > 12:
                raise ValueError("Postal code is too long")
        
        return postal_code
    
    def validate_phone(self, phone: str) -> str:
        """
        Validate an international phone number.
        
        Rules:
        - Must include country code with + prefix
        - Only digits, spaces, and designated separators
        - Appropriate length check
        """
        # Clean the input of common formatting characters
        original_phone = phone
        phone = re.sub(r'[\s\-\(\)]', '', phone.strip())
        
        if not phone:
            raise ValueError("Phone number cannot be empty")
            
        # Must start with + for international format
        if not phone.startswith('+'):
            raise ValueError("Phone number must include country code with + prefix (e.g., +1 for US)")
            
        # Remove the + for further validation
        phone_digits = phone[1:]
        
        # Check if all remaining characters are digits
        if not phone_digits.isdigit():
            raise ValueError("Phone number must contain only digits, spaces, and separators")
            
        # Length check (international numbers are typically 7-15 digits)
        if len(phone_digits) < 7:
            raise ValueError("Phone number is too short")
            
        if len(phone_digits) > 15:
            raise ValueError("Phone number is too long")
            
        # Format the phone number consistently
        formatted_phone = f"+{phone_digits[:1]} "
        
        # Add formatting based on country
        country_code = self.state.get("country_code")
        if country_code == "US" or country_code == "CA":
            # Format as +1 XXX-XXX-XXXX
            if len(phone_digits) == 11 and phone_digits.startswith('1'):
                formatted_phone = f"+{phone_digits[0]} {phone_digits[1:4]}-{phone_digits[4:7]}-{phone_digits[7:]}"
            else:
                # Just use cleaned version with + if we can't recognize format
                formatted_phone = f"+{phone_digits}"
        else:
            # Use cleaned version with +
            formatted_phone = f"+{phone_digits}"
        
        return formatted_phone
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate the Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
            
        if len(s2) == 0:
            return len(s1)
            
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
            
        return previous_row[-1]
    
    def collect_kyc_information(self) -> bool:
        """
        Collect all required KYC information from the user.
        
        Returns:
            bool: True if KYC information was successfully collected, False if user cancelled
        """
        # Display introduction panel
        self.console.print(Panel(
            "[bold]KYC Information Collection[/bold]\n\n"
            "We need to collect detailed Know Your Customer (KYC) information "
            "for Binance sub-account creation and compliance purposes.\n\n"
            "This information will be handled securely and only shared with Binance "
            "for regulatory compliance.",
            title="KYC Information",
            expand=False
        ))
        
        # Initialize progress bar
        total_fields = len(self.fields)
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console
        ) as progress:
            # Create the progress bar
            task = progress.add_task("[cyan]Completing KYC information...", total=total_fields)
            
            # Collect each field in sequence
            field_names = list(self.fields.keys())
            field_idx = 0
            
            while field_idx < len(field_names):
                field_name = field_names[field_idx]
                field = self.fields[field_name]
                
                # Update progress bar description
                progress.update(task, description=f"[cyan]Field: {field.display_name}[/cyan]")
                
                # Check if field already has a value (for resuming or editing)
                current_value = self.state.get(field_name)
                
                # Always allow editing even if there's a current value
                if current_value:
                    self.console.print(f"Current {field.display_name}: {current_value}")
                    if not Confirm.ask(f"Would you like to change this?"):
                        # Skip to next field if user doesn't want to change
                        self.completed_fields.add(field_name)
                        progress.update(task, advance=1)
                        field_idx += 1
                        continue
                
                # Collect the field value
                success = self._collect_field(field)
                
                # Give option to cancel after each field
                if not success:
                    if Confirm.ask("Would you like to cancel KYC information collection?"):
                        return False
                    # If not cancelling, try this field again
                    continue
                
                # Mark field as completed and update progress
                self.completed_fields.add(field_name)
                progress.update(task, advance=1)
                
                # Option to go back to previous field
                if field_idx > 0:  # Not the first field
                    if Confirm.ask("Would you like to go back to the previous field?"):
                        # Remove current field from completed set
                        self.completed_fields.remove(field_name)
                        # Go back to previous field
                        field_idx -= 1
                        # Update progress
                        progress.update(task, completed=len(self.completed_fields))
                        continue
                
                # Move to next field
                field_idx += 1
        
        # Show KYC information summary for final review
        return self._show_kyc_summary()
    
    def _collect_field(self, field: KYCField) -> bool:
        """
        Collect a single KYC field from the user.
        
        Args:
            field: The KYC field configuration
            
        Returns:
            bool: True if field was successfully collected, False if user cancelled
        """
        # Display field information and examples
        self.console.print(f"\n[bold]{field.display_name}[/bold]: {field.description}")
        
        if field.examples:
            examples_text = ", ".join(field.examples)
            self.console.print(f"[dim]Examples: {examples_text}[/dim]")
        
        # Get the input with validation
        try:
            value = self._prompt_with_validation(field)
            # Store the value in state
            self.state.update(field.name, value, sensitive=field.sensitive)
            return True
        except KeyboardInterrupt:
            self.console.print("\n[warning]Input cancelled[/warning]")
            return False
    
    def _prompt_with_validation(self, field: KYCField) -> str:
        """Prompt user with validation and error handling."""
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                value = Prompt.ask(field.get_prompt_text(), password=field.sensitive)
                validated_value = field.validator(value)
                return validated_value
            except ValueError as e:
                self.console.print(f"[error]Error: {str(e)}[/error]")
                attempts += 1
                if attempts >= max_attempts:
                    self.console.print("[warning]Maximum attempts reached. Please try again later.[/warning]")
                    raise KeyboardInterrupt
        
        # Should not reach here, but just in case
        raise KeyboardInterrupt
    
    def _show_kyc_summary(self) -> bool:
        """
        Show a summary of the collected KYC information for confirmation.
        
        Returns:
            bool: True if user confirms the information, False otherwise
        """
        self.console.print("\n[bold]Please review your KYC information:[/bold]")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Field")
        table.add_column("Value")
        
        # Add each field to the table
        for field_name, field in self.fields.items():
            value = self.state.get(field_name, "")
            
            if field.sensitive and value:
                # Mask sensitive data
                if isinstance(value, str):
                    # Show only first and last character, mask the rest
                    if len(value) > 2:
                        masked_value = f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
                    else:
                        masked_value = "****"
                else:
                    masked_value = "****"
                
                table.add_row(field.display_name, masked_value)
            else:
                table.add_row(field.display_name, str(value))
        
        self.console.print(table)
        
        # Confirm the information
        if Confirm.ask("[bold]Is this information correct?[/bold]"):
            self.console.print("[success]KYC information confirmed![/success]")
            return True
        else:
            # Offer to edit specific fields
            self.console.print("[info]Let's edit the information.[/info]")
            return self._edit_kyc_information()
    
    def _edit_kyc_information(self) -> bool:
        """
        Allow editing of specific KYC fields.
        
        Returns:
            bool: True if editing was completed successfully, False if user cancelled
        """
        while True:
            # Create a table of fields to edit
            table = Table(show_header=True, header_style="bold")
            table.add_column("#")
            table.add_column("Field")
            
            # Add each field to the table with index
            for i, (field_name, field) in enumerate(self.fields.items(), 1):
                table.add_row(str(i), field.display_name)
            
            self.console.print("\n[bold]Which field would you like to edit?[/bold]")
            self.console.print(table)
            self.console.print("[dim]Enter 0 to finish editing and confirm all information[/dim]")
            
            # Get field number
            try:
                choice = int(Prompt.ask("Enter field number"))
                
                if choice == 0:
                    # Show final summary
                    return self._show_kyc_summary()
                
                if 1 <= choice <= len(self.fields):
                    # Get the field to edit
                    field_name = list(self.fields.keys())[choice - 1]
                    field = self.fields[field_name]
                    
                    # Collect the field
                    self._collect_field(field)
                else:
                    self.console.print("[error]Invalid choice. Please enter a valid field number.[/error]")
            except ValueError:
                self.console.print("[error]Please enter a number.[/error]")
            except KeyboardInterrupt:
                if Confirm.ask("[bold]Cancel editing?[/bold]"):
                    return False 