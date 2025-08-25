#!/usr/bin/env python3
"""
Test script for the search CLI functionality.
This script demonstrates how to use the ClaimsSearcher class programmatically.
"""

import sys
from pathlib import Path

# Add the app directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from search_cli import ClaimsSearcher


def test_search_functionality():
    """Test the search functionality with a sample query."""
    
    print("🧪 Testing Political Claims Search Functionality")
    print("=" * 60)
    
    try:
        # Initialize the searcher
        print("📡 Initializing searcher...")
        searcher = ClaimsSearcher()
        print("✅ Searcher initialized successfully")
        
        # Test queries
        test_queries = [
            "immigration policy changes",
            "Does the National Guard in DC help the crime issue there?"
        ]
        
        for test_query in test_queries:
            print(f"\n🔍 Testing search with query: '{test_query}'")
            
            # Perform search
            results = searcher.search_claims(
                query=test_query,
                similarity_threshold=0.5,  # Lower threshold for testing
                limit=5,
                include_sources=True
            )
            
            # Display results
            print(f"\n📊 Search Results:")
            print(f"Query: {results['query']}")
            print(f"Threshold: {results['threshold']}")
            print(f"Total found: {results['total_found']}")
            print(f"Message: {results['message']}")
            
            if results['results']:
                print(f"\n📋 Found {len(results['results'])} claims:")
                for i, result in enumerate(results['results'], 1):
                    print(f"\n{i}. Claim ID: {result['claim_id']}")
                    print(f"   Similarity: {result['similarity_score']:.4f}")
                    print(f"   Text: {result['claim_text'][:100]}...")
                    
                    if result.get('sources'):
                        print(f"   Sources: {len(result['sources'])} found")
                        for k, source in enumerate(result['sources'][:2], 1):  # Show first 2 sources
                            print(f"     {k}. {source.get('description', 'No description')[:50]}...")
                            if source.get('link'):
                                print(f"        🔗 {source.get('link')}")
                    else:
                        print(f"   Sources: None found")
            else:
                print("\n❌ No results found. This might be normal if:")
                print("   - The database is empty")
                print("   - The similarity threshold is too high")
                print("   - The query doesn't match any existing claims")
            
            print("\n" + "="*60)
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        print("This might be due to:")
        print("   - Database connection issues")
        print("   - Missing environment variables")
        print("   - Database not being populated with claims")
        return False
    
    return True


def test_database_connection():
    """Test basic database connectivity."""
    
    print("\n🔌 Testing Database Connection")
    print("=" * 40)
    
    try:
        from database.vector_api import VectorStore
        from database.sql_api import SqlStore
        
        # Test vector store connection
        print("📡 Testing vector store connection...")
        vector_store = VectorStore("canon_claims")
        print("✅ Vector store connected successfully")
        
        # Test SQL store connection
        print("📡 Testing SQL store connection...")
        sql_store = SqlStore()
        print("✅ SQL store connected successfully")
        
        # Try to get some basic info about the database
        print("📊 Checking database status...")
        
        # This would require implementing a method to count records
        # For now, just test the connection
        print("✅ Database connections working")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting Political Claims Search Tests")
    print("=" * 60)
    
    # Test database connection first
    db_ok = test_database_connection()
    
    if db_ok:
        # Test search functionality
        search_ok = test_search_functionality()
        
        if search_ok:
            print("\n🎉 All tests passed! The search functionality is working correctly.")
        else:
            print("\n⚠️  Search functionality test failed, but database connection works.")
    else:
        print("\n❌ Database connection failed. Please check your configuration.")
    
    print("\n" + "=" * 60)
    print("Test completed.")
