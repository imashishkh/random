# Unified Exchange Adapter Architecture

## Overview

The Unified Exchange Adapter is designed to provide a consistent interface for interacting with various cryptocurrency exchanges through different transport methods (REST and WebSocket). This architecture enables code reuse, consistent error handling, and uniform authentication and rate limiting across transport types.

## Core Components

### 1. Class Diagram

```mermaid
classDiagram
    class BaseTransport {
        <<abstract>>
        +authenticate()
        +handle_error(error)
        +apply_rate_limiting()
        +execute_request(request)
        +close()
    }
    
    class RestTransport {
        -session: Session
        +execute_request(request)
        +close()
    }
    
    class WebSocketTransport {
        -connection: Connection
        -message_handlers: Map
        +connect()
        +subscribe(channel, handler)
        +unsubscribe(channel)
        +send_message(message)
        +close()
    }
    
    class AuthProvider {
        -credentials_manager
        +get_credentials(exchange)
        +sign_request(request, credentials)
        +refresh_credentials(exchange)
        +validate_credentials(credentials)
    }
    
    class RateLimiter {
        -limits_by_endpoint: Map
        -global_limits: List
        -request_history: Queue
        +check_limit(endpoint)
        +register_request(endpoint, weight)
        +update_limits(response_headers)
        +get_delay_time(endpoint)
    }
    
    class ErrorHandler {
        +normalize_error(transport_error)
        +is_retriable(error)
        +get_retry_delay(error)
        +handle_circuit_breaking(error)
    }
    
    class ExchangeClient {
        -transports: Map
        +get_transport(type)
        +create_request(params)
        +execute_market_operation(operation, params)
    }
    
    BaseTransport <|-- RestTransport
    BaseTransport <|-- WebSocketTransport
    BaseTransport --> AuthProvider
    BaseTransport --> RateLimiter
    BaseTransport --> ErrorHandler
    ExchangeClient --> BaseTransport
```

### 2. Sequence Diagram - REST Request Flow

```mermaid
sequenceDiagram
    participant C as Client Code
    participant EC as ExchangeClient
    participant RT as RestTransport
    participant AP as AuthProvider
    participant RL as RateLimiter
    participant EH as ErrorHandler
    
    C->>EC: execute_market_operation(buy, params)
    EC->>EC: create_request(params)
    EC->>RT: execute_request(request)
    RT->>RL: check_limit(endpoint)
    
    alt Rate limit exceeded
        RL-->>RT: delay_required
        RT-->>EC: delay_execution
    else Rate limit ok
        RL-->>RT: proceed
        RT->>AP: sign_request(request)
        AP-->>RT: signed_request
        RT->>RT: send HTTP request
        
        alt Request successful
            RT->>RL: register_request(endpoint, weight)
            RT->>RL: update_limits(response_headers)
            RT-->>EC: response
        else Request failed
            RT->>EH: normalize_error(transport_error)
            EH->>EH: is_retriable(error)
            
            alt Error is retriable
                EH->>EH: get_retry_delay(error)
                EH-->>RT: retry_after_delay
                RT->>RT: retry request after delay
            else Error is not retriable
                EH-->>RT: final_error
                RT-->>EC: error_response
            end
        end
    end
    
    EC-->>C: operation_result
```

### 3. Sequence Diagram - WebSocket Flow

```mermaid
sequenceDiagram
    participant C as Client Code
    participant EC as ExchangeClient
    participant WT as WebSocketTransport
    participant AP as AuthProvider
    participant EH as ErrorHandler
    
    C->>EC: get_transport(WEBSOCKET)
    EC->>WT: create if not exists
    C->>WT: subscribe(market_data, handler)
    
    WT->>WT: check if connected
    
    alt Not connected
        WT->>AP: get_credentials(exchange)
        AP-->>WT: credentials
        WT->>WT: connect with credentials
    end
    
    WT->>WT: register subscription
    
    loop While subscribed
        WT->>WT: receive message
        WT->>EH: validate message
        
        alt Valid message
            WT->>C: invoke handler(message)
        else Error in message
            WT->>EH: normalize_error(message_error)
            EH->>EH: handle_circuit_breaking(error)
            
            alt Circuit open
                EH-->>WT: reconnect recommendation
                WT->>WT: reconnect()
            else Handle normally
                EH-->>WT: error details
                WT->>C: invoke error_handler(error)
            end
        end
    end
    
    C->>WT: unsubscribe(market_data)
    WT->>WT: remove handler
    
    alt No more subscriptions
        WT->>WT: close connection
    end
```

## Component Details

### 1. Base Transport Interface (`src/exchange/transport/base.py`)

The `BaseTransport` abstract class defines the common interface for all transport methods:

- `authenticate()`: Establishes and validates credentials
- `handle_error(error)`: Processes and normalizes transport-specific errors
- `apply_rate_limiting()`: Ensures request rate adherence
- `execute_request(request)`: Executes a transport-specific request
- `close()`: Closes connections and performs cleanup

### 2. Authentication Provider (`src/exchange/auth/provider.py`)

The `AuthProvider` manages authentication across transport types:

- Works with both REST and WebSocket connections
- Integrates with the Secret Manager from Task 1
- Supports multiple authentication methods (API key/secret, JWT, OAuth)
- Handles credential rotation and refresh
- Provides signing utilities for authenticated requests

### 3. Rate Limiter (`src/exchange/rate_limiting/limiter.py`)

The enhanced `RateLimiter` tracks and enforces rate limits:

- Tracks limits across all transport types
- Supports per-endpoint and global weight-based limits
- Implements dynamic limit adjustment based on response headers
- Provides intelligent request queuing with priority support
- Handles backoff strategies for rate limit errors

### 4. Error Handler (`src/exchange/exceptions.py`)

The `ErrorHandler` standardizes error handling:

- Normalizes errors across transport types
- Provides detailed context for debugging
- Supports retry policies and circuit breaking
- Categorizes errors (connectivity, authentication, rate limit, exchange-specific)
- Implements exponential backoff for transient errors

### 5. Request/Response Models

The data models provide transport-agnostic representations:

- `Request` models with standardized parameters
- `Response` models with normalized structure
- Serialization/deserialization utilities
- Consistent typing and validation

## Implementation Notes

### Directory Structure

```
src/exchange/
├── __init__.py
├── client.py                 # Unified client interface
├── exceptions.py             # Error models and handler
├── base.py                   # Common utilities
├── transport/
│   ├── __init__.py
│   ├── base.py               # Base transport interface
│   ├── rest.py               # REST implementation
│   └── websocket.py          # WebSocket implementation
├── auth/
│   ├── __init__.py
│   ├── provider.py           # Authentication provider
│   └── credentials.py        # Credential models
└── rate_limiting/
    ├── __init__.py
    ├── limiter.py            # Rate limiter
    └── models.py             # Rate limit models
```

### Design Patterns

1. **Strategy Pattern**: Used for transport selection, allowing the client to switch between REST and WebSocket seamlessly.

2. **Factory Pattern**: Employed in the ExchangeClient to create appropriate transport instances.

3. **Repository Pattern**: Used for data access and normalization, providing a consistent interface for exchange-specific implementations.

4. **Singleton Pattern**: Applied to shared components like the rate limiter and authentication provider to ensure consistency.

5. **Observer Pattern**: Implemented for event notifications across transports, especially for WebSocket subscriptions.

6. **Adapter Pattern**: Used to normalize exchange-specific APIs into a consistent interface.

## Extension Points

The architecture supports extension in the following ways:

1. **New Transport Types**: Additional transport methods can be added by implementing the BaseTransport interface.

2. **Exchange-Specific Implementations**: Exchange-specific behavior can be encapsulated in dedicated classes that implement the common interfaces.

3. **Custom Rate Limiting Strategies**: The rate limiter can be extended with custom strategies for different exchanges.

4. **Authentication Methods**: New authentication methods can be added to the AuthProvider.

## Conclusion

This unified exchange adapter architecture provides a solid foundation for interacting with cryptocurrency exchanges through multiple transport methods. By sharing common components like authentication, rate limiting, and error handling, it ensures consistency while allowing for transport-specific optimizations.

The design prioritizes:
- Code reuse and maintainability
- Consistent error handling
- Uniform authentication and rate limiting
- Extensibility for future transport methods
- Exchange-specific customization when needed 