/**
 * Common JavaScript functionality for the Forex Trading Platform
 */

// Execute when DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
  // Initialize tooltips
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });
  
  // Initialize popovers
  const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
  popoverTriggerList.map(function (popoverTriggerEl) {
    return new bootstrap.Popover(popoverTriggerEl);
  });
  
  // Active navigation highlighting
  highlightCurrentNavItem();
});

/**
 * Highlights the current navigation item based on the current URL path
 */
function highlightCurrentNavItem() {
  const currentPath = window.location.pathname;
  const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
  
  navLinks.forEach(link => {
    // Remove active class from all links
    link.classList.remove('active');
    
    // Get the href attribute
    const href = link.getAttribute('href');
    
    // Skip placeholder links
    if (href === '#') return;
    
    // Check if the current path starts with the link's href
    if (currentPath === href || 
        (href !== '/' && currentPath.startsWith(href))) {
      link.classList.add('active');
    } else if (href === '/' && currentPath === '/') {
      link.classList.add('active');
    }
  });
}

/**
 * Shows a notification to the user
 * @param {string} message - The message to display
 * @param {string} type - The type of alert: 'success', 'danger', 'warning', 'info'
 * @param {number} duration - Time in milliseconds to show the alert (default: 5000)
 */
function showNotification(message, type = 'info', duration = 5000) {
  // Create alert element
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${type} alert-dismissible fade show alert-animated fixed-top w-75 mx-auto mt-3`;
  alertDiv.setAttribute('role', 'alert');
  alertDiv.style.zIndex = '9999';
  
  // Add message
  alertDiv.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  `;
  
  // Append to body
  document.body.appendChild(alertDiv);
  
  // Create Bootstrap alert instance
  const alert = new bootstrap.Alert(alertDiv);
  
  // Auto dismiss after duration
  if (duration > 0) {
    setTimeout(() => {
      alert.close();
    }, duration);
  }
  
  // Remove from DOM after animation completes
  alertDiv.addEventListener('closed.bs.alert', function () {
    alertDiv.remove();
  });
}

/**
 * Formats a number as currency
 * @param {number} amount - The amount to format
 * @param {string} currency - The currency code (default: 'USD')
 * @returns {string} - Formatted currency string
 */
function formatCurrency(amount, currency = 'USD') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency
  }).format(amount);
}

/**
 * Formats a date string or object
 * @param {string|Date} date - The date to format
 * @param {boolean} includeTime - Whether to include time (default: true)
 * @returns {string} - Formatted date string
 */
function formatDate(date, includeTime = true) {
  if (typeof date === 'string') {
    date = new Date(date);
  }
  
  const options = {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  };
  
  if (includeTime) {
    options.hour = '2-digit';
    options.minute = '2-digit';
  }
  
  return date.toLocaleDateString('en-US', options);
} 