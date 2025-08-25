#!/usr/bin/env python3
"""
CLI Search Program for Political Claims Database

This program allows users to search the canon_claims table using vector similarity search.
Users can input a claim they want to check, and the program will return similar claims
from the database that meet a specified similarity threshold.
"""

import argparse
import logging
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd

# Add the app directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from database.vector_api import VectorStore
from database.sql_api import SqlStore
from util.ai_ext_calls import OpenAiSync


class ClaimsSearcher:
    """
    A class for searching claims in the database using vector similarity.
    """
    
    def __init__(self):
        """Initialize the searcher with vector store and SQL store."""
        self.vector_store = VectorStore("canon_claims")
        self.sql_store = SqlStore()
        self.ai_client = OpenAiSync(provider="openai")
        
    def search_claims(
        self, 
        query: str, 
        similarity_threshold: float = 0.7,
        limit: int = 10,
        include_sources: bool = True
    ) -> Dict[str, Any]:
        """
        Search for claims similar to the input query.
        
        Args:
            query: The claim text to search for
            similarity_threshold: Minimum similarity score (0.0 to 1.0, where 1.0 is exact match)
            limit: Maximum number of results to return
            include_sources: Whether to include source information in results
            
        Returns:
            Dictionary containing search results and metadata
        """
        try:
            # Perform vector search
            results_df = self.vector_store.search_by_text(
                query_text=query,
                limit=limit,
                return_dataframe=True
            )
            
            # Filter results by similarity threshold
            # Note: distance is cosine distance, so lower is better
            # Convert to similarity score (1 - distance)
            results_df['similarity'] = 1 - results_df['distance']
            filtered_results = results_df[results_df['similarity'] >= similarity_threshold]
            
            if filtered_results.empty:
                return {
                    'query': query,
                    'threshold': similarity_threshold,
                    'results': [],
                    'total_found': 0,
                    'message': f"No claims found with similarity >= {similarity_threshold}"
                }
            
            # Get additional source information if requested
            results_list = []
            for _, row in filtered_results.iterrows():
                result = {
                    'claim_id': row['id'],
                    'claim_text': row['content'],
                    'similarity_score': round(row['similarity'], 4),
                    'metadata': row.get('metadata_', {})
                }
                
                if include_sources:
                    # Get sources associated with this claim
                    sources = self._get_sources_for_claim(row['id'])
                    result['sources'] = sources
                
                results_list.append(result)
            
            return {
                'query': query,
                'threshold': similarity_threshold,
                'results': results_list,
                'total_found': len(results_list),
                'message': f"Found {len(results_list)} claims with similarity >= {similarity_threshold}"
            }
            
        except Exception as e:
            logging.error(f"Error during search: {e}")
            return {
                'query': query,
                'threshold': similarity_threshold,
                'results': [],
                'total_found': 0,
                'message': f"Error during search: {str(e)}"
            }
    
    def _get_sources_for_claim(self, claim_id: str) -> List[Dict[str, Any]]:
        """
        Get sources associated with a specific canonical claim.
        Follows the relationship chain: canonical_claim -> claim -> source
        
        Args:
            claim_id: The ID of the canonical claim
            
        Returns:
            List of source dictionaries
        """
        try:
            sources = []
            
            # Step 1: Get all claims that reference this canonical claim
            canonical_edges = self.sql_store.get_edges_by_node('canonical_claim', claim_id)
            
            for edge in canonical_edges:
                if edge.get('dest_type') == 'claim' and edge.get('relationship_type') == 'references':
                    claim_id = edge.get('dest_id')
                    
                    # Step 2: Get all sources that are cited by this claim
                    claim_edges = self.sql_store.get_edges_by_node('claim', claim_id)
                    
                    for claim_edge in claim_edges:
                        if claim_edge.get('dest_type') == 'source' and claim_edge.get('relationship_type') == 'cites':
                            source_id = claim_edge.get('dest_id')
                            source_data = self.sql_store.get_data_by_field('sources', 'id', source_id)
                            if source_data:
                                sources.append(source_data[0])
            
            return sources
        except Exception as e:
            logging.error(f"Error getting sources for claim {claim_id}: {e}")
            return []
    
    def interactive_search(self):
        """
        Run an interactive search session.
        """
        print("🔍 Political Claims Search Tool")
        print("=" * 50)
        print("Enter a claim to search for similar claims in the database.")
        print("Type 'quit' to exit, 'help' for commands.")
        print()
        
        while True:
            try:
                # Get user input
                query = input("Enter claim to search: ").strip()
                
                if query.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break
                
                if query.lower() == 'help':
                    self._show_help()
                    continue
                
                if not query:
                    print("Please enter a claim to search.")
                    continue
                
                # Get search parameters
                threshold = self._get_similarity_threshold()
                limit = self._get_result_limit()
                include_sources = self._get_include_sources()
                
                print(f"\n🔍 Searching for: '{query}'")
                print(f"📊 Similarity threshold: {threshold}")
                print(f"📋 Max results: {limit}")
                print("⏳ Searching...")
                
                # Perform search
                results = self.search_claims(
                    query=query,
                    similarity_threshold=threshold,
                    limit=limit,
                    include_sources=include_sources
                )
                
                # Display results
                self._display_results(results)
                
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def _get_similarity_threshold(self) -> float:
        """Get similarity threshold from user input."""
        while True:
            try:
                threshold_input = input("Similarity threshold (0.0-1.0, default 0.7): ").strip()
                if not threshold_input:
                    return 0.7
                
                threshold = float(threshold_input)
                if 0.0 <= threshold <= 1.0:
                    return threshold
                else:
                    print("Threshold must be between 0.0 and 1.0")
            except ValueError:
                print("Please enter a valid number")
    
    def _get_result_limit(self) -> int:
        """Get result limit from user input."""
        while True:
            try:
                limit_input = input("Max results (default 10): ").strip()
                if not limit_input:
                    return 10
                
                limit = int(limit_input)
                if limit > 0:
                    return limit
                else:
                    print("Limit must be greater than 0")
            except ValueError:
                print("Please enter a valid number")
    
    def _get_include_sources(self) -> bool:
        """Get whether to include sources from user input."""
        while True:
            include_input = input("Include sources? (y/n, default y): ").strip().lower()
            if not include_input or include_input in ['y', 'yes']:
                return True
            elif include_input in ['n', 'no']:
                return False
            else:
                print("Please enter y or n")
    
    def _show_help(self):
        """Show help information."""
        print("\n📖 Help:")
        print("- Enter any claim text to search for similar claims")
        print("- Similarity threshold: 0.0 = no similarity, 1.0 = exact match")
        print("- Higher thresholds return fewer but more relevant results")
        print("- Commands: 'help', 'quit'")
        print()
    
    def _display_results(self, results: Dict[str, Any]):
        """Display search results in a formatted way."""
        print(f"\n{results['message']}")
        
        if not results['results']:
            print("No results found.")
            return
        
        print(f"\n📋 Results ({len(results['results'])} found):")
        print("=" * 80)
        
        for i, result in enumerate(results['results'], 1):
            print(f"\n{i}. Claim ID: {result['claim_id']}")
            print(f"   Similarity: {result['similarity_score']:.4f}")
            print(f"   Text: {result['claim_text']}")
            
            if result.get('metadata'):
                metadata = result['metadata']
                if metadata.get('category'):
                    print(f"   Category: {metadata['category']}")
                if metadata.get('data_id'):
                    print(f"   Data ID: {metadata['data_id']}")
            
            if result.get('sources'):
                print(f"   Sources ({len(result['sources'])}):")
                for j, source in enumerate(result['sources'], 1):
                    print(f"     {j}. {source.get('description', 'No description')}")
                    
                    # Display source link if available
                    if source.get('link'):
                        print(f"        🔗 Link: {source.get('link')}")
                    
                    # Display metadata if available
                    if source.get('metadata_'):
                        metadata = source.get('metadata_', {})
                        if isinstance(metadata, dict):
                            if metadata.get('source_type'):
                                print(f"        📄 Type: {metadata['source_type']}")
                            if metadata.get('publisher_or_court'):
                                print(f"        🏢 Publisher: {metadata['publisher_or_court']}")
                            if metadata.get('url'):
                                print(f"        🌐 URL: {metadata['url']}")
                    
                    # Display verification status
                    if source.get('verified') is not None:
                        status = "✅ Verified" if source.get('verified') else "❌ Not Verified"
                        print(f"        {status}")
                    
                    print()  # Add spacing between sources
        
        print("\n" + "=" * 80)


def main():
    """Main function to run the CLI search tool."""
    parser = argparse.ArgumentParser(
        description="Search political claims database using vector similarity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python search_cli.py --query "immigration policy changes" --threshold 0.8
  python search_cli.py --interactive
  python search_cli.py --query "tax reform" --limit 5 --no-sources
        """
    )
    
    parser.add_argument(
        '--query', '-q',
        type=str,
        help='Claim text to search for'
    )
    
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.7,
        help='Similarity threshold (0.0-1.0, default: 0.7)'
    )
    
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=10,
        help='Maximum number of results (default: 10)'
    )
    
    parser.add_argument(
        '--no-sources',
        action='store_true',
        help='Exclude source information from results'
    )
    
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        searcher = ClaimsSearcher()
        
        if args.interactive:
            searcher.interactive_search()
        elif args.query:
            results = searcher.search_claims(
                query=args.query,
                similarity_threshold=args.threshold,
                limit=args.limit,
                include_sources=not args.no_sources
            )
            searcher._display_results(results)
        else:
            parser.print_help()
            
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
