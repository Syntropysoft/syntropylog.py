#!/usr/bin/env python3
"""
Data Masking test - testing ultra-fast masking with JSON flattening.

This example demonstrates the DataMaskingEngine using JSON flattening strategy
for extreme processing speed, handling any object depth and complexity.
"""

import asyncio
import sys
import os
import time

# Add the syntropylog directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'syntropylog'))

from syntropylog import syntropy_log


def create_complex_data():
    """Create complex nested data for testing."""
    return {
        "user": {
            "profile": {
                "credit_card": "4111-1111-1111-1111",
                "ssn": "123-45-6789",
                "email": "john.doe@example.com",
                "phone": "555-123-4567"
            },
            "orders": [
                {
                    "payment": {
                        "card_number": "5555-5555-5555-5555",
                        "cvv": "123"
                    },
                    "items": [
                        {"product_id": "PROD001", "price": 29.99},
                        {"product_id": "PROD002", "price": 49.99}
                    ]
                },
                {
                    "payment": {
                        "card_number": "6666-6666-6666-6666",
                        "cvv": "456"
                    },
                    "items": [
                        {"product_id": "PROD003", "price": 79.99}
                    ]
                }
            ],
            "preferences": {
                "notifications": {
                    "email_alerts": "alerts@example.com",
                    "sms_number": "555-987-6543"
                }
            }
        },
        "session": {
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "refresh_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        },
        "api_keys": {
            "stripe_key": "sk_test_1234567890abcdef",
            "aws_key": "AKIAIOSFODNN7EXAMPLE"
        }
    }


async def test_basic_masking():
    """Test basic masking functionality."""
    print("\n🔧 Testing basic masking...")
    
    # Configure masking rules
    syntropy_log.add_masking_rule(r"(?:credit|card|cc|payment).*?(?:number|num|id)", "credit_card")
    syntropy_log.add_masking_rule(r"(?:ssn|social|security).*?(?:number|num)", "ssn")
    syntropy_log.add_masking_rule(r"(?:email|mail|e-mail)", "email")
    syntropy_log.add_masking_rule(r"(?:phone|tel|mobile|cell).*?(?:number|num)", "phone")
    syntropy_log.add_masking_rule(r"(?:token|key|auth|jwt|bearer)", "token")
    syntropy_log.add_masking_rule(r"(?:password|pass|pwd|secret)", "password")
    
    # Create test data
    test_data = {
        "credit_card": "4111-1111-1111-1111",
        "ssn": "123-45-6789",
        "email": "test@example.com",
        "phone": "555-123-4567",
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "password": "secret123",
        "normal_field": "this should not be masked"
    }
    
    # Mask the data
    masked_data = syntropy_log.mask_data(test_data)
    
    print("📊 Original data:")
    for key, value in test_data.items():
        print(f"   {key}: {value}")
    
    print("\n🔒 Masked data:")
    for key, value in masked_data.items():
        print(f"   {key}: {value}")


async def test_complex_nested_masking():
    """Test masking with complex nested objects."""
    print("\n🏗️ Testing complex nested masking...")
    
    # Create complex nested data
    complex_data = create_complex_data()
    
    print("📊 Original complex data structure:")
    print(f"   User credit card: {complex_data['user']['profile']['credit_card']}")
    print(f"   User SSN: {complex_data['user']['profile']['ssn']}")
    print(f"   Order 1 payment: {complex_data['user']['orders'][0]['payment']['card_number']}")
    print(f"   Session token: {complex_data['session']['token']}")
    
    # Mask the complex data
    start_time = time.time()
    masked_data = syntropy_log.mask_data(complex_data)
    end_time = time.time()
    
    print(f"\n⚡ Masking completed in {(end_time - start_time) * 1000:.2f}ms")
    
    print("\n🔒 Masked complex data:")
    print(f"   User credit card: {masked_data['user']['profile']['credit_card']}")
    print(f"   User SSN: {masked_data['user']['profile']['ssn']}")
    print(f"   Order 1 payment: {masked_data['user']['orders'][0]['payment']['card_number']}")
    print(f"   Session token: {masked_data['session']['token']}")


async def test_custom_masking_rules():
    """Test custom masking rules."""
    print("\n🎨 Testing custom masking rules...")
    
    # Custom masking function
    def custom_phone_mask(value: str) -> str:
        """Custom phone masking that shows only area code."""
        if len(value) >= 10:
            return f"({value[:3]}) ***-****"
        return "*" * len(value)
    
    # Add custom rule
    syntropy_log.add_masking_rule(
        r"custom_phone",
        "custom",
        custom_mask=custom_phone_mask
    )
    
    test_data = {
        "custom_phone": "555-123-4567",
        "normal_phone": "555-987-6543",
        "other_field": "normal data"
    }
    
    masked_data = syntropy_log.mask_data(test_data)
    
    print("📊 Custom masking results:")
    for key, value in masked_data.items():
        print(f"   {key}: {value}")


async def test_performance():
    """Test masking performance with large datasets."""
    print("\n🚀 Testing performance...")
    
    # Create large dataset
    large_data = []
    for i in range(1000):
        large_data.append({
            "user_id": f"user_{i}",
            "credit_card": f"4111-1111-1111-{i:04d}",
            "email": f"user{i}@example.com",
            "phone": f"555-{i:03d}-{i:04d}",
            "token": f"token_{i}_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "normal_data": f"normal_data_{i}"
        })
    
    print(f"📊 Processing {len(large_data)} records...")
    
    # Test performance
    start_time = time.time()
    masked_data = syntropy_log.mask_data(large_data)
    end_time = time.time()
    
    duration = end_time - start_time
    throughput = len(large_data) / duration
    
    print(f"⚡ Performance results:")
    print(f"   Duration: {duration:.3f}s")
    print(f"   Throughput: {throughput:.0f} records/second")
    print(f"   Average per record: {(duration / len(large_data)) * 1000:.2f}ms")


async def test_logging_with_masking():
    """Test logging with automatic masking."""
    print("\n📝 Testing logging with automatic masking...")
    
    # Add sensitive data to context
    syntropy_log.add_context("user_credit_card", "4111-1111-1111-1111")
    syntropy_log.add_context("user_ssn", "123-45-6789")
    syntropy_log.add_context("user_email", "john.doe@example.com")
    syntropy_log.add_context("normal_field", "this is normal")
    
    # Log with sensitive data
    print("📊 Logging with sensitive data (should be masked automatically):")
    syntropy_log.info("User payment processed", 
                     payment_method="credit_card",
                     amount=99.99,
                     sensitive_data={
                         "card_number": "5555-5555-5555-5555",
                         "cvv": "123",
                         "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                     })


async def test_masking_stats():
    """Test masking engine statistics."""
    print("\n📊 Testing masking statistics...")
    
    stats = syntropy_log.get_masking_stats()
    
    print("📈 Masking engine statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")


async def main():
    """Main example function."""
    print("🚀 SyntropyLog Python - Data Masking Engine Test")
    print("=" * 60)
    
    try:
        # Initialize the framework
        print("\n📋 Initializing SyntropyLog framework...")
        config = {
            'logger': {
                'level': 'info',
                'transports': ['console']
            },
            'context': {
                'enabled': True,
                'enable_auto_correlation': True
            },
            'masking': {
                'rules': [
                    {
                        'pattern': r'(?:credit|card|cc|payment).*?(?:number|num|id)',
                        'strategy': 'credit_card'
                    },
                    {
                        'pattern': r'(?:ssn|social|security).*?(?:number|num)',
                        'strategy': 'ssn'
                    }
                ]
            }
        }
        
        await syntropy_log.init(config)
        print("✅ Framework initialized successfully")
        
        # Run tests
        await test_basic_masking()
        await test_complex_nested_masking()
        await test_custom_masking_rules()
        await test_performance()
        await test_logging_with_masking()
        await test_masking_stats()
        
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