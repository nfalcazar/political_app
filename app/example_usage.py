#!/usr/bin/env python3
"""
Example usage of the Political Claims Search functionality.

This script demonstrates how to use the ClaimsSearcher class programmatically
for integrating search functionality into other applications.
"""

import sys
from pathlib import Path

# Add the app directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from search_cli import ClaimsSearcher


def example_basic_search():
    """Example of basic search functionality."""
    
    print("🔍 Example: Basic Search")
    print("=" * 40)
    
    searcher = ClaimsSearcher()
    
    # Example queries to try
    queries = [
        "immigration policy changes",
        "tax reform legislation", 
        "healthcare policy updates",
        "climate change regulations"
    ]
    
    for query in queries:
        print(f"\n📝 Searching for: '{query}'")
        
        results = searcher.search_claims(
            query=query,
            similarity_threshold=0.6,  # Moderate threshold
            limit=3,
            include_sources=True
        )
        
        print(f"   Found: {results['total_found']} claims")
        
        if results['results']:
            for i, result in enumerate(results['results'], 1):
                print(f"   {i}. Similarity: {result['similarity_score']:.3f}")
                print(f"      Text: {result['claim_text'][:80]}...")
        else:
            print("   No results found")


def example_advanced_search():
    """Example of advanced search with different thresholds."""
    
    print("\n🔍 Example: Advanced Search with Different Thresholds")
    print("=" * 60)
    
    searcher = ClaimsSearcher()
    query = "immigration policy"
    
    thresholds = [0.5, 0.7, 0.8, 0.9]
    
    for threshold in thresholds:
        print(f"\n📊 Threshold: {threshold}")
        
        results = searcher.search_claims(
            query=query,
            similarity_threshold=threshold,
            limit=5,
            include_sources=False  # Exclude sources for cleaner output
        )
        
        print(f"   Results: {results['total_found']}")
        
        if results['results']:
            for result in results['results']:
                print(f"   - {result['similarity_score']:.3f}: {result['claim_text'][:60]}...")


def example_programmatic_integration():
    """Example of how to integrate search into other applications."""
    
    print("\n🔍 Example: Programmatic Integration")
    print("=" * 50)
    
    searcher = ClaimsSearcher()
    
    # Simulate a claim checking system
    user_claim = "The government increased taxes on middle class families"
    
    print(f"User claim: '{user_claim}'")
    print("Checking for similar claims in database...")
    
    # Search for similar claims
    results = searcher.search_claims(
        query=user_claim,
        similarity_threshold=0.7,
        limit=5,
        include_sources=True
    )
    
    if results['results']:
        print(f"\n✅ Found {len(results['results'])} similar claims:")
        
        for result in results['results']:
            print(f"\n📋 Similar Claim (Score: {result['similarity_score']:.3f}):")
            print(f"   Text: {result['claim_text']}")
            
            if result.get('sources'):
                print(f"   Sources: {len(result['sources'])} found")
                for source in result['sources'][:2]:  # Show first 2 sources
                    print(f"     - {source.get('description', 'No description')}")
            else:
                print("   Sources: None found")
    else:
        print("\n❌ No similar claims found in database")


def example_batch_search():
    """Example of batch searching multiple claims."""
    
    print("\n🔍 Example: Batch Search")
    print("=" * 30)
    
    searcher = ClaimsSearcher()
    
    # List of claims to check
    claims_to_check = [
        "immigration policy changes",
        "tax reform legislation",
        "healthcare policy updates",
        "climate change regulations",
        "education funding increases"
    ]
    
    print(f"Checking {len(claims_to_check)} claims...")
    
    all_results = {}
    
    for claim in claims_to_check:
        results = searcher.search_claims(
            query=claim,
            similarity_threshold=0.6,
            limit=3,
            include_sources=False
        )
        
        all_results[claim] = results
    
    # Summary
    print("\n📊 Search Summary:")
    for claim, results in all_results.items():
        print(f"   '{claim}': {results['total_found']} results")


if __name__ == "__main__":
    print("🚀 Political Claims Search - Usage Examples")
    print("=" * 60)
    
    try:
        # Run examples
        example_basic_search()
        example_advanced_search()
        example_programmatic_integration()
        example_batch_search()
        
        print("\n✅ All examples completed successfully!")
        print("\n💡 Tips:")
        print("   - Adjust similarity thresholds based on your needs")
        print("   - Use include_sources=True to get source information")
        print("   - Higher thresholds (0.8+) give more precise matches")
        print("   - Lower thresholds (0.5-0.7) give broader results")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        print("Make sure your database is running and properly configured.")
