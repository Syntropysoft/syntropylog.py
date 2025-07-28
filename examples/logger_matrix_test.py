#!/usr/bin/env python3
"""
Logger Matrix test - testing context filtering and control.

This example demonstrates how to use the Logger Matrix to control which
context fields are included in log output, preventing log pollution
from large objects and unwanted fields.
"""

import asyncio
import sys
import os

# Add the syntropylog directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'syntropylog'))

from syntropylog import syntropy_log


async def test_basic_matrix():
    """Test basic logger matrix functionality."""
    print("\n🔧 Testing basic Logger Matrix...")
    
    # Configure logger matrix
    syntropy_log.configure_logger_matrix(
        include_fields=['user_id', 'session_id', 'correlation_id'],
        exclude_fields=['internal_data', 'temp_vars'],
        level_matrices={
            'debug': ['all_fields', 'debug_info'],
            'info': ['user_id', 'action', 'status'],
            'warn': ['user_id', 'error_code'],
            'error': ['user_id', 'error_details', 'stack_trace']
        }
    )
    
    # Add context with different visibility
    syntropy_log.add_context('user_id', '12345')
    syntropy_log.add_context('session_id', 'session_abc')
    syntropy_log.add_context('internal_data', {'temp': 'data'})  # Will be excluded
    syntropy_log.add_context('temp_vars', ['var1', 'var2'])      # Will be excluded
    
    # Test different log levels
    syntropy_log.debug('Debug message with all context')
    syntropy_log.info('Info message with filtered context')
    syntropy_log.warn('Warning message with minimal context')
    syntropy_log.error('Error message with error context')


async def test_large_objects():
    """Test handling of large objects and arrays."""
    print("\n📦 Testing large objects handling...")
    
    # Create large objects that should be filtered
    large_dict = {f'key_{i}': f'value_{i}' for i in range(50)}
    large_array = [f'item_{i}' for i in range(100)]
    complex_object = {
        'nested': {
            'deep': {
                'very_deep': {
                    'data': 'this should be truncated'
                }
            }
        }
    }
    
    # Add large objects to context
    syntropy_log.add_context('large_dict', large_dict)
    syntropy_log.add_context('large_array', large_array)
    syntropy_log.add_context('complex_object', complex_object)
    syntropy_log.add_context('simple_field', 'this should appear')
    
    # Log with different levels
    syntropy_log.info('Message with large objects')
    syntropy_log.debug('Debug with large objects')


async def test_matrix_control():
    """Test matrix control methods."""
    print("\n🎛️ Testing matrix control methods...")
    
    # Add context with matrix control
    syntropy_log.add_context_with_matrix('public_data', 'visible in logs', include_in_logs=True)
    syntropy_log.add_context_with_matrix('private_data', 'hidden from logs', include_in_logs=False)
    syntropy_log.add_context_with_matrix('conditional_data', 'conditional visibility', include_in_logs=True)
    
    # Log to see what appears
    syntropy_log.info('Message with matrix-controlled context')
    
    # Show filtered context
    filtered_context = syntropy_log.get_filtered_context('info')
    print(f"📊 Filtered context for 'info' level: {filtered_context}")


async def test_per_level_filtering():
    """Test per-level filtering."""
    print("\n📊 Testing per-level filtering...")
    
    # Configure level-specific matrices
    syntropy_log.configure_logger_matrix(
        level_matrices={
            'debug': ['user_id', 'session_id', 'debug_info', 'all_fields'],
            'info': ['user_id', 'action', 'status'],
            'warn': ['user_id', 'warning_code'],
            'error': ['user_id', 'error_code', 'error_message']
        }
    )
    
    # Add various context fields
    syntropy_log.add_context('user_id', '12345')
    syntropy_log.add_context('session_id', 'session_abc')
    syntropy_log.add_context('action', 'login')
    syntropy_log.add_context('status', 'success')
    syntropy_log.add_context('debug_info', 'debug details')
    syntropy_log.add_context('warning_code', 'W001')
    syntropy_log.add_context('error_code', 'E001')
    syntropy_log.add_context('error_message', 'Something went wrong')
    
    # Test each level
    print("\n🔍 Testing each log level:")
    syntropy_log.debug('Debug message')
    syntropy_log.info('Info message')
    syntropy_log.warn('Warning message')
    syntropy_log.error('Error message')


async def test_dynamic_matrix():
    """Test dynamic matrix configuration."""
    print("\n⚡ Testing dynamic matrix configuration...")
    
    # Start with basic configuration
    syntropy_log.configure_logger_matrix(
        include_fields=['user_id'],
        exclude_fields=['temp_data']
    )
    
    syntropy_log.add_context('user_id', '12345')
    syntropy_log.add_context('temp_data', 'should be hidden')
    syntropy_log.add_context('dynamic_field', 'should appear')
    
    syntropy_log.info('Message with initial matrix')
    
    # Dynamically update matrix
    syntropy_log.configure_logger_matrix(
        include_fields=['user_id', 'dynamic_field'],
        exclude_fields=['temp_data', 'old_field']
    )
    
    syntropy_log.add_context('new_field', 'newly visible')
    syntropy_log.info('Message with updated matrix')


async def main():
    """Main example function."""
    print("🚀 SyntropyLog Python - Logger Matrix Test")
    print("=" * 60)
    
    try:
        # Initialize the framework
        print("\n📋 Initializing SyntropyLog framework...")
        config = {
            'logger': {
                'level': 'debug',
                'transports': ['console']
            },
            'context': {
                'correlation_enabled': True,
                'auto_generate_ids': True,
                'logger_matrix': {
                    'include_fields': ['correlation_id', 'user_id'],
                    'exclude_fields': ['internal_debug'],
                    'max_object_depth': 2,
                    'max_field_length': 500
                }
            }
        }
        
        await syntropy_log.init(config)
        print("✅ Framework initialized successfully")
        
        # Run tests
        await test_basic_matrix()
        await test_large_objects()
        await test_matrix_control()
        await test_per_level_filtering()
        await test_dynamic_matrix()
        
        print("\n⏳ Waiting 2 seconds before shutdown...")
        await asyncio.sleep(2)
        
    except Exception as error:
        print(f"\n❌ Error during execution: {error}")
    finally:
        # Graceful shutdown
        print("\n🛑 Starting graceful shutdown...")
        shutdown_result = await syntropy_log.shutdown()
        print(f"✅ Shutdown completed: {shutdown_result['success']}")


if __name__ == "__main__":
    asyncio.run(main())