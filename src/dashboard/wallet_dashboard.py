import logging
from typing import Dict, List, Any, Optional
from ..services.wallet import WalletService
from .widgets.wallet_widgets import (
    WalletOverviewWidget,
    TransactionHistoryWidget,
    FundAllocationWidget,
    BalanceHistoryWidget,
    AlertsWidget,
    WalletActionsWidget
)

logger = logging.getLogger(__name__)

class WalletDashboard:
    """Dashboard for displaying wallet information and management."""
    
    def __init__(self):
        """Initialize the wallet dashboard."""
        self.wallet_service = WalletService()
        self.active_wallet_id = None
        
        # Initialize all widgets
        self.overview_widget = WalletOverviewWidget()
        self.transaction_widget = TransactionHistoryWidget()
        self.allocation_widget = FundAllocationWidget()
        self.history_widget = BalanceHistoryWidget()
        self.alerts_widget = AlertsWidget()
        self.actions_widget = WalletActionsWidget()
        
        # Set the active wallet if available
        active_wallet = self.wallet_service.get_active_wallet()
        if active_wallet:
            self.active_wallet_id = active_wallet.get("id")
            self.update_widgets(active_wallet.get("id"))
    
    def update_widgets(self, wallet_id: str) -> None:
        """Update all widgets with data for the specified wallet.
        
        Args:
            wallet_id: ID of the wallet to display
        """
        logger.debug(f"Updating dashboard widgets for wallet ID: {wallet_id}")
        self.active_wallet_id = wallet_id
        
        # Get wallet data
        wallet = self.wallet_service.get_wallet(wallet_id)
        if not wallet:
            logger.error(f"Could not find wallet with ID: {wallet_id}")
            return
        
        # Update each widget with relevant data
        try:
            # Overview widget needs all wallets and active wallet
            self.overview_widget.update({
                "active_wallet": wallet,
                "wallets": self.wallet_service.get_wallets()
            })
            
            # Transaction history widget
            self.transaction_widget.update(
                self.wallet_service.get_transactions(wallet_id)
            )
            
            # Fund allocation widget
            self.allocation_widget.update(
                self.wallet_service.get_allocation(wallet_id)
            )
            
            # Balance history widget
            self.history_widget.update(
                self.wallet_service.get_balance_history(wallet_id)
            )
            
            # Alerts widget
            self.alerts_widget.update(
                self.wallet_service.get_alerts(wallet_id)
            )
            
            # Actions widget needs wallet data
            self.actions_widget.update(wallet)
            
            logger.debug(f"Successfully updated all widgets for wallet ID: {wallet_id}")
        except Exception as e:
            logger.error(f"Error updating widgets: {str(e)}")
    
    def switch_wallet(self, wallet_id: str) -> bool:
        """Switch to a different wallet.
        
        Args:
            wallet_id: ID of the wallet to switch to
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Switching to wallet ID: {wallet_id}")
        
        try:
            # Update the active wallet in the service
            if self.wallet_service.set_active_wallet(wallet_id):
                # Update widgets with new wallet data
                self.update_widgets(wallet_id)
                return True
            else:
                logger.error(f"Failed to set active wallet: {wallet_id}")
                return False
        except Exception as e:
            logger.error(f"Error switching wallet: {str(e)}")
            return False
    
    def render(self) -> str:
        """Render the wallet dashboard.
        
        Returns:
            HTML representation of the dashboard
        """
        if not self.active_wallet_id:
            return """
            <div class="wallet-dashboard">
                <div class="dashboard-message">
                    <h2>No wallet selected</h2>
                    <p>Please select a wallet to view its details</p>
                </div>
            </div>
            """
        
        # Render each widget
        overview_html = self.overview_widget.render()
        transactions_html = self.transaction_widget.render()
        allocation_html = self.allocation_widget.render()
        history_html = self.history_widget.render()
        alerts_html = self.alerts_widget.render()
        actions_html = self.actions_widget.render()
        
        # Assemble dashboard layout
        return f"""
        <div class="wallet-dashboard">
            <div class="dashboard-row">
                <div class="dashboard-col dashboard-col-left">
                    {overview_html}
                    {actions_html}
                </div>
                <div class="dashboard-col dashboard-col-right">
                    {alerts_html}
                </div>
            </div>
            
            <div class="dashboard-row">
                <div class="dashboard-col dashboard-col-full">
                    {history_html}
                </div>
            </div>
            
            <div class="dashboard-row">
                <div class="dashboard-col dashboard-col-left">
                    {transactions_html}
                </div>
                <div class="dashboard-col dashboard-col-right">
                    {allocation_html}
                </div>
            </div>
        </div>
        """
    
    def process_action(self, action: str, params: Dict[str, Any]) -> bool:
        """Process a wallet action.
        
        Args:
            action: Type of action to perform (deposit, withdraw, transfer)
            params: Parameters for the action
            
        Returns:
            True if successful, False otherwise
        """
        if not self.active_wallet_id:
            logger.error("No active wallet selected")
            return False
        
        wallet_id = params.get("wallet_id", self.active_wallet_id)
        
        try:
            if action == "deposit":
                # Process deposit
                amount = params.get("amount")
                description = params.get("description", "Deposit")
                
                # Add transaction through the wallet service
                self.wallet_service.add_transaction(
                    wallet_id=wallet_id,
                    transaction_type="deposit",
                    amount=amount,
                    description=description
                )
                
                # Update widgets after action
                self.update_widgets(wallet_id)
                return True
                
            elif action == "withdraw":
                # Process withdrawal
                amount = params.get("amount")
                description = params.get("description", "Withdrawal")
                
                # Add transaction through the wallet service
                self.wallet_service.add_transaction(
                    wallet_id=wallet_id,
                    transaction_type="withdraw",
                    amount=amount,
                    description=description
                )
                
                # Update widgets after action
                self.update_widgets(wallet_id)
                return True
                
            elif action == "transfer":
                # Process transfer
                amount = params.get("amount")
                target_wallet_id = params.get("target_wallet_id")
                description = params.get("description", "Transfer")
                
                if not target_wallet_id:
                    logger.error("No target wallet specified for transfer")
                    return False
                
                # Add withdrawal transaction from source wallet
                self.wallet_service.add_transaction(
                    wallet_id=wallet_id,
                    transaction_type="withdraw",
                    amount=amount,
                    description=f"Transfer to {target_wallet_id}: {description}"
                )
                
                # Add deposit transaction to target wallet
                self.wallet_service.add_transaction(
                    wallet_id=target_wallet_id,
                    transaction_type="deposit",
                    amount=amount,
                    description=f"Transfer from {wallet_id}: {description}"
                )
                
                # Update widgets after action
                self.update_widgets(wallet_id)
                return True
                
            else:
                logger.error(f"Unknown wallet action: {action}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing action {action}: {str(e)}")
            return False 